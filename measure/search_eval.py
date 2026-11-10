"""검색 실험 도구(작업 B): 답변 AI 없이 검색만 돌려 정답 조각 순위·적중률·평균 역순위를 잰다.

사용법: python -m measure.search_eval <질문 CSV> --label <이름>
- CSV 열: id, model_id, question, expected_ref(여러 개면 |로). # 로 시작하는 줄은 건너뛴다. 기대 근거가 없는 행(함정)은 집계에서 뺀다
- 운영과 같은 개인정보 가리기 → (질문 변형 함수, 기본은 그대로) → 임베딩 → 모델 필터 검색 상위 20개 → 진단 규칙(needs_diagnostic)
- 적중률은 정답 조각이 1·3·5위 안에 있는 비율, 평균 역순위는 1/순위의 평균(20위 밖은 0). hit5_or_diag는 5위 안 또는 진단 안내 쪽으로 답변 AI에 넘어가는지
- 비용은 임베딩뿐. 결과(근거 표기만, 조각 본문 없음)는 measure/out/에 둔다
"""
import argparse
import csv
import datetime
from collections.abc import Callable
from pathlib import Path

from app.input_guard.pii import mask_pii
from app.retrieval.search import needs_diagnostic
from measure.retrieval_probe import expected_rank

OUT = Path(__file__).resolve().parent / "out"
DEPTH, TOP_K = 20, 5


def read_cases(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    hit = lambda k: round(sum(1 for r in ranks if r and r <= k) / n, 4) if n else 0.0
    return {"n": n, "hit@1": hit(1), "hit@3": hit(3), "hit@5": hit(5),
            "mrr": sum(1 / r for r in ranks if r) / n if n else 0.0}


def run_eval(cases: list[dict], embed: Callable, search: Callable, diagnostic: Callable,
             transform: Callable[[str, str], str] | None = None, top_k: int = TOP_K) -> list[dict]:
    """transform(가린 질문, model_id) → 검색에 쓸 질문. 검색 개선 실험(M3 등)이 끼울 자리"""
    rows = []
    for c in cases:
        refs = [r for r in c["expected_ref"].split("|") if r]
        if not refs:
            continue
        query = mask_pii(c["question"])[0]
        if transform:
            query = transform(query, c["model_id"])
        chunks = search(c["model_id"], embed(query), query, DEPTH)
        top = chunks[:top_k]
        diag = [d.ref for d in diagnostic(c["model_id"]) if d.id not in {x.id for x in top}] if needs_diagnostic(query, top) else []
        rank = expected_rank(chunks, refs)
        rows.append({"id": c["id"], "model_id": c["model_id"], "expected_ref": c["expected_ref"], "rank": rank,
                     "top5": "|".join(x.ref for x in top), "diag": "|".join(diag),
                     "hit5_or_diag": bool(rank and rank <= top_k) or any(r in diag for r in refs)})
    return rows


METHODS = {"m0": "운영 검색", "m1": "실험 색인 m1_title(조각에 제목 붙이기)", "m2": "실험 색인 m2_question(조각마다 질문, max 규칙)",
           "m3": "용어 사전으로 질문 넓히기(measure/m3_terms.json, expand_query)"}


def method_fns(method: str, base_search: Callable, variant_search: Callable, terms: dict) -> tuple[Callable, Callable | None]:
    """방법별 (검색, 질문 변형). M1·M2는 실험 색인으로 검색, M3는 운영 검색 + 질문 넓히기"""
    from measure.search_variants import expand_query
    if method in ("m1", "m2"):
        variant = {"m1": "m1_title", "m2": "m2_question"}[method]
        return (lambda m, v, t, k: variant_search(m, v, t, k, variant)), None
    if method == "m3":
        return base_search, lambda q, model_id: expand_query(q, terms.get(model_id, {}))
    return base_search, None


def rank_changes(base_rows: list[dict], rows: list[dict]) -> dict[str, str]:
    from measure.retrieval_probe import compare
    base = {r["id"]: r["rank"] for r in base_rows}
    return {r["id"]: compare(r["rank"], base[r["id"]]) for r in rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--label", required=True)
    ap.add_argument("--method", choices=list(METHODS), default="m0")
    args = ap.parse_args()

    from ingest.__main__ import load_env
    load_env()
    from app.ask.routes import get_deps
    from app.core.config import get_settings
    from evaluation.run_config import warn_if_different, write_settings

    settings = get_settings()
    if warn_if_different(settings):
        raise SystemExit("운영 기본값과 다른 설정이라 멈춤")
    from app.core.db import get_conn
    from app.retrieval.search import search_vector
    from measure.search_variants import load_terms

    deps = get_deps()

    def variant_search(model_id, vec, text, k, variant):
        with get_conn() as conn:
            return search_vector(conn, model_id, vec, k, variant=variant)

    search, transform = method_fns(args.method, deps.search, variant_search, load_terms() if args.method == "m3" else {})
    rows = run_eval(read_cases(args.cases), deps.embed_query, search, deps.diagnostic, transform=transform, top_k=settings.top_k)
    summary = metrics([r["rank"] for r in rows]) | {
        "hit5_or_diag": round(sum(r["hit5_or_diag"] for r in rows) / len(rows), 4) if rows else 0.0}
    OUT.mkdir(exist_ok=True)
    out = OUT / f"search-eval-{args.label}-{datetime.date.today().isoformat()}.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_settings(out, settings, f"search-eval-{args.label}",
                   experiment=None if args.method == "m0" else {"method": args.method, "desc": METHODS[args.method]})
    for r in rows:
        print(r["id"], r["rank"], r["top5"], r["diag"] or "-", flush=True)
    print(summary, "csv:", out.name)


if __name__ == "__main__":
    main()
