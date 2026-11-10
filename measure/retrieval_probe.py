"""근거 관련성 원인 조사 Task 2: 답변 AI 없이 검색만 돌려 질문 형태(① 바꾼 질문, ② 사람이 쓴 짧은 질문, ③ 원래 질문)별 정답 조각 순위를 비교한다.

사용법: python -m measure.retrieval_probe   (measure/cr_queries.csv, evaluation/followups.csv를 읽음)
- 운영과 같은 개인정보 가리기 → 임베딩 → 모델 필터 벡터 검색(상위 20개). 진단 안내 규칙(v2a)으로 덧붙는 쪽은 따로 표시
- 비용은 임베딩뿐. 결과(근거 표기만, 조각 본문 없음)는 measure/out/에 둔다
"""
import csv
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "out"
DEPTH = 20


def expected_rank(results: list, expected_refs: list[str], depth: int = DEPTH) -> int | None:
    """정답 조각이 상위 몇 위인지(1부터). 기대 근거(manual:쪽·guide:문서·chunk:조각 번호)가 여러 개면 가장 높은 순위, depth 밖이면 None."""
    for i, chunk in enumerate(results[:depth], 1):
        if chunk.ref in expected_refs or f"chunk:{getattr(chunk, 'id', None)}" in expected_refs:  # 가이드 조각은 chunk:<id>로 지정
            return i
    return None


def compare(a: int | None, b: int | None) -> str:
    """a가 b보다 순위가 좋으면 better. None(20위 밖)은 어떤 순위보다 나쁘다."""
    a_, b_ = a or DEPTH + 1, b or DEPTH + 1
    return "better" if a_ < b_ else "worse" if a_ > b_ else "same"


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def main() -> None:
    from ingest.__main__ import load_env
    load_env()
    from app.ask.routes import get_deps
    from app.core.config import get_settings
    from app.input_guard.pii import mask_pii
    from app.retrieval.search import contains_code, extract_code_tokens
    from evaluation.run_config import warn_if_different, write_settings

    settings = get_settings()
    if warn_if_different(settings):
        raise SystemExit("운영 기본값과 다른 설정이라 멈춤")
    expected = {f"{r['dialog_id']}-{r['turn']}": r["expected_ref"] for r in _read(ROOT / "evaluation" / "followups.csv")}
    deps, rows = get_deps(), []
    for q in _read(ROOT / "measure" / "cr_queries.csv"):
        refs = [x for x in expected[q["id"]].split("|") if x]
        row = {"id": q["id"], "type": q["type"], "term_changed": q["term_changed"], "expected_ref": expected[q["id"]]}
        for name, text in (("q1", q["q1_rewritten"] or q["q3_original"]), ("q2", q["q2_human"]), ("q3", q["q3_original"])):
            masked = mask_pii(text)[0]  # 운영과 같은 가리기 뒤 검색
            chunks = deps.search(q["model_id"], deps.embed_query(masked), masked, DEPTH)
            top5 = chunks[:settings.top_k]
            tokens = extract_code_tokens(masked)
            diag = []
            if tokens and not all(any(contains_code(t, c.content) for c in top5) for t in tokens):
                diag = [c.ref for c in deps.diagnostic(q["model_id"]) if c.id not in {x.id for x in top5}]
            row |= {f"{name}_rank": expected_rank(chunks, refs) if refs else None,
                    f"{name}_top5": "|".join(c.ref for c in top5), f"{name}_diag": "|".join(diag)}
        rows.append(row)
        print(row["id"], {k: row[k] for k in ("q1_rank", "q2_rank", "q3_rank")}, flush=True)
    OUT.mkdir(exist_ok=True)
    out = OUT / f"retrieval-probe-{datetime.date.today().isoformat()}.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_settings(out, settings, "retrieval-probe")
    print("csv:", out.name)


if __name__ == "__main__":
    main()
