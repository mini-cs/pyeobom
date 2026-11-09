import csv
from collections import Counter
from pathlib import Path

from evaluation.followups import COLUMNS, TYPES, load_followups, run_dialog

ROOT = Path(__file__).resolve().parents[2]


def _first_questions():
    with open(ROOT / "evaluation" / "questions.csv", encoding="utf-8-sig", newline="") as f:
        return {(r["model_id"], r["question"]): r for r in csv.DictReader(f)}


def test_followups_csv_format():
    rows = load_followups(ROOT / "evaluation" / "followups.csv")
    assert list(rows[0]) == COLUMNS
    assert {r["type"] for r in rows} <= TYPES
    assert {r["expected_found"] for r in rows} <= {"true", "false"}
    dialogs = {}
    for r in rows:
        dialogs.setdefault(r["dialog_id"], []).append(r)
    assert len(dialogs) >= 12
    first = _first_questions()
    for did, turns in dialogs.items():
        assert [int(t["turn"]) for t in turns] == list(range(1, len(turns) + 1)), did
        assert 2 <= len(turns) <= 3, did
        assert len({t["model_id"] for t in turns}) == 1, did
        assert turns[0]["type"] == "base" and (turns[0]["model_id"], turns[0]["question"]) in first, did
        assert all(t["type"] != "base" and t["expected_rewrite_intent"] for t in turns[1:]), did
    counts = Counter(r["type"] for r in rows if r["type"] != "base")
    assert all(counts[t] >= 2 for t in TYPES - {"base"}), counts


def test_followups_csv_has_confirmation_line():
    first_line = (ROOT / "evaluation" / "followups.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert first_line.startswith("# 확정:")


def test_run_dialog_sends_previous_turns_as_history():
    calls = []

    def client(model_id, question, history):
        calls.append((model_id, question, [dict(h) for h in history]))
        n = len(calls)
        return {"found": True, "answer": f"답{n}", "question_masked": f"가린 질문{n}", "rewritten_question": f"바꾼 질문{n}" if n > 1 else None,
                "cited_refs": ["manual:42"], "retrieved_refs": ["manual:42", "manual:43"], "latency_ms": 100 * n, "rewrite_ms": 10 if n > 1 else None}

    turns = [{"dialog_id": "d01", "turn": str(i), "model_id": "washer-a", "question": f"질문{i}"} for i in (1, 2, 3)]
    results = run_dialog(turns, client)
    assert calls[0][2] == []
    assert calls[1][2] == [{"question": "가린 질문1", "answer": "답1"}]
    assert calls[2][2] == [{"question": "가린 질문1", "answer": "답1"}, {"question": "가린 질문2", "answer": "답2"}]
    assert [r.rewritten_question for r in results] == [None, "바꾼 질문2", "바꾼 질문3"]
    assert results[1].found is True and results[1].cited_refs == ["manual:42"] and results[1].ms == 200


def test_run_dialog_keeps_going_after_error():
    def client(model_id, question, history):
        return {"error_code": "AI_TIMEOUT"} if not history else {"found": False, "answer": "", "question_masked": question,
                                                                  "rewritten_question": None, "cited_refs": [], "latency_ms": 5}

    turns = [{"dialog_id": "d02", "turn": "1", "model_id": "washer-a", "question": "질문1"},
             {"dialog_id": "d02", "turn": "2", "model_id": "washer-a", "question": "질문2"}]
    results = run_dialog(turns, client)
    assert results[0].error == "AI_TIMEOUT" and results[1].error == ""


def test_score_turn_checks_found_ref_and_rewrite():
    from evaluation.followups import TurnResult, score_turn
    row = {"dialog_id": "d01", "turn": "2", "type": "pronoun", "expected_found": "true", "expected_ref": "manual:42"}
    ok = score_turn(row, TurnResult("d01", 2, rewritten_question="세탁조 청소는 얼마나 자주 해요?", found=True, cited_refs=["manual:42"]))
    assert (ok["found_ok"], ok["ref_hit"], ok["hallucinated"], ok["rewrite_used"]) == (True, True, None, True)
    trap = {"dialog_id": "d07", "turn": "2", "type": "trap", "expected_found": "false", "expected_ref": ""}
    bad = score_turn(trap, TurnResult("d07", 2, found=True, cited_refs=["manual:56"]))
    # 함정은 found 값으로 채점하지 않는다(새 세트 기준: 지어내지 않고 '없다'고 밝히면 정답, 관련 안내 덧붙임 허용) → 사람 판정
    assert (bad["found_ok"], bad["ref_hit"], bad["hallucinated"], bad["rewrite_used"]) == (None, None, None, False)
    base = score_turn({"dialog_id": "d01", "turn": "1", "type": "base", "expected_found": "true", "expected_ref": "manual:42"},
                      TurnResult("d01", 1, found=True, cited_refs=["manual:43"]))
    assert base["rewrite_used"] is None and base["ref_hit"] is False


def test_summarize_followups_counts_traps_by_human_verdict():
    from evaluation.followups import summarize_followups
    rows = [
        {"turn": "1", "type": "base", "found_ok": True, "ref_hit": True, "rewrite_used": None, "human_rewrite_ok": "", "human_verdict": "정답"},
        {"turn": "2", "type": "pronoun", "found_ok": True, "ref_hit": False, "rewrite_used": True, "human_rewrite_ok": "O", "human_verdict": "정답"},
        {"turn": "2", "type": "trap", "found_ok": None, "ref_hit": None, "rewrite_used": True, "human_rewrite_ok": "O", "human_verdict": "정답"},
        {"turn": "3", "type": "trap", "found_ok": None, "ref_hit": None, "rewrite_used": False, "human_rewrite_ok": "X", "human_verdict": "환각"},
    ]
    s = summarize_followups(rows)
    assert s["found_ok"] == "2/2" and s["ref_hit"] == "1/2"
    assert s["rewrite_used"] == "2/3" and s["human_rewrite_ok"] == "2/3"
    assert s["trap"] == {"정답": 1, "오답": 0, "환각": 1, "미판정": 0}
    assert s["human_verdict"] == "3/4" and s["hallucinated"] == 1
