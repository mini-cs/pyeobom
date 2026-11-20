"""임베딩 모델 바꾸기(v1.9): 후보 조각(운영과 글·번호가 같고 임베딩만 다름)과 벌마다 질문 임베딩.

설계 `docs/superpowers/specs/2026-11-20-embedding-large-design.md` 5절, 계획 Task 2.
CLI: python -m measure.emb_large estimate | store | verify | measure [--out 폴더]
"""
import csv
import functools
import json
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.retrieval.embeddings import embed_query, embed_texts
from ingest.load import ROOT
from measure.v17_bundle import BundleChunk, bundle_exists


@dataclass(frozen=True)
class EmbedSpec:
    model: str
    dimensions: int | None


CANDIDATE = EmbedSpec("text-embedding-3-large", 1536)
BUNDLE = "emb_large"
BUNDLE_EMBED: dict[str, EmbedSpec] = {BUNDLE: CANDIDATE}
PRICE_PER_CHAR = 1.3e-7  # 0.13달러/100만 토큰, 글자 = 토큰 가정
OUT = ROOT / "measure" / "out" / "v17"
STAGE1 = OUT / "fable-stage1"  # 운영 1~20위 대조용(2026-11-20 1단계)
_EMBEDS: dict[EmbedSpec, Callable[[str], list[float]]] = {}
INSERT_SQL = "INSERT INTO bundle_chunks (bundle, id, doc_id, page, content, embedding) VALUES (%s, %s, %s, %s, %s, %s)"


def embed_for(bundle: str | None, base: Callable[[str], list[float]]) -> Callable[[str], list[float]]:
    """다시 임베딩한 벌이면 그 설정의 질문 임베딩(같은 설정이면 같은 함수 객체), 아니면 base."""
    spec = BUNDLE_EMBED.get(bundle) if bundle else None
    if spec is None:
        return base
    if spec not in _EMBEDS:
        _EMBEDS[spec] = functools.partial(embed_query, model=spec.model, dimensions=spec.dimensions)
    return _EMBEDS[spec]


def production_chunks(conn) -> list[BundleChunk]:
    """운영 chunks 전부(설명서 + 가이드), id 순, 읽기만."""
    rows = conn.execute("SELECT id, doc_id, page, content FROM chunks ORDER BY id").fetchall()
    return [BundleChunk(*r) for r in rows]


def store_reembedded(name: str, chunks: list[BundleChunk], spec: EmbedSpec, *, conn, embed=None) -> int:
    """본문 그대로 spec으로 모두 임베딩한 뒤 한 트랜잭션으로 같은 id·doc_id·page·content로 넣는다. 넣은 행 수."""
    if bundle_exists(conn, name):
        raise SystemExit(f"이미 저장된 실험 조각 한 벌이라 멈춤: {name} (지우기는 사용자 확인 뒤)")
    conn.commit()  # 위 SELECT가 연 암묵 트랜잭션을 닫아, 임베딩 동안 트랜잭션이 열린 채 남지 않게
    vectors = (embed or embed_texts)([c.content for c in chunks], model=spec.model, dimensions=spec.dimensions)
    rows = [(name, c.id, c.doc_id, c.page, c.content, v) for c, v in zip(chunks, vectors, strict=True)]
    with conn.transaction(), conn.cursor() as cur:  # 임베딩을 다 받은 뒤에만 넣는다(일부만 들어간 한 벌 방지)
        cur.executemany(INSERT_SQL, rows)
    return len(rows)


def text_mismatches(conn, name: str) -> list[int]:
    """운영 chunks와 한 벌의 id 집합·doc_id·page·content가 다른 id. 같으면 []."""
    rows = conn.execute(
        """SELECT COALESCE(c.id, b.id) FROM chunks c
           FULL OUTER JOIN (SELECT id, doc_id, page, content FROM bundle_chunks WHERE bundle = %s) b ON b.id = c.id
           WHERE c.id IS NULL OR b.id IS NULL OR b.doc_id IS DISTINCT FROM c.doc_id
             OR b.page IS DISTINCT FROM c.page OR b.content IS DISTINCT FROM c.content
           ORDER BY 1""", (name,)).fetchall()
    return [r[0] for r in rows]


def rank_buckets(ranks: list[int | None]) -> dict[str, int]:
    def bucket(r):
        if r is None or r > 100:
            return "100+"
        return next(k for k, hi in (("1-5", 5), ("6-10", 10), ("11-20", 20), ("21-30", 30), ("31-50", 50), ("51-100", 100)) if r <= hi)
    c = Counter(bucket(r) for r in ranks)
    return {k: c.get(k, 0) for k in ("1-5", "6-10", "11-20", "21-30", "31-50", "51-100", "100+")}


def _production_rank_mismatches(rows: dict) -> list[tuple]:
    """운영 벌 순위를 2026-11-20 1단계(20위까지)와 견준다. 21위 이상은 그 파일에서 "20위 밖"(빈칸)이다."""
    out = []
    for set_name in ("dev", "q30"):
        with open(STAGE1 / f"{set_name}-production.csv", encoding="utf-8-sig") as f:
            old = {r["id"]: r["rank"] for r in csv.DictReader(f)}
        for x in rows[(set_name, None)]:
            now = str(x["rank"]) if x["rank"] and x["rank"] <= 20 else ""
            if old.get(x["id"]) != now:
                out.append((set_name, x["id"], old.get(x["id"]), now))
    return out


def measure(out_name: str = "emb-stage1") -> None:
    from ingest.__main__ import load_env
    load_env()
    from app.ask.routes import get_deps
    from app.catalog.registry import load_models
    from app.core.config import get_settings
    from app.core.db import get_conn
    from evaluation.run_config import warn_if_different, write_settings
    from measure.search_eval import bundle_fns, read_cases
    from measure.v17_stage1 import SETS, guard_cases_path, measure_sets

    settings = get_settings()
    if warn_if_different(settings):
        raise SystemExit("운영 기본값과 다른 설정이라 멈춤")
    if settings.search_mode != "vector":
        raise SystemExit("벡터 검색(search_mode=vector)에서만 써서 멈춤")
    for p in SETS.values():
        guard_cases_path(p)
    models = {m["id"]: m for m in load_models()}
    deps = get_deps()
    fns = lambda b: (deps.search, deps.diagnostic) if b is None else bundle_fns(b, models, get_conn)
    cases = {k: read_cases(ROOT / p) for k, p in SETS.items()}
    summary, rows = measure_sets(cases, [None, BUNDLE], deps.embed_query, fns, top_k=settings.top_k,
                                 embed_for=embed_for, depth=100)
    if bad := _production_rank_mismatches(rows):
        raise SystemExit(f"운영 벌 1~20위가 2026-11-20 1단계와 달라 멈춤: {bad}")
    out = OUT / out_name
    out.mkdir(parents=True, exist_ok=True)
    for (set_name, b), r in rows.items():
        path = out / f"{set_name}-{b or 'production'}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(r[0]))
            w.writeheader()
            w.writerows(r)
        spec = BUNDLE_EMBED.get(b)
        write_settings(path, settings, f"emb-{out_name}-{set_name}",
                       experiment={"bundle": b, "set": set_name, "depth": 100,
                                   "query_embed": {"model": spec.model, "dimensions": spec.dimensions} if spec else "운영 설정"})
    buckets = {s: {b or "production": rank_buckets([x["rank"] for x in rows[(s, b)]]) for b in (None, BUNDLE)} for s in cases}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "buckets.json").write_text(json.dumps(buckets, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"summary": summary, "buckets": buckets}, ensure_ascii=False))


def main() -> None:
    args = sys.argv[1:]
    if args[:1] in (["estimate"], ["store"], ["verify"]):
        from ingest.__main__ import load_env
        load_env()
        from app.core.db import get_conn
        with get_conn() as conn:
            if args == ["estimate"]:
                chunks = production_chunks(conn)
                chars = sum(len(c.content) for c in chunks)
                print({"chunks": len(chunks), "chars": chars, "cost_usd": round(chars * PRICE_PER_CHAR, 6)})
            elif args == ["store"]:
                chunks = production_chunks(conn)
                n = store_reembedded(BUNDLE, chunks, CANDIDATE, conn=conn)
                print({"bundle": BUNDLE, "rows": n, "chars": sum(len(c.content) for c in chunks)})
            elif args == ["verify"]:
                bad = text_mismatches(conn, BUNDLE)
                if bad:
                    raise SystemExit(f"운영과 글·쪽·문서·번호가 다른 id가 있어 멈춤: {bad[:20]} (모두 {len(bad)}개)")
                print({"bundle": BUNDLE, "mismatches": 0})
            else:
                raise SystemExit("사용법: python -m measure.emb_large estimate | store | verify | measure [--out 폴더]")
    elif args[:1] == ["measure"]:
        out = args[2] if args[1:2] == ["--out"] and len(args) == 3 else "emb-stage1" if len(args) == 1 else None
        if out is None:
            raise SystemExit("사용법: python -m measure.emb_large measure [--out 폴더]")
        measure(out)
    else:
        raise SystemExit("사용법: python -m measure.emb_large estimate | store | verify | measure [--out 폴더]")


if __name__ == "__main__":
    main()
