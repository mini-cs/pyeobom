from ingest.page_marker import count_remaining_markers, strip_page_marker


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
