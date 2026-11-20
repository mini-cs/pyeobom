"""v1.7 1단계(검색만): 실험 조각 한 벌 만들기·저장·측정. `python -m measure.v17_stage1 estimate|store <한 벌>|measure`

한 벌 이름(코드): strip_800=쪽 표시만 지운 것, docling_800/marker_800=각 도구 800자, docling_sections=Docling 소제목(Task 8).
`measure [--out 폴더] [한 벌 ...]`: 한 벌을 주면 운영 그대로와 그 한 벌들만 잰다. 본문·질문 글자는 출력하지 않는다.
"""
import csv
import json
import sys
from collections.abc import Callable
from pathlib import Path

from ingest.page_marker import count_remaining_markers
from ingest.section_chunk import chunk_sections
from ingest.load import ROOT
from measure.v17_bundle import (build_bundle, chunk_plain_800, load_guide_chunks, manual_pages_from_pypdfium2,
                                manual_pages_from_tool, store_bundle)
from measure.fable_split import fable_pages
from measure.v17_gate import DOCS, EXTRACT, _load

OUT = ROOT / "measure" / "out" / "v17"
BUNDLES = {"strip_800": ("pypdfium2", manual_pages_from_pypdfium2, chunk_plain_800),
           "docling_800": ("docling", manual_pages_from_tool, chunk_plain_800),
           "marker_800": ("marker", manual_pages_from_tool, chunk_plain_800),
           "docling_sections": ("docling", manual_pages_from_tool, chunk_sections),  # 순서는 Docling 800자와 같고 자르기만 소제목
           # Fable 분할(계획 2026-11-20 Task 2): 운영과 같은 글에 Fable이 정한 자를 위치를 붙여 소제목 자르기와 같은 규칙으로
           "fable_lines": ("pypdfium2", fable_pages("fable_lines"), chunk_sections),
           "fable_pdf": ("pypdfium2", fable_pages("fable_pdf"), chunk_sections)}
COST_PER_CHAR = 2e-8
SETS = {"dev": "evaluation/paraphrase_dev.csv", "q30": "evaluation/questions.csv"}


def manual_pages(bundle: str, root: Path = EXTRACT) -> dict:
    if bundle not in BUNDLES:
        raise SystemExit(f"모르는 한 벌 이름이라 멈춤: {bundle}")
    tool, fn, _ = BUNDLES[bundle]
    return fn({d: _load(root / tool, d) for d in DOCS})


def parse_measure_args(args: list[str]) -> tuple[list[str] | None, str]:
    """(잴 한 벌 목록 또는 None=저장된 전부, 결과 폴더 이름)"""
    out, names = "stage1", []
    it = iter(args)
    for a in it:
        if a == "--out":
            out = next(it, "")
            if not out:
                raise SystemExit("--out 뒤에 폴더 이름이 없어 멈춤")
        elif a in BUNDLES:
            names.append(a)
        else:
            raise SystemExit(f"모르는 한 벌 이름이라 멈춤: {a}")
    return (names or None), out


def guard_cases_path(path: str | Path) -> None:
    if Path(path).name == "paraphrase_test.csv":
        raise SystemExit("확인용 질문은 1단계에서 재지 않아 멈춤")


def measure_sets(cases: dict[str, list[dict]], bundles: list[str | None], embed: Callable, fns: Callable,
                 top_k: int = 5, *, embed_for: Callable | None = None, depth: int = 20) -> tuple[dict, dict]:
    """fns(한 벌 이름 또는 None) → (검색, 진단). embed_for(벌, embed) → 그 벌의 질문 임베딩 함수(v1.9, 없으면 모두 embed).
    질문 임베딩은 (임베딩 함수, 질문 글자)마다 1회. (요약, 행)"""
    from measure.search_eval import run_eval
    cache: dict[tuple, list[float]] = {}

    def cached_with(fn):
        def cached(q):
            if (fn, q) not in cache:
                cache[(fn, q)] = fn(q)
            return cache[(fn, q)]
        return cached

    summary: dict = {}
    rows: dict = {}
    for set_name, cs in cases.items():
        for b in bundles:
            search, diag = fns(b)
            r = run_eval(cs, cached_with(embed_for(b, embed) if embed_for else embed), search, diag, top_k=top_k, depth=depth)
            rows[(set_name, b)] = r
            summary.setdefault(set_name, {})[b or "production"] = {
                "hit5": sum(bool(x["rank"] and x["rank"] <= top_k) for x in r), "denominator": len(r),
                "hit5_or_diag": sum(x["hit5_or_diag"] for x in r)}
    return summary, rows


def _conn_guides():
    from app.core.db import get_conn
    with get_conn() as conn:
        return load_guide_chunks(conn)


def estimate(names: list[str] | None = None) -> None:
    guides = _conn_guides()
    print(f"가이드 조각 {len(guides)}개(DB 읽기만)")
    result = {}
    for name in names or BUNDLES:
        pages = manual_pages(name)
        chunks = build_bundle(name, pages, BUNDLES[name][2], guides=guides)
        chars = store_bundle(name, chunks, apply=False)
        left = {d: sum(count_remaining_markers(pp.text, p) for p, pp in pages[d]) for d in DOCS}
        result[name] = {"manual_chunks": len(chunks) - len(guides), "chars": chars, "cost_usd": round(chars * COST_PER_CHAR, 6),
                        "remaining_markers": left, "remaining_total": sum(left.values())}
        print(name, {k: v for k, v in result[name].items() if k != "remaining_markers"})
    (OUT / f"estimate-{'-'.join(names) if names else 'all'}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


def store(name: str) -> None:
    pages = manual_pages(name)
    chunks = build_bundle(name, pages, BUNDLES[name][2], guides=_conn_guides())
    embedded = store_bundle(name, chunks, apply=False)
    rows = store_bundle(name, chunks, apply=True)
    print(f"{name}: 넣은 행 {rows}, 임베딩한 글자 {embedded}")


def measure(only: list[str] | None = None, out_name: str = "stage1") -> None:
    from ingest.__main__ import load_env
    load_env()
    from app.ask.routes import get_deps
    from app.catalog.registry import load_models
    from app.core.config import get_settings
    from app.core.db import get_conn
    from evaluation.run_config import warn_if_different, write_settings
    from measure.search_eval import bundle_fns, read_cases

    settings = get_settings()
    if warn_if_different(settings):
        raise SystemExit("운영 기본값과 다른 설정이라 멈춤")
    if settings.search_mode != "vector":
        raise SystemExit("벡터 검색(search_mode=vector)에서만 써서 멈춤")
    for p in SETS.values():
        guard_cases_path(p)
    with get_conn() as conn:
        names = [r[0] for r in conn.execute("SELECT DISTINCT bundle FROM bundle_chunks ORDER BY bundle").fetchall()]
    if only:
        missing = [n for n in only if n not in names]
        if missing:
            raise SystemExit(f"저장되지 않은 한 벌이라 멈춤: {missing}")
        names = only
    models = {m["id"]: m for m in load_models()}
    deps = get_deps()
    fns = lambda b: (deps.search, deps.diagnostic) if b is None else bundle_fns(b, models, get_conn)
    cases = {k: read_cases(ROOT / p) for k, p in SETS.items()}
    from measure.emb_large import embed_for  # 다시 임베딩한 벌(v1.9)이 섞여도 그 벌의 모델로 질문을 임베딩
    summary, rows = measure_sets(cases, [None, *names], deps.embed_query, fns, top_k=settings.top_k, embed_for=embed_for)
    out = OUT / out_name
    out.mkdir(parents=True, exist_ok=True)
    for (set_name, b), r in rows.items():
        path = out / f"{set_name}-{b or 'production'}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(r[0]))
            w.writeheader()
            w.writerows(r)
        write_settings(path, settings, f"v17-{out_name}-{set_name}", experiment={"bundle": b, "set": set_name})
        print(set_name, b or "production", [(x["id"], x["rank"]) for x in r], flush=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    cmd = sys.argv[1:2]
    if cmd == ["estimate"]:
        from ingest.__main__ import load_env
        load_env()
        estimate(parse_measure_args(sys.argv[2:])[0])
    elif cmd == ["store"] and len(sys.argv) == 3:
        from ingest.__main__ import load_env
        load_env()
        store(sys.argv[2])
    elif cmd == ["measure"]:
        measure(*parse_measure_args(sys.argv[2:]))
    else:
        raise SystemExit("사용법: python -m measure.v17_stage1 estimate [한 벌 ...] | store <한 벌> | measure [--out 폴더] [한 벌 ...]")


if __name__ == "__main__":
    main()
