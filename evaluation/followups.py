"""이어지는 질문 평가(계획 2 Task 5): followups.csv의 대화를 차례로 보내고 턴별로 채점한다.

- 앞 턴의 가린 질문(question_masked)과 답을 history로 붙인다(화면과 같은 방식, 최근 3개).
- 자동 채점은 찾음 여부·근거 적중만 본다. 바꾸기 정확도(human_rewrite_ok)와 답의 정답(human_verdict)은 사람이 판정한다.
"""
import csv
from dataclasses import dataclass, field
from pathlib import Path

COLUMNS = ["dialog_id", "turn", "model_id", "question", "expected_rewrite_intent", "expected_found", "expected_ref", "type"]
TYPES = {"base", "pronoun", "ellipsis", "topic_switch", "trap", "pii"}  # base = 대화의 1번째 질문(1차 30문항)
MAX_HISTORY = 3


@dataclass
class TurnResult:
    dialog_id: str
    turn: int
    question_masked: str = ""
    rewritten_question: str | None = None
    found: bool | None = None
    answer: str = ""
    cited_refs: list[str] = field(default_factory=list)
    retrieved_refs: list[str] = field(default_factory=list)
    ms: int | None = None
    rewrite_ms: int | None = None
    error: str = ""


def load_followups(path: str | Path) -> list[dict]:
    # 첫 줄(# 확정: …)처럼 #로 시작하는 줄은 건너뛴다
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def run_dialog(turns: list[dict], client) -> list[TurnResult]:
    """client(model_id, question, history) -> 응답 dict(debug). 오류 턴도 기록하고 다음 턴으로 넘어간다."""
    history, results = [], []
    for t in turns:
        resp = client(t["model_id"], t["question"], list(history))
        r = TurnResult(t["dialog_id"], int(t["turn"]))
        if "error_code" in resp:
            r.error = resp["error_code"]
            history.append({"question": t["question"], "answer": ""})
        else:
            r.question_masked, r.rewritten_question = resp.get("question_masked", ""), resp.get("rewritten_question")
            r.found, r.answer = resp.get("found"), resp.get("answer", "")
            r.cited_refs, r.retrieved_refs = resp.get("cited_refs", []), resp.get("retrieved_refs", [])
            r.ms, r.rewrite_ms = resp.get("latency_ms"), resp.get("rewrite_ms")
            history.append({"question": r.question_masked, "answer": r.answer})
        history = history[-MAX_HISTORY:]
        results.append(r)
    return results


RESULT_COLUMNS = ["dialog_id", "turn", "type", "model_id", "question", "question_masked", "expected_rewrite_intent",
                  "rewritten_question", "expected_found", "got_found", "found_ok", "expected_ref", "cited_refs", "ref_hit",
                  "hallucinated", "rewrite_used", "rewrite_ms", "latency_ms", "error", "answer", "human_rewrite_ok", "human_verdict"]


def score_turn(row: dict, r: TurnResult) -> dict:
    """찾음 여부가 기대와 맞는지, 근거 적중(답 있는 턴), 환각(답 없는 턴), 바꾸기 사용(2번째 턴부터)."""
    answerable = row["expected_found"] == "true"
    refs = [x for x in row["expected_ref"].split("|") if x]
    ok = None if r.error else (r.found is True) == answerable
    return {
        "found_ok": ok,
        "ref_hit": (any(x in r.cited_refs for x in refs) if answerable and not r.error else None),
        "hallucinated": (r.found is True if not answerable and not r.error else None),
        "rewrite_used": None if row["turn"] == "1" else r.rewritten_question is not None,
    }


def run_all(rows: list[dict], client) -> list[dict]:
    """대화별로 run_dialog를 돌려 결과 CSV 행(사람 판정 칸 비움)을 만든다."""
    dialogs: dict[str, list[dict]] = {}
    for row in rows:
        dialogs.setdefault(row["dialog_id"], []).append(row)
    out = []
    for turns in dialogs.values():
        for row, r in zip(turns, run_dialog(turns, client)):
            out.append({k: row.get(k, "") for k in RESULT_COLUMNS} | score_turn(row, r) | {
                "question_masked": r.question_masked, "rewritten_question": r.rewritten_question or "",
                "got_found": r.found, "cited_refs": "|".join(r.cited_refs), "rewrite_ms": r.rewrite_ms,
                "latency_ms": r.ms, "error": r.error, "answer": r.answer, "human_rewrite_ok": "", "human_verdict": ""})
    return out
