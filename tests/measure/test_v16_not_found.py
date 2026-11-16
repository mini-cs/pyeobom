import json

import pytest

from app.answer.check import parse_and_verify
from app.ask.service import Deps, answer_question
from app.core.config import Settings
from app.retrieval.search import Chunk
from measure.v16_not_found import (
    BAD_QUOTE, EMPTY, FOUND_FALSE, JSON_ERROR, NOT_IN_CHUNK, PASS, UNRETRIEVED,
    ask_fixed, capture_deps, classify, marker_shape, page_marker, stage3_judgments, strip_page_marker, verdict,
)

S = Settings(openai_api_key="", database_url="", openai_embed_model="m", openai_chat_model="m", embed_dim=3)
P55 = Chunk(83, "manual-x", "manual", "설명서", "https://example.com/m.pdf", 55, "한국어 55\n배수 필터를 청소하세요. 물이 나올 수 있습니다.", 0.1)
P72 = Chunk(105, "manual-x", "manual", "설명서", "https://example.com/m.pdf", 72, "탈수가 안 되면 세탁물을 고르게 펴세요.", 0.2)
P56 = Chunk(90, "manual-x", "manual", "설명서", "https://example.com/m.pdf", 56, "56 한국어\n먼지 필터를 씻으세요.", 0.3)
GUIDE = Chunk(333, "guide-5c", "guide", "5C 가이드", "https://example.com/g", None, "5C 에러는 배수 막힘입니다.", 0.4)
CHUNKS = [P55, P72, P56, GUIDE]


def out(found=True, answer="답", citations=None):
    return json.dumps({"found": found, "answer": answer, "citations": citations or []}, ensure_ascii=False)


# ── 쪽 표시 ──

@pytest.mark.parametrize("content,page,expected", [
    ("한국어 55\n본문", 55, True),
    ("55 한국어\n본문", 55, True),
    ("본문 앞 20자 밖에는 쪽이 있어도 세지 않는다 55", 55, False),
    ("한국어 155\n본문", 55, False),   # 앞에 숫자
    ("한국어 550\n본문", 55, False),   # 뒤에 숫자
    ("한국어 55\n본문", None, False),  # 가이드(쪽 없음)
])
def test_page_marker_counts_own_page_in_first_20_chars_without_adjacent_digits(content, page, expected):
    assert page_marker(content, page) is expected


def test_marker_shape_tells_korean_first_from_number_first():
    assert marker_shape("한국어 55\n본문", 55) == "한국어 N"
    assert marker_shape("56 한국어\n본문", 56) == "N 한국어"
    assert marker_shape("세탁 55 본문", 55) == "그 밖"
    assert marker_shape("본문만", 55) is None


def test_strip_page_marker_removes_through_number_and_following_whitespace():
    assert strip_page_marker("한국어 55\n 배수 필터", 55) == ("배수 필터", "한국어 55\n ")


def test_strip_page_marker_leaves_body_without_marker():
    assert strip_page_marker("배수 필터", 55) == ("배수 필터", "")


# ── 출력 분류: check.py와 같은 순서로 처음 걸린 검사 ──

QUOTE55 = "배수 필터를 청소하세요."
QUOTE72 = "세탁물을 고르게 펴세요."
CASES = [
    (out(citations=[{"chunk_id": 105, "quote": QUOTE72}]), PASS),
    ("JSON 아님", JSON_ERROR),
    ('["found"]', JSON_ERROR),
    (out(found=False), FOUND_FALSE),
    (out(answer=" "), EMPTY),
    (out(citations=[]), EMPTY),
    (out(citations=[{"chunk_id": 55, "quote": QUOTE55}, {"chunk_id": 105, "quote": QUOTE72}]), UNRETRIEVED),
    (out(citations=[{"chunk_id": 105, "quote": ""}]), BAD_QUOTE),
    (out(citations=[{"chunk_id": 105, "quote": "가" * 151}]), BAD_QUOTE),
    (out(citations=[{"chunk_id": 105, "quote": QUOTE55}]), NOT_IN_CHUNK),
    (out(citations=[{"chunk_id": 105, "quote": QUOTE72}, {"chunk_id": 55, "quote": QUOTE55}]), UNRETRIEVED),
]


@pytest.mark.parametrize("raw,reason", CASES)
def test_classify_reason(raw, reason):
    assert classify(raw, CHUNKS)["reason"] == reason


@pytest.mark.parametrize("raw,reason", CASES)
def test_classify_agrees_with_parse_and_verify(raw, reason):
    verified = parse_and_verify(raw, CHUNKS)
    assert (classify(raw, CHUNKS)["reason"] in (PASS, FOUND_FALSE)) is (verified is not None)


def test_each_citation_is_judged_alone():
    raw = out(citations=[{"chunk_id": 55, "quote": QUOTE55}, {"chunk_id": 105, "quote": QUOTE72}])
    cites = classify(raw, CHUNKS)["citations"]
    assert [(c["chunk_id"], c["alone_ok"], c["alone_reason"]) for c in cites] == [(55, False, UNRETRIEVED), (105, True, PASS)]


def test_unretrieved_citation_points_to_chunk_holding_the_quote():
    raw = out(citations=[{"chunk_id": 55, "quote": "  배수 필터를\n청소하세요. "}])
    cite = classify(raw, CHUNKS)["citations"][0]
    assert cite["quote_in"] == [{"id": 83, "page": 55, "id_is_page": True, "page_marker": True}]
    assert cite["page_with_marker"] is True


def test_unretrieved_citation_without_matching_page():
    raw = out(citations=[{"chunk_id": 56, "quote": QUOTE55}])  # 56쪽 조각은 쪽 표시가 있지만 인용 글은 83에 있음
    cite = classify(raw, CHUNKS)["citations"][0]
    assert cite["quote_in"] == [{"id": 83, "page": 55, "id_is_page": False, "page_marker": True}]
    assert cite["page_with_marker"] is False


def test_retrieved_citation_has_no_page_analysis():
    cite = classify(out(citations=[{"chunk_id": 105, "quote": QUOTE72}]), CHUNKS)["citations"][0]
    assert "quote_in" not in cite


# ── 고정 입력으로 서비스와 같은 두 번 묻기 ──

def test_ask_fixed_asks_twice_with_same_messages_and_keeps_every_output():
    outputs = [out(citations=[{"chunk_id": 55, "quote": QUOTE55}]), out(citations=[{"chunk_id": 83, "quote": QUOTE55}])]
    seen = []
    result = ask_fixed("5C가 떠요", CHUNKS, lambda m: seen.append(m) or outputs[len(seen) - 1], "v1")
    assert seen[0] == seen[1]
    assert result["outputs"] == outputs
    assert [c["reason"] for c in result["classes"]] == [UNRETRIEVED, PASS]
    assert result["found"] is True


def test_ask_fixed_stops_after_first_pass():
    seen = []
    result = ask_fixed("q", CHUNKS, lambda m: seen.append(m) or out(citations=[{"chunk_id": 105, "quote": QUOTE72}]), "v1")
    assert len(seen) == 1 and result["found"] is True


def test_ask_fixed_not_found_after_two_failures():
    result = ask_fixed("q", CHUNKS, lambda m: out(citations=[{"chunk_id": 55, "quote": QUOTE55}]), "v1")
    assert len(result["outputs"]) == 2 and result["found"] is False


def test_ask_fixed_uses_given_chunk_page_in_tag():
    seen = []
    from dataclasses import replace
    ask_fixed("q", [replace(P55, page=None)], lambda m: seen.append(m) or out(found=False), "v1")
    assert 'chunk_id="83"' in seen[0][1]["content"] and 'page=""' in seen[0][1]["content"]


# ── 3단계 판정 ①~④ ──

def _cls(reason, cites=()):
    return {"reason": reason, "citations": [dict(c) for c in cites]}


BAD55 = {"chunk_id": 55, "alone_ok": False, "alone_reason": UNRETRIEVED, "page_with_marker": True}
BAD9 = {"chunk_id": 9, "alone_ok": False, "alone_reason": UNRETRIEVED, "page_with_marker": False}
OK = {"chunk_id": 105, "alone_ok": True, "alone_reason": PASS}


def _item(classes, found, answerable=True, error=""):
    return {"answerable": answerable, "found": found, "error": error, "classes": classes}


def test_verdict_thresholds():
    assert verdict(2, 2, 0.5) == "판단 불가"
    assert verdict(4, 2, 0.5) == "지지됨"
    assert verdict(4, 1, 0.5) == "지지 안 됨"
    assert verdict(3, 2, 2 / 3) == "지지됨"
    assert verdict(5, 4, 0.8) == "지지됨" and verdict(5, 3, 0.8) == "지지 안 됨"


def test_stage3_judgments_count_each_rule():
    items = [
        _item([_cls(UNRETRIEVED, [BAD55, OK]), _cls(UNRETRIEVED, [BAD55])], False),     # 검증 2번 실패 + 검색 안 된 번호
        _item([_cls(UNRETRIEVED, [BAD9]), _cls(NOT_IN_CHUNK, [OK])], False),            # 두 번째는 다른 검사
        _item([_cls(FOUND_FALSE)], False),                                              # AI가 found false
        _item([_cls(NOT_IN_CHUNK, [OK]), _cls(PASS, [OK])], True),                      # 재요청에서 통과
        _item([_cls(FOUND_FALSE)], False, answerable=False),                            # 함정: ①에서 뺌
        _item([], None, error="AI_TIMEOUT"),                                            # 오류: ①에서 뺌
    ]
    j = stage3_judgments(items)
    assert (j["①"]["n"], j["①"]["k"], j["①"]["verdict"]) == (3, 2, "지지됨")
    assert (j["②"]["n"], j["②"]["k"], j["②"]["verdict"]) == (3, 2, "지지 안 됨")
    assert (j["③"]["n"], j["③"]["k"], j["③"]["verdict"]) == (3, 1, "지지 안 됨")
    assert (j["④"]["n"], j["④"]["k"], j["④"]["verdict"]) == (5, 3, "지지됨")


# ── 서비스 흐름 감싸기 ──

def test_capture_deps_records_outputs_chunks_and_rewrite():
    outputs = [out(citations=[{"chunk_id": 55, "quote": QUOTE55}]), out(citations=[{"chunk_id": 105, "quote": QUOTE72}])]
    deps = Deps(embed_query=lambda t: [0.1, 0.2, 0.3], search=lambda m, v, q, k: [P55, P72],
                complete=lambda msgs: outputs.pop(0), supported_ids={"washer-a"}, official_url=lambda m: "https://example.com")
    rec: dict = {}
    resp = answer_question("washer-a", "물이 안 빠져요", capture_deps(deps, rec), S, debug=True)
    assert resp["found"] is True
    assert [c.id for c in rec["chunks"]] == resp["retrieved_chunk_ids"] == [83, 105]
    assert len(rec["outputs"]) == 2
    assert rec["rewrite"] is None  # 앞 대화가 없으면 바꾸기를 부르지 않는다
