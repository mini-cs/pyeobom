from ingest.chunk import chunk_pages
from ingest.plaintext import PlainPage
from ingest.section_chunk import chunk_sections


def _page(*parts):
    """parts: (제목 or None, 본문) -> PlainPage (제목 줄 + 본문)"""
    text, heads = "", []
    for h, body in parts:
        if h:
            heads.append((len(text), h))
            text += h + "\n"
        text += body + "\n"
    return PlainPage(text, heads)


def test_new_chunk_at_each_heading():
    pp = _page(("제목A", "가" * 300), ("제목B", "나" * 300))
    out = chunk_sections([(1, pp)])
    assert len(out) == 2
    assert out[0][1].startswith("제목A") and out[1][1].startswith("제목B")


def test_text_before_first_heading_is_section():
    pp = _page((None, "앞" * 200), ("제목A", "가" * 300))
    out = chunk_sections([(1, pp)])
    assert len(out) == 2
    assert out[0][1] == "앞" * 200 and out[1][1].startswith("제목A")


def test_no_page_crossing():
    p1 = _page(("제목A", "가" * 300))
    p2 = _page((None, "이어진" * 100), ("제목B", "나" * 300))
    out = chunk_sections([(1, p1), (2, p2)])
    assert [p for p, _ in out] == [1, 2, 2]
    assert out[1][1].startswith("이어진")


def test_long_section_split():
    pp = _page(("제목A", "가" * 1900))
    out = chunk_sections([(3, pp)])
    assert out == chunk_pages([(3, pp.text)], 800, 100)
    assert len(out) > 1


def test_short_section_merged_with_next():
    pp = _page(("짧은", "가" * 20), ("제목B", "나" * 300))
    out = chunk_sections([(1, pp)])
    assert len(out) == 1
    assert out[0][1] == pp.text.strip()


def test_short_last_section_merged_with_previous():
    pp = _page(("제목A", "가" * 300), ("끝", "나" * 20))
    out = chunk_sections([(1, pp)])
    assert len(out) == 1
    assert out[0][1].endswith("나" * 20)


def test_single_short_section_kept():
    pp = _page(("제목A", "가" * 20))
    assert chunk_sections([(1, pp)]) == [(1, pp.text.strip())]


def test_no_added_text():
    pp = _page((None, "앞" * 150), ("제목A", "가" * 1500), ("B", "나" * 10), ("제목C", "다" * 400))
    for page, chunk in chunk_sections([(5, pp)]):
        assert page == 5 and chunk in pp.text
