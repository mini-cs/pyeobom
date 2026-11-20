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


# --- Task 2: 줄 번호 파일·자를 위치 파일 ---
import json

from measure import fable_split as fs
from measure.v17_gate import DOCS


def _fake_pages(n_lines=9):
    return {d: [(1, PlainPage("\n".join(f"{i}번째 줄 문장입니다" for i in range(1, n_lines + 1)), []))] for d in DOCS}


def _setup(tmp_path, monkeypatch, pages, bundle, answers):
    monkeypatch.setattr(fs, "FABLE", tmp_path)
    monkeypatch.setattr(fs, "base_pages", lambda: pages)
    fs.write_lines(tmp_path / "input")
    (tmp_path / "answers" / bundle).mkdir(parents=True)
    for d in DOCS:
        (tmp_path / "answers" / bundle / f"{d}.md").write_text(answers.get(d, "```\n1:2\n```"), encoding="utf-8")


def _build(tmp_path, bundle):
    return fs.build_cuts(bundle, tmp_path / "answers", tmp_path / "cuts")


def test_cuts_refuse_when_text_hash_differs(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, _fake_pages(), "fable_lines", {})
    meta = json.loads((tmp_path / "input" / "meta.json").read_text(encoding="utf-8"))
    meta[DOCS[0]]["text_hash"] = "0" * 64
    (tmp_path / "input" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(SystemExit):
        _build(tmp_path, "fable_lines")


@pytest.mark.parametrize("missing_lines, eliminated", [(["1:20", "1:21"], True), (["1:20"], False)])
def test_build_cuts_marks_eliminated_over_10_percent(tmp_path, monkeypatch, missing_lines, eliminated):
    good = [f"1:{i}" for i in range(1, 11 - len(missing_lines))]
    answer = "```\n" + "\n".join(good + missing_lines) + "\n```"
    _setup(tmp_path, monkeypatch, _fake_pages(), "fable_lines", {DOCS[0]: answer})
    got = _build(tmp_path, "fable_lines")
    assert got["stats"][DOCS[0]]["received"] == 10
    assert got["stats"][DOCS[0]]["missing"] == len(missing_lines)
    assert got["eliminated"] is eliminated
    assert json.loads((tmp_path / "cuts" / "fable_lines.json").read_text(encoding="utf-8"))["eliminated"] is eliminated


def test_write_lines_meta_has_counts_only(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "base_pages", lambda: _fake_pages(3))
    meta = fs.write_lines(tmp_path)
    assert meta[DOCS[0]] | {"text_hash": ""} == {"text_hash": "", "pages": 1, "lines": 3,
                                                  "chars": len((tmp_path / f"{DOCS[0]}-lines.txt").read_text(encoding="utf-8"))}
    assert (tmp_path / f"{DOCS[0]}-lines.txt").read_bytes().count(b"\r") == 0


def test_fable_pages_stops_when_eliminated(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "FABLE", tmp_path)
    raw = {d: [(1, "세탁 코스 설명 문장입니다.\n건조 코스 설명 문장입니다.")] for d in DOCS}
    (tmp_path / "cuts").mkdir()
    cuts = {"cuts": {d: {"1": [15]} for d in DOCS}, "stats": {}, "eliminated": False, "text_hash": {}}
    (tmp_path / "cuts" / "fable_lines.json").write_text(json.dumps(cuts), encoding="utf-8")
    got = fs.fable_pages("fable_lines")(raw)
    assert got[DOCS[0]][0][1].headings == [(15, "")]
    (tmp_path / "cuts" / "fable_lines.json").write_text(json.dumps(cuts | {"eliminated": True}), encoding="utf-8")
    with pytest.raises(SystemExit):
        fs.fable_pages("fable_lines")(raw)
