"""python -m evaluation --label v1 --prompt v1 --search vector

questions.csv 30개를 answer_question(debug=True)으로 직접 돌려(HTTP 아님) 채점한다.
결과: evaluation/results/<label>-<날짜>.csv(사람 판정용 human_verdict 열), docs/평가/<날짜>-<label>.md(요약 + 문항별 표).
로컬 .env의 접속 주소·키를 쓰지만 출력하지 않는다. 조회만 하고 DB를 바꾸지 않는다.
"""
import argparse
import os
import csv
import json
import datetime
from dataclasses import replace
from pathlib import Path

from ingest.__main__ import load_env

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["id", "type", "model_id", "question", "expected_found", "got_found", "correct", "ref_hit", "hallucinated",
           "error", "latency_ms", "failure", "expected_ref", "cited_refs", "retrieved_refs", "retrieved_chunk_ids", "answer",
           "human_verdict"]


def _mark(v) -> str:
    return "" if v is None else ("O" if v is True else "X" if v is False else str(v))


def write_report(path: Path, label: str, args, summary: dict, rows: list[dict], diffs: list[str] | None = None) -> None:
    lines = [
        f"# 평가 리포트 {label} ({datetime.date.today()})", "",
        f"- 실행: `python -m evaluation --label {args.label} --prompt {args.prompt} --search {args.search}`",
        "- 문항: `evaluation/questions.csv` 30개 (2026-10-28 고정)",
        f"- 실행 설정: 결과 CSV 옆 `.settings.json`. " + ("**⚠ 운영 기본값과 다름: " + ", ".join(diffs) + "**" if diffs else "운영 기본값과 같음"), "",
        "## 요약", "",
        "| 정답률 | 근거 적중률 | 환각률 | 오류율 | 응답 시간 평균 | 최대 | 실패: 검색 | 실패: 답변 |",
        "|---|---|---|---|---|---|---|---|",
        f"| {summary['accuracy']}% | {summary['ref_hit_rate']}% | {summary['hallucination_rate']}% | {summary['error_rate']}% "
        f"| {summary['latency_avg_ms']}ms | {summary['latency_max_ms']}ms | {summary['failures']['retrieval']} | {summary['failures']['answer']} |",
        "", "- 정답률·근거 적중률은 답 있는 문항, 환각률은 함정 문항, 오류율은 전체가 분모다.", "",
        "## 문항별", "",
        "| id | 유형 | 기대 | 결과 | 정답 | 근거 적중 | 환각 | 실패 | 기대 근거 | 실제 인용 | ms |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['id']} | {r['type']} | {r['expected_found']} | {_mark(r['got_found']) if not r['error'] else '오류'} "
                     f"| {_mark(r['correct'])} | {_mark(r['ref_hit'])} | {_mark(r['hallucinated'])} | {r['failure'] or ''} "
                     f"| {r['expected_ref']} | {r['cited_refs']} | {r['latency_ms'] or ''} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_followups(args, settings, get_deps, answer_question, AppError, write_settings) -> None:
    from evaluation.followups import RESULT_COLUMNS, load_followups, run_all, summarize_followups

    from evaluation.contexts import capture_contexts
    captured: list[list[str]] = []  # 턴 순서대로(run_all이 대화·턴 순서로 부름)

    def client(model_id, question, history):
        deps = get_deps()
        if args.save_contexts:
            captured.append([])
            deps = capture_contexts(deps, captured[-1])
        try:
            return answer_question(model_id, question, deps, settings, debug=True, history=history)
        except AppError as e:
            return {"error_code": e.code}

    rows = run_all(load_followups(ROOT / "evaluation" / "followups.csv"), client)
    out_csv = ROOT / "evaluation" / "results" / f"{args.label}-{datetime.date.today().isoformat()}.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    write_settings(out_csv, settings, args.label)
    if args.save_contexts:  # DeepEval용 근거 본문(설명서 원문, 커밋 금지: .gitignore *-contexts.json)
        contexts = {f"{r['dialog_id']}-{r['turn']}": c for r, c in zip(rows, captured)}
        (out_csv.parent / f"{args.label}-contexts.json").write_text(json.dumps(contexts, ensure_ascii=False), encoding="utf-8")
    # 사람 판정 칸은 비어 있으므로 여기서는 자동 지표만 의미가 있다(함정은 사람 판정 후 다시 집계)
    print(summarize_followups(rows) | {"turns": len(rows), "errors": sum(1 for r in rows if r["error"]), "csv": out_csv.name})


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evaluation")
    parser.add_argument("--label", required=True)
    parser.add_argument("--prompt", default="v1")
    parser.add_argument("--search", default="vector", choices=["vector", "hybrid"])
    parser.add_argument("--save-contexts", action="store_true",
                        help="AI에 넘긴 조각 본문을 evaluation/results/<label>-contexts.json에 저장(DeepEval용, 커밋 금지)")
    parser.add_argument("--followups", action="store_true", help="이어지는 질문 세트(evaluation/followups.csv)를 대화별로 실행")
    args = parser.parse_args()

    load_env()
    os.environ["SEARCH_MODE"] = args.search  # get_deps가 설정에서 검색 방식을 읽는다
    from app.ask.routes import get_deps  # load_env 뒤에 설정을 읽게 한다
    from app.ask.service import answer_question
    from app.core.config import get_settings
    from app.core.errors import AppError
    from evaluation.contexts import capture_contexts
    from evaluation.scoring import score_case, summarize

    settings = replace(get_settings(), prompt_version=args.prompt, search_mode=args.search)
    from evaluation.run_config import warn_if_different, write_settings
    diffs = warn_if_different(settings)  # 로컬 .env 실험 설정이 섞이면 시작할 때 알린다
    if args.followups:
        return _run_followups(args, settings, get_deps, answer_question, AppError, write_settings)
    with (ROOT / "evaluation" / "questions.csv").open(encoding="utf-8-sig", newline="") as f:
        cases = list(csv.DictReader(f))

    rows, scores, contexts = [], [], {}
    for case in cases:
        deps = get_deps()
        if args.save_contexts:
            contexts[case["id"]] = []
            deps = capture_contexts(deps, contexts[case["id"]])
        try:
            resp = answer_question(case["model_id"], case["question"], deps, settings, debug=True)
        except AppError as e:
            resp = {"error_code": e.code}
        score = score_case(case, resp)
        scores.append(score)
        rows.append(score | {"model_id": case["model_id"], "question": case["question"], "expected_ref": case["expected_ref"],
                             "cited_refs": "|".join(resp.get("cited_refs", [])),
                             "retrieved_refs": "|".join(resp.get("retrieved_refs", [])),
                             "retrieved_chunk_ids": "|".join(map(str, resp.get("retrieved_chunk_ids", []))),
                             "answer": resp.get("answer", resp.get("error_code", ""))})
        print(f"{case['id']} {score['type']:16s} 정답={_mark(score['correct'])} 근거={_mark(score['ref_hit'])} "
              f"환각={_mark(score['hallucinated'])} 실패={score['failure'] or ''} {'오류' if score['error'] else score['latency_ms']}ms", flush=True)

    today = datetime.date.today().isoformat()
    out_csv = ROOT / "evaluation" / "results" / f"{args.label}-{today}.csv"
    out_csv.parent.mkdir(exist_ok=True)
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:  # 엑셀에서 한글이 깨지지 않게 BOM
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    write_settings(out_csv, settings, args.label)
    if args.save_contexts:
        (out_csv.parent / f"{args.label}-contexts.json").write_text(json.dumps(contexts, ensure_ascii=False), encoding="utf-8")
    summary = summarize(scores)
    write_report(ROOT / "docs" / "평가" / f"{today}-{args.label}.md", args.label, args, summary, rows, diffs)
    print(summary)


if __name__ == "__main__":
    main()
