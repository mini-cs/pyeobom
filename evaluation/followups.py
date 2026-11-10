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
TRAP_RULE = ("묻는 정보(가격·전기세 등)를 지어내지 않고 '없다'고 밝히면 정답. 근거 있는 관련 안내를 덧붙이는 건 허용. "
             "묻는 정보를 지어내면 환각. (새 세트에만 적용, 1차 30문항은 그대로)")


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
    retrieved_chunk_ids: list[int] = field(default_factory=list)  # 받은 조각 번호(가이드는 문서 단위 표기라 조각 번호로)
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
            r.retrieved_chunk_ids = resp.get("retrieved_chunk_ids", [])
            r.ms, r.rewrite_ms = resp.get("latency_ms"), resp.get("rewrite_ms")
            history.append({"question": r.question_masked, "answer": r.answer})
        history = history[-MAX_HISTORY:]
        results.append(r)
    return results


RESULT_COLUMNS = ["dialog_id", "turn", "type", "model_id", "question", "question_masked", "expected_rewrite_intent",
                  "rewritten_question", "expected_found", "got_found", "found_ok", "expected_ref", "cited_refs", "retrieved_chunk_ids", "ref_hit",
                  "hallucinated", "rewrite_used", "rewrite_ms", "latency_ms", "error", "answer", "human_rewrite_ok", "human_verdict"]


def score_turn(row: dict, r: TurnResult) -> dict:
    """찾음 여부가 기대와 맞는지, 근거 적중(답 있는 턴), 바꾸기 사용(2번째 턴부터).

    함정(trap)은 found 값으로 채점하지 않는다(새 세트 기준, TRAP_RULE) → 사람 판정(human_verdict: 정답·오답·환각).
    """
    answerable = row["expected_found"] == "true"
    refs = [x for x in row["expected_ref"].split("|") if x]
    trap = row["type"] == "trap"
    ok = None if r.error or trap else (r.found is True) == answerable
    return {
        "found_ok": ok,
        "ref_hit": (any(x in r.cited_refs for x in refs) if answerable and not r.error and not trap else None),
        "hallucinated": (r.found is True if not answerable and not r.error and not trap else None),
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
                "got_found": r.found, "cited_refs": "|".join(r.cited_refs),
                "retrieved_chunk_ids": "|".join(map(str, r.retrieved_chunk_ids)), "rewrite_ms": r.rewrite_ms,
                "latency_ms": r.ms, "error": r.error, "answer": r.answer, "human_rewrite_ok": "", "human_verdict": ""})
    return out


def _ratio(values) -> str:
    values = [v for v in values if v is not None and v != ""]
    return f"{sum(1 for v in values if v in (True, 'O', '정답', 'True'))}/{len(values)}"


def summarize_followups(rows: list[dict]) -> dict:
    """자동 지표(함정 제외)와 사람 판정(바꾸기 정확도·정답, 함정은 TRAP_RULE)을 함께 집계한다."""
    follow = [r for r in rows if r["turn"] != "1"]
    traps = [r for r in rows if r["type"] == "trap"]
    trap = {k: sum(1 for r in traps if r["human_verdict"] == k) for k in ("정답", "오답", "환각")}
    trap["미판정"] = len(traps) - sum(trap.values())
    return {
        "found_ok": _ratio(r["found_ok"] for r in rows if r["type"] != "trap"),
        "ref_hit": _ratio(r["ref_hit"] for r in rows),
        "rewrite_used": _ratio(r["rewrite_used"] for r in follow),
        "human_rewrite_ok": _ratio(r["human_rewrite_ok"] for r in follow),
        "human_verdict": _ratio(r["human_verdict"] for r in rows),
        "trap": trap,
        "hallucinated": sum(1 for r in rows if r.get("hallucinated") is True or r["human_verdict"] == "환각"),
    }
