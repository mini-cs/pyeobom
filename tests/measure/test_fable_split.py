import pytest

from ingest.plaintext import PlainPage
from ingest.section_chunk import chunk_sections
from measure.fable_split import (Parsed, cuts_from_lines, cuts_from_pdf, dropped_ratio, locate_start, numbered_lines,
                                 parse_line_answer, parse_pdf_answer, with_cuts)


def test_numbered_lines_skips_blank_and_maps_offsets():
    pp = PlainPage("가나\n\n  \n다라마", [])
    text, idx = numbered_lines([(3, pp)])
    assert text.splitlines() == ["3:1\t가나", "3:2\t다라마"]
    assert idx == {(3, 1): 0, (3, 2): pp.text.index("다라마")}


def test_parse_joins_blocks_dedups_and_sorts():
    ans = "앞말\n```text\n5:3\n4:2\n```\n중간\n```\n5:3\n4:7\n```"
    p = parse_line_answer(ans)
    assert p.items == [(4, 2), (4, 7), (5, 3)] and p.received == 4 and p.bad_format == 0


def test_parse_counts_bad_lines_and_handles_crlf():
    p = parse_line_answer("```\r\n5:3\r\n5:3-7\r\n12쪽 4줄\r\n```")
    assert p.items == [(5, 3)] and p.received == 3 and p.bad_format == 2
    q = parse_pdf_answer("```\n7 | 세탁물의 무게와 종류\n7 세탁물\n```")
    assert q.items == [(7, "세탁물의 무게와 종류")] and q.bad_format == 1


def test_locate_ignores_symbols_spacing_and_fullwidth():
    t = "※ 참고\n• 최대 용량: 9.0 kg\n쾌속 일상 세탁물을"
    assert locate_start(t, "쾌속 일상 세탁물을") == t.index("쾌속")
    assert locate_start(t, "최대용량９") == t.index("최대")


def test_locate_out_of_range_page_and_short_key():
    pages = [(1, PlainPage("첫 쪽 글입니다", []))]
    cuts, missing = cuts_from_pdf(pages, [(9, "첫 쪽 글입니"), (1, "첫"), (1, "첫 쪽 글입니다")])
    assert cuts == {1: [0]} and missing == 2


def test_cuts_from_lines_counts_missing():
    _, idx = numbered_lines([(1, PlainPage("가\n나", []))])
    cuts, missing = cuts_from_lines(idx, [(1, 2), (1, 9), (8, 1)])
    assert cuts == {1: [2]} and missing == 2


def test_with_cuts_feeds_chunk_sections():
    pp = PlainPage("가" * 150 + "\n" + "나" * 150, [])
    out = chunk_sections(with_cuts([(1, pp)], {1: [151]}))
    assert [t[:1] for _, t in out] == ["가", "나"]


def test_unclosed_last_block_reads_to_end():
    p = parse_line_answer("```text\n3:1\n```\n```\n4:2\n4:5")
    assert p.items == [(3, 1), (4, 2), (4, 5)] and p.received == 3


def test_zero_items_is_unreadable():
    with pytest.raises(ValueError):
        dropped_ratio(parse_line_answer("설명만 있음"), 0)


def test_dropped_ratio_counts_bad_and_missing():
    assert dropped_ratio(Parsed(items=[(1, 1)] * 9, received=10, bad_format=1), 1) == 0.2
