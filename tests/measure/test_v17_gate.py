import json

import pytest

from measure.v17_gate import (BROKEN_CHARS, broken_lines, char_ratio, count_leftovers, decimal_ok, heading_hit_rate,
                              page_alignment, page_count_ok, run_gate, run_leftover, table_rows_ok)

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



def test_decimal_ok_whitespace_variants():
    assert decimal_ok([(38, "4.0kg")])
    assert decimal_ok([(38, "4.0  kg")])
    assert not decimal_ok([(38, "14.0 kg")])
    assert not decimal_ok([(38, "4.0kg\n4 0 kg")])


def test_heading_hit_rate_contain_rule():
    toc = [(5, "경고")]
    assert heading_hit_rate({5: ["경고"]}, toc) == 1.0
    toc = [(5, "제품을 설치할 때")]
    assert heading_hit_rate({5: ["설치"]}, toc) == 0.0  # 2자지만 긴 쪽의 절반 미만
    assert heading_hit_rate({5: ["때"]}, toc) == 0.0  # 1자
    assert heading_hit_rate({5: ["제품을 설치할"]}, toc) == 1.0


def test_count_leftovers():
    c = count_leftovers("a\\*b\n<br>x<BR/>y</div>\n[a](b)\n*강조* 와 _밑줄_\n")
    assert c["backslash_escape"] == 1 and c["html:br"] == 2 and c["html:div"] == 1 and c["md_link"] == 1
    assert c["star_wrapped"] == 1 and c["underscore_wrapped"] == 1
    clean = count_leftovers("WD90H25AH*/WD90H25BH* a_b_c **굵게** __x__ 2 * 3 * 4")
    assert not any(clean.values())


def _w(root, tool, doc, pages):
    d = root / tool
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{doc}.json").write_text(json.dumps([{"page": p, "markdown": m} for p, m in pages], ensure_ascii=False),
                                   encoding="utf-8")


SAM, DRUM, AIR = "manual-samsung-wd90h25", "manual-lg-fx25", "manual-lg-sq06fa1wds"


def _base_pages(doc):
    n = {SAM: 38, DRUM: 16, AIR: 3}[doc]
    pages = {p: f"{doc} 쪽 {p} 에만 있는 고유한 긴 문장입니다 abc" for p in range(1, n + 1)}
    if doc == SAM:
        pages[38] += "\n최대 4.0 kg"
    if doc == DRUM:
        pages[16] += "\n40 15 30\n50 20 35\n60 25 45"
    return sorted(pages.items())


def _setup(root):
    for doc in (SAM, DRUM, AIR):
        base = _base_pages(doc)
        _w(root, "pypdfium2", doc, base)
        _w(root, "good", doc, [(p, "## 제목\n" + m if p == 2 else m) for p, m in base])
        _w(root, "baddecimal", doc, [(p, m.replace("4.0 kg", "4 0 kg")) for p, m in base])
        _w(root, "shift", doc, [(p, "" if p == 1 else base[p - 2][1]) for p, _ in base])
    _w(root, "partial", SAM, _base_pages(SAM))  # 3종이 다 없는 도구는 판정하지 않는다
    (root / "toc.json").write_text(json.dumps({SAM: [[2, "제목"]], DRUM: [], AIR: []}, ensure_ascii=False),
                                   encoding="utf-8")


def test_run_gate(tmp_path):
    _setup(tmp_path)
    (tmp_path / "good" / "run.json").write_text(json.dumps({"run_seconds": {SAM: 10}, "device": "cpu"}), encoding="utf-8")
    r = run_gate(tmp_path, tmp_path / "toc.json", tmp_path / "gate.json")
    assert r["good"]["eliminated"] == [] and r["good"]["heading_tool"] is True  # 목차 빈 설명서는 빼고 센다
    assert r["good"]["manuals"][SAM]["heading_hit_rate"] == 1.0 and r["good"]["manuals"][DRUM]["heading_hit_rate"] is None
    assert r["baddecimal"]["eliminated"] == [3]
    assert 2 in r["shift"]["eliminated"]
    assert "partial" in r["not_run"] and "pypdfium2" not in r
    assert json.loads((tmp_path / "gate.json").read_text(encoding="utf-8"))["good"]["eliminated"] == []


def test_heading_tool_rule(tmp_path):
    _setup(tmp_path)
    toc = tmp_path / "toc.json"
    toc.write_text(json.dumps({SAM: [[2, "제목"]], DRUM: [[2, "없는제목입니다"]], AIR: []}, ensure_ascii=False), encoding="utf-8")
    assert run_gate(tmp_path, toc, tmp_path / "g.json")["good"]["heading_tool"] is False  # 남은 설명서 하나가 0.70 미만
    toc.write_text(json.dumps({SAM: [], DRUM: [], AIR: []}), encoding="utf-8")
    assert run_gate(tmp_path, toc, tmp_path / "g.json")["good"]["heading_tool"] is False  # 남은 설명서 0개


def test_run_gate_excluded_by_run_json(tmp_path):
    _setup(tmp_path)
    (tmp_path / "good" / "run.json").write_text(json.dumps({"excluded": "설치 실패"}), encoding="utf-8")
    assert run_gate(tmp_path, tmp_path / "toc.json", tmp_path / "g.json")["good"]["eliminated"] == [1]


def test_run_gate_slow_and_gpu(tmp_path):
    _setup(tmp_path)
    (tmp_path / "good" / "run.json").write_text(json.dumps({"run_seconds": {SAM: 1801}, "gpu_required": True}),
                                                encoding="utf-8")
    assert run_gate(tmp_path, tmp_path / "toc.json", tmp_path / "g.json")["good"]["eliminated"] == [1]
    (tmp_path / "good" / "run.json").write_text(json.dumps({"run_seconds": {SAM: 1800}, "excluded": False}),
                                                encoding="utf-8")
    assert run_gate(tmp_path, tmp_path / "toc.json", tmp_path / "g.json")["good"]["eliminated"] == []


def test_run_gate_applies_clean_text(tmp_path):
    _setup(tmp_path)
    for doc in (SAM, DRUM, AIR):  # 바닥글·(cid:)는 clean_text가 지우므로 도구 쪽 깨진 줄·글자 수에 세지 않는다
        _w(tmp_path, "good", doc, [(p, m + "\n(cid:12)\nUntitled-1 12") for p, m in _base_pages(doc)])
    r = run_gate(tmp_path, tmp_path / "toc.json", tmp_path / "g.json")["good"]
    assert r["eliminated"] == [] and r["manuals"][SAM]["broken_lines"] == 0
    assert r["manuals"][SAM]["char_ratio"] == 1.0


def test_run_leftover(tmp_path, capsys):
    _setup(tmp_path)
    assert run_leftover(tmp_path) is False
    _w(tmp_path, "good", AIR, [(1, "x <br> y")])
    assert run_leftover(tmp_path) is True
    out = capsys.readouterr().out
    assert "html:br" in out and "x <br>" not in out
