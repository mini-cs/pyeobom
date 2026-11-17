import random

from measure.v17_blind4 import build_sheet

Q = lambda i, a, t="usage": {"id": i, "type": t, "question": f"질문{i}", "expected_ref": "manual:1", "answer": a}
F = lambda d, n, q, a, t="base": {"dialog_id": d, "turn": str(n), "type": t, "question": q, "expected_ref": "manual:2", "answer": a}


def _runs():
    q30 = {"v17-s4-m0-r1": [Q("q01", "A"), Q("q02", "없음", "trap_none")],
           "v17-s4-strip-r1": [Q("q01", "A"), Q("q02", "다름", "trap_none")]}
    fu = {"v17-s4fu-m0-r1": [F("d01", 1, "첫 질문", "답1"), F("d01", 2, "그거 다시", "답2")],
          "v17-s4fu-strip-r1": [F("d01", 1, "첫 질문", "다른답1"), F("d01", 2, "그거 다시", "답2")]}
    return q30, fu


def test_sheet_sections_and_grouping():
    q30, fu = _runs()
    text, key = build_sheet(q30, fu, random.Random(3), label="v17-s4")
    assert "## 30문항" in text and "## 이어지는 질문" in text
    assert text.count("**답 ") == 2 + 2 + 2  # q01 묶음 1 + q02 2 / d01-1 2 / d01-2는 앞 대화가 달라 2
    assert "### q02 (함정)" in text and "- 기대 근거:" in text
    assert "m0" not in text and "strip" not in text and "r1" not in text
    assert "함정이 아닌 문항의 '찾지 못함'은 오답" in text


def test_followup_history_line_uses_same_number():
    q30, fu = _runs()
    text, key = build_sheet(q30, fu, random.Random(3), label="v17-s4")
    lines = text.splitlines()
    hist = [i for i, l in enumerate(lines) if l.startswith("- 앞 대화(답 ")]
    assert len(hist) == 2  # 2턴 답 두 개에만, 1턴에는 없음
    for i in hist:
        n = lines[i].split("(답 ")[1].split(")")[0]
        assert lines[i + 1].startswith(f"- **답 {n}**: ")
        assert "1턴 질문 첫 질문 → 1턴 답 " in lines[i]
    assert all(l.endswith("→ 판정: ") for l in lines if l.startswith("- **답 "))


def test_key_covers_every_answer_and_numbers_unique():
    q30, fu = _runs()
    text, key = build_sheet(q30, fu, random.Random(3), label="v17-s4")
    assert len(key) == 8  # 2문항 × 2 + 2턴 × 2
    assert {k["run"] for k in key} == set(q30) | set(fu)
    nums = [int(l.split("**답 ")[1].split("**")[0]) for l in text.splitlines() if l.startswith("- **답 ")]
    assert len(nums) == len(set(nums)) and {k["no"] for k in key} == set(nums)
    m0 = [k for k in key if k["item"] == "q01"]
    assert len({k["no"] for k in m0}) == 1  # 같은 답은 같은 번호
