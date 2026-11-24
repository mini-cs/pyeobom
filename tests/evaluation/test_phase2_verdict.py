"""2차 확인 질문 세트 규칙과 합격 판정(설계 9.3-7·8, 계획 Global 6)."""
from evaluation.phase2_verdict import VERDICTS, passes, validate_confirm_set

PAGES = 30  # 앞 1~10, 중간 11~20, 뒤 21~30


def usage(qid, page, source="manual"):
    return {"qid": qid, "kind": "사용법", "question": f"가짜 질문 {qid}", "expected_pages": str(page), "source": source}


def error(qid, page, source="guide:guide-test"):
    return {"qid": qid, "kind": "에러 코드", "question": f"가짜 에러 {qid}", "expected_pages": str(page), "source": source}


def good_set():
    pages = [2, 5, 9, 12, 15, 19, 23, 28]
    return [usage(f"q{i + 1}", p) for i, p in enumerate(pages)] + [error("q9", 3), error("q10", 4)]


def test_confirm_set_rules():
    assert validate_confirm_set(good_set(), PAGES) == []
    # 에러 코드가 없으면 사용법 10개
    ten = [usage(f"q{i + 1}", p) for i, p in enumerate([1, 4, 8, 11, 14, 17, 20, 22, 26, 30])]
    assert validate_confirm_set(ten, PAGES) == []
    # 10개가 아님
    assert validate_confirm_set(good_set()[:9], PAGES)
    # 에러 코드가 0·2개가 아님
    one_error = good_set()[:9] + [usage("q10", 29)]
    assert validate_confirm_set(one_error, PAGES)
    # 뒤 1/3에 사용법이 1개뿐
    skewed = good_set()
    skewed[6] = usage("q7", 13)
    assert validate_confirm_set(skewed, PAGES)
    # expected_pages가 빔
    empty = good_set()
    empty[0]["expected_pages"] = ""
    assert validate_confirm_set(empty, PAGES)


def test_confirm_set_accepts_several_pages_and_rejects_bad_fields():
    rows = good_set()
    rows[0]["expected_pages"] = "2;3"
    assert validate_confirm_set(rows, PAGES) == []
    for field, value in [("kind", "함정"), ("source", "web"), ("expected_pages", "31"), ("expected_pages", "2쪽")]:
        rows = good_set()
        rows[0][field] = value
        assert validate_confirm_set(rows, PAGES), (field, value)


def judged(verdicts, borderline=()):
    """borderline: (인덱스, worse_verdict) 목록."""
    rows = [{"qid": f"q{i + 1}", "verdict": v, "borderline": "no", "worse_verdict": ""} for i, v in enumerate(verdicts)]
    for i, worse in borderline:
        rows[i].update(borderline="yes", worse_verdict=worse)
    return rows


def test_passes_counts_borderline_by_worse_verdict():
    # 정답 9(그중 경계 2, worse 오답) + 오답 1 → correct 9, correct_worst 7 → 불합격
    ok, detail = passes(judged(["정답"] * 9 + ["오답"], borderline=[(0, "오답"), (1, "오답")]))
    assert not ok and detail["correct"] == 9 and detail["correct_worst"] == 7
    # 정답 8 + 오답 2, 환각 0 → 합격
    ok, detail = passes(judged(["정답"] * 8 + ["오답"] * 2))
    assert ok and detail == {"correct": 8, "hallucination": 0, "correct_worst": 8, "hallucination_worst": 0}
    # 정답 10 중 경계 1(worse 환각) → 불합격
    ok, detail = passes(judged(["정답"] * 10, borderline=[(4, "환각")]))
    assert not ok and detail["hallucination"] == 0 and detail["hallucination_worst"] == 1


def test_passes_fails_on_any_hallucination():
    ok, _ = passes(judged(["정답"] * 9 + ["환각"]))
    assert not ok


def test_verdicts_fixed():
    assert VERDICTS == ("정답", "오답", "환각", "찾지 못함")
