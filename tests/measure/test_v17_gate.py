import pytest

from measure.v17_gate import (BROKEN_CHARS, broken_lines, char_ratio, decimal_ok, heading_hit_rate,
                              page_alignment, page_count_ok, table_rows_ok)

BASE = [(1, "첫째 쪽에만 있는 긴 문장입니다 하나\n짧음"), (2, "둘째 쪽에만 있는 긴 문장입니다 둘\n짧음"),
        (3, "셋째 쪽에만 있는 긴 문장입니다 셋\n짧음")]


def test_page_count_ok():
    assert page_count_ok(BASE, BASE)
    assert not page_count_ok(BASE[:2], BASE)


def test_page_alignment_same():
    assert page_alignment(BASE, BASE) == 1.0


def test_page_alignment_ignores_whitespace_and_repeated_lines():
    base = [(1, "같은 줄이 여러 쪽에 반복됩니다 머리글\n고유한 첫 번째 쪽 문장입니다 가나"), (2, "같은 줄이 여러 쪽에 반복됩니다 머리글")]
    tool = [(1, "고유한첫번째쪽 문장입니다가나"), (2, "")]
    assert page_alignment(tool, base) == 1.0  # 2쪽은 고를 줄이 없어 세지 않는다


def test_page_alignment_detects_shift():
    tool = [(1, BASE[0][1]), (2, ""), (3, BASE[1][1]), (4, BASE[2][1])]
    assert page_alignment(tool, BASE) < 0.9


def test_decimal_ok():
    assert decimal_ok([(38, "최대 용량: 4.0 kg")])
    assert not decimal_ok([(38, "최대 용량: 4.0 kg\n4 0 kg")])
    assert not decimal_ok([(37, "4.0 kg")])


def test_table_rows_ok():
    assert table_rows_ok([(16, "40 15 30\n50  20 35\n60 25 45")])
    assert not table_rows_ok([(16, "40 50 60\n15 20 25\n30 35 45")])


def test_char_ratio():
    assert char_ratio([(1, "a b c")], [(1, "abcd")]) == 0.75


def test_heading_hit_rate():
    toc = [(26, "세제함 사용하기")]
    assert heading_hit_rate({26: ["세제함  사용하기"]}, toc) == 1.0
    assert heading_hit_rate({27: ["세제함 사용하기"]}, toc) == 0.0
    assert heading_hit_rate({26: ["제 3장 세제함 사용하기 안내"]}, toc) == 1.0
    with pytest.raises(ValueError):
        heading_hit_rate({}, [])


def test_broken_lines():
    assert broken_lines([(1, "깨짐 (cid:12)\n정상 한글 줄")]) == 1


def test_broken_chars_fixed():
    assert broken_lines([(1, "a\ufffdb\nc\ue000d\ne\x00f\ng\x1fh\ni\tj\nk\u00a0l\n정상")]) == 4
    assert "\ufffd" in BROKEN_CHARS and "\ue000" in BROKEN_CHARS and "\uf8ff" in BROKEN_CHARS
    assert "\t" not in BROKEN_CHARS and "\n" not in BROKEN_CHARS and "\r" not in BROKEN_CHARS
