import json
from types import SimpleNamespace

import pytest

from measure import v17_stage1 as s1

P = lambda n: [{"page": n, "markdown": f"{n}\n본문 {n} 입니다 " * 3}]


def write(root, tool, doc, pages):
    (root / tool).mkdir(parents=True, exist_ok=True)
    (root / tool / f"{doc}.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")


def test_bundle_definition_uses_right_tool_and_tail_rule(tmp_path):
    # 끝에만 쪽 번호가 있는 쪽: pypdfium2 쪽(check_tail 없음)은 남기고, 도구 쪽(check_tail=True)은 지운다
    page = [{"page": 5, "markdown": "본문 줄 하나 그리고 둘\n5"}]
    for tool in ("pypdfium2", "docling"):
        for d in s1.DOCS:
            write(tmp_path, tool, d, page)
    strip = s1.manual_pages("strip_800", tmp_path)
    tool = s1.manual_pages("docling_800", tmp_path)
    assert set(strip) == set(s1.DOCS)
    assert strip[s1.DOCS[0]][0][1].text.rstrip().endswith("5")
    assert not tool[s1.DOCS[0]][0][1].text.rstrip().endswith("5")


def test_unknown_bundle_stops(tmp_path):
    with pytest.raises(SystemExit):
        s1.manual_pages("nope", tmp_path)


def test_measure_embeds_once_and_shares_vector():
    cases = {"dev": [{"id": "a", "model_id": "m", "question": "같은 질문", "expected_ref": "x:1"}],
             "q30": [{"id": "b", "model_id": "m", "question": "같은 질문", "expected_ref": "x:1"},
                     {"id": "c", "model_id": "m", "question": "다른 질문", "expected_ref": "x:1"},
                     {"id": "t", "model_id": "m", "question": "함정", "expected_ref": ""}]}
    calls, seen = [], []

    def embed(q):
        calls.append(q)
        return [float(len(calls))]

    def fns(name):
        def search(m, vec, text, k):
            seen.append((name, tuple(vec)))
            return [SimpleNamespace(id=1, ref="x:1")]
        return search, lambda m: []

    summary, rows = s1.measure_sets(cases, [None, "b1", "b2"], embed, fns, top_k=5)
    assert len(calls) == 2  # 질문 글자별 1회
    for q in ("같은 질문", "다른 질문"):
        pass
    vecs = {}
    for name, v in seen:
        vecs.setdefault(name, set()).add(v)
    assert vecs[None] == vecs["b1"] == vecs["b2"] and len(vecs[None]) == 2
    assert summary["q30"]["b1"]["denominator"] == 2  # 함정 제외
    assert summary["dev"]["b1"]["denominator"] == 1
    assert summary["q30"]["b1"]["hit5"] == 2


def test_test_set_path_is_refused():
    with pytest.raises(SystemExit):
        s1.guard_cases_path("evaluation/paraphrase_test.csv")
    s1.guard_cases_path("evaluation/paraphrase_dev.csv")


def test_sections_bundle_uses_docling_and_chunk_sections(tmp_path):  # Task 8: 순서는 Docling 800자와 같고 자르기만 소제목
    from ingest.section_chunk import chunk_sections
    # 같은 글자만 되풀이한 줄은 clean_text가 지우므로 보통 문장을 쓴다
    md = "## 첫 제목\n" + "세탁 코스 설명 문장입니다. " * 10 + "\n## 둘째 제목\n" + "건조 코스 설명 문장입니다. " * 10
    for d in s1.DOCS:
        write(tmp_path, "docling", d, [{"page": 1, "markdown": md}])
    pages = s1.manual_pages("docling_sections", tmp_path)
    assert pages == s1.manual_pages("docling_800", tmp_path)
    assert s1.BUNDLES["docling_sections"][2] is chunk_sections
    assert s1.BUNDLES["docling_800"][2] is s1.chunk_plain_800
    got = s1.BUNDLES["docling_sections"][2](pages[s1.DOCS[0]])
    assert [t[:5] for _, t in got] == ["첫 제목\n", "둘째 제목"[:5]]


def test_measure_args_select_bundles_and_out():
    assert s1.parse_measure_args([]) == (None, "stage1")
    assert s1.parse_measure_args(["--out", "stage2", "strip_800", "docling_sections"]) == (
        ["strip_800", "docling_sections"], "stage2")
    with pytest.raises(SystemExit):
        s1.parse_measure_args(["nope"])


def test_fable_bundles_use_pypdfium2_and_chunk_sections():  # Fable 분할 계획 Task 2
    from ingest.section_chunk import chunk_sections
    for name in ("fable_lines", "fable_pdf"):
        assert s1.BUNDLES[name][0] == "pypdfium2"
        assert s1.BUNDLES[name][2] is chunk_sections
