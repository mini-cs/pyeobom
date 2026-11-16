from measure.v17_page_marker import summarize


def test_summarize_counts_shapes_and_recount():
    pages = [(1, "1 사용 전에 안전 수칙을 읽으세요"), (2, "한국어 2\n세탁 방법"), (3, "본문만 있는 쪽")]
    r = summarize(pages)
    assert r["total_pages"] == 3 and r["removed_pages"] == 2
    assert r["shapes"] == {"N": 1, "한국어 N": 1}
    assert r["before"] == 2 and r["after"] == 0
    assert r["removed"] == [{"page": 1, "removed": ["1 "]}, {"page": 2, "removed": ["한국어 2\n"]}]
