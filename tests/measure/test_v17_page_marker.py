from measure.v17_page_marker import summarize


def test_summarize_counts_shapes_and_recount():
    pages = [(1, "1 사용 전에 안전 수칙을 읽으세요"), (2, "한국어 2\n세탁 방법"), (3, "본문만 있는 쪽")]
    r = summarize(pages)
    assert r["total_pages"] == 3 and r["removed_pages"] == 2
    assert r["shapes"] == {"N": 1, "한국어 N": 1}
    assert r["before"] == 2 and r["after"] == 0
    assert r["removed"] == [{"page": 1, "removed": ["1 "]}, {"page": 2, "removed": ["한국어 2\n"]}]


def test_diff_check_passes_and_fails():
    from measure.v17_page_marker import check_diff
    assert check_diff("12 사용 전에", "사용 전에", ["12 "]) is True
    assert check_diff("12 사용 전에", "사용 전", ["12 "]) is False  # 지운 자리 밖 글자가 달라짐


def test_summarize_reports_diff_and_position():
    r = summarize([(1, "1 사용 전에 안전"), (2, "제품 사용\n2 설명")])
    assert r["diff_ok"] == 2 and r["front"] == 1 and r["other"] == 1


def test_after_class_hides_characters():
    from measure.v17_page_marker import after_class
    assert [after_class(c, 5) for c in ("5 가", "5\n가", "55", "5가", "5", "5, 가")] == ["공백", "줄바꿈", "글 끝", "기타", "글 끝", "기타"]


def test_diff_check_ambiguous_position():  # 지운 글자가 앞 줄바꿈과 겹쳐 보여도 통과
    from measure.v17_page_marker import check_diff
    assert check_diff("가\n36 한국어\n나", "가\n나", ["36 한국어\n"]) is True
