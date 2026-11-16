"""v1.7 1단계(검색만): 실험 조각 한 벌 만들기·저장·측정. `python -m measure.v17_stage1 estimate|store <한 벌>|measure`

한 벌 이름(코드): strip_800=쪽 표시만 지운 것, docling_800/marker_800=각 도구 800자. 본문·질문 글자는 출력하지 않는다.
"""
import csv
import json
import sys
from collections.abc import Callable
from pathlib import Path

from ingest.page_marker import count_remaining_markers
from ingest.load import ROOT
from measure.v17_bundle import (build_bundle, chunk_plain_800, load_guide_chunks, manual_pages_from_pypdfium2,
                                manual_pages_from_tool, store_bundle)
from measure.v17_gate import DOCS, EXTRACT, _load

OUT = ROOT / "measure" / "out" / "v17"
BUNDLES = {"strip_800": ("pypdfium2", manual_pages_from_pypdfium2), "docling_800": ("docling", manual_pages_from_tool),
           "marker_800": ("marker", manual_pages_from_tool)}
COST_PER_CHAR = 2e-8
SETS = {"dev": "evaluation/paraphrase_dev.csv", "q30": "evaluation/questions.csv"}


def manual_pages(bundle: str, root: Path = EXTRACT) -> dict:
    if bundle not in BUNDLES:
        raise SystemExit(f"모르는 한 벌 이름이라 멈춤: {bundle}")
    tool, fn = BUNDLES[bundle]
    return fn({d: _load(root / tool, d) for d in DOCS})


def guard_cases_path(path: str | Path) -> None:
    if Path(path).name == "paraphrase_test.csv":
        raise SystemExit("확인용 질문은 1단계에서 재지 않아 멈춤")


def measure_sets(cases: dict[str, list[dict]], bundles: list[str | None], embed: Callable, fns: Callable,
                 top_k: int = 5) -> tuple[dict, dict]:
    """fns(한 벌 이름 또는 None) → (검색, 진단). 질문 임베딩은 질문 글자별 1회. (요약, 행)"""
    from measure.search_eval import run_eval
    cache: dict[str, list[float]] = {}

    def cached(q):
        if q not in cache:
            cache[q] = embed(q)
        return cache[q]

    summary: dict = {}
    rows: dict = {}
    for set_name, cs in cases.items():
        for b in bundles:
            search, diag = fns(b)
            r = run_eval(cs, cached, search, diag, top_k=top_k)
            rows[(set_name, b)] = r
            summary.setdefault(set_name, {})[b or "production"] = {
                "hit5": sum(bool(x["rank"] and x["rank"] <= top_k) for x in r), "denominator": len(r),
                "hit5_or_diag": sum(x["hit5_or_diag"] for x in r)}
    return summary, rows


def _conn_guides():
    from app.core.db import get_conn
    with get_conn() as conn:
        return load_guide_chunks(conn)


def estimate() -> None:
    guides = _conn_guides()
    print(f"가이드 조각 {len(guides)}개(DB 읽기만)")
    result = {}
    for name in BUNDLES:
        pages = manual_pages(name)
        chunks = build_bundle(name, pages, chunk_plain_800, guides=guides)
        chars = store_bundle(name, chunks, apply=False)
        left = {d: sum(count_remaining_markers(pp.text, p) for p, pp in pages[d]) for d in DOCS}
        result[name] = {"manual_chunks": len(chunks) - len(guides), "chars": chars, "cost_usd": round(chars * COST_PER_CHAR, 6),
                        "remaining_markers": left, "remaining_total": sum(left.values())}
        print(name, {k: v for k, v in result[name].items() if k != "remaining_markers"})
    (OUT / "stage1-estimate.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


def store(name: str) -> None:
    pages = manual_pages(name)
    chunks = build_bundle(name, pages, chunk_plain_800, guides=_conn_guides())
    embedded = store_bundle(name, chunks, apply=False)
    rows = store_bundle(name, chunks, apply=True)
    print(f"{name}: 넣은 행 {rows}, 임베딩한 글자 {embedded}")


def measure() -> None:
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
    models = {m["id"]: m for m in load_models()}
    deps = get_deps()
    fns = lambda b: (deps.search, deps.diagnostic) if b is None else bundle_fns(b, models, get_conn)
    cases = {k: read_cases(ROOT / p) for k, p in SETS.items()}
    summary, rows = measure_sets(cases, [None, *names], deps.embed_query, fns, top_k=settings.top_k)
    out = OUT / "stage1"
    out.mkdir(parents=True, exist_ok=True)
    for (set_name, b), r in rows.items():
        path = out / f"{set_name}-{b or 'production'}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(r[0]))
            w.writeheader()
            w.writerows(r)
        write_settings(path, settings, f"v17-stage1-{set_name}", experiment={"bundle": b, "set": set_name})
        print(set_name, b or "production", [(x["id"], x["rank"]) for x in r], flush=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    cmd = sys.argv[1:2]
    if cmd == ["estimate"]:
        from ingest.__main__ import load_env
        load_env()
        estimate()
    elif cmd == ["store"] and len(sys.argv) == 3:
        from ingest.__main__ import load_env
        load_env()
        store(sys.argv[2])
    elif cmd == ["measure"]:
        measure()
    else:
        raise SystemExit("사용법: python -m measure.v17_stage1 estimate | store <한 벌> | measure")


if __name__ == "__main__":
    main()
