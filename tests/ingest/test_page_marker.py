from ingest.page_marker import count_remaining_markers, strip_page_marker, strip_plain_page
from ingest.plaintext import PlainPage


def test_samsung_odd(): assert strip_page_marker("한국어 55\n5. 부드러운 솔", 55) == ("5. 부드러운 솔", ["한국어 55\n"])
def test_samsung_crlf(): assert strip_page_marker("한국어 7\r\n 세탁물이", 7) == (" 세탁물이", ["한국어 7\r\n"])
def test_samsung_even_after_chapter():
    assert strip_page_marker("제품 사용 방법\n36 한국어\n AI 맞춤+", 36) == ("제품 사용 방법\n AI 맞춤+", ["36 한국어\n"])
def test_lg_space(): assert strip_page_marker("12 사용 전에", 12) == ("사용 전에", ["12 "])
def test_lg_newline(): assert strip_page_marker("12\n사용 전에", 12) == ("사용 전에", ["12\n"])
def test_other_number_kept(): t = "• 36 °C 이상 고온"; assert strip_page_marker(t, 4) == (t, [])
def test_digit_neighbors_kept(): t = "155 ml 이하"; assert strip_page_marker(t, 55) == (t, [])
def test_list_number_kept(): t = "1. 세탁물을 분류하세요."; assert strip_page_marker(t, 1) == (t, [])
def test_beyond_20_kept(): t = "가" * 25 + "\n55"; assert strip_page_marker(t, 55) == (t, [])
def test_tail(): assert strip_page_marker("본문 끝\n55", 55, check_tail=True) == ("본문 끝", ["\n55"])
def test_tail_off_by_default(): t = "본문 끝\n55"; assert strip_page_marker(t, 55) == (t, [])
def test_count_remaining(): assert count_remaining_markers("본문\n55\n더\n한국어 55 끝", 55) == 2
def test_count_ignores_other_numbers(): assert count_remaining_markers("55 ml\n155", 55) == 0
def test_tail_removes_one_break_only():
    assert strip_page_marker("본문\n\n55", 55, check_tail=True) == ("본문\n", ["\n55"])
    assert strip_page_marker("본문 \n55", 55, check_tail=True) == ("본문 ", ["\n55"])


def test_attached_korean_stays_on_same_line():
    assert strip_page_marker("55\n한국어 설명서 본문", 55) == ("한국어 설명서 본문", ["55\n"])
    assert count_remaining_markers("55\n한국어 설명", 55) == 1


def test_tail_only_when_front_removed_nothing():
    assert strip_page_marker("12\n본문 끝\n12", 12, check_tail=True) == ("본문 끝\n12", ["12\n"])


def _assert_headings_aligned(pp):
    for pos, title in pp.headings:
        assert pp.text[pos:].startswith(title)


def test_plain_front_marker_shifts_headings():
    text = "한국어 5\n서론\n본문\n제목B\n끝"
    pp = PlainPage(text, [(text.index("서론"), "서론"), (text.index("제목B"), "제목B")])
    out, removed = strip_plain_page(pp, 5)
    assert removed == ["한국어 5\n"] and out.text == "서론\n본문\n제목B\n끝"
    assert [t for _, t in out.headings] == ["서론", "제목B"]
    _assert_headings_aligned(out)


def test_plain_heading_starting_in_removed_span_dropped():
    text = "12\n사용 전에\n본문"
    pp = PlainPage(text, [(0, "12"), (text.index("사용"), "사용 전에")])
    out, _ = strip_plain_page(pp, 12)
    assert out.headings == [(0, "사용 전에")]
    _assert_headings_aligned(out)


def test_plain_heading_overlapping_removed_span_dropped():
    text = "12 사용 전에\n본문"  # 제목이 지운 "12 "와 겹침
    pp = PlainPage(text, [(0, "12 사용 전에")])
    out, removed = strip_plain_page(pp, 12)
    assert removed == ["12 "] and out.headings == []


def test_plain_tail_removal_keeps_earlier_headings():
    text = "제목\n본문 끝\n55"
    pp = PlainPage(text, [(0, "제목")])
    out, removed = strip_plain_page(pp, 55, check_tail=True)
    assert removed == ["\n55"] and out.text == "제목\n본문 끝" and out.headings == [(0, "제목")]
    _assert_headings_aligned(out)


def test_plain_nothing_removed_same_page():
    pp = PlainPage("• 36 °C 이상\n제목", [(10, "제목")])
    assert strip_plain_page(pp, 4) == (pp, [])
