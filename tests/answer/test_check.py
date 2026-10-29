import pytest

from app.answer.check import NOT_FOUND_MESSAGE, Answer, Citation, parse_and_verify
from app.retrieval.search import Chunk

CH = [Chunk(7, "manual-washer-a", "manual", "A 세탁기 사용설명서", "https://example.com/a.pdf", 32, "배수 필터를 시계 반대 방향으로 돌려 빼 주세요. 이물질을 제거합니다.", 0.1),
      Chunk(8, "guide-drum-5c", "guide", "드럼 세탁기 배수 에러", "https://example.com/g", None, "배수 에러는 배수필터 막힘으로 생길 수 있습니다.", 0.2)]
VALID = '{"found": true, "answer": "배수 필터를 청소하세요.", "citations": [{"chunk_id": 7, "quote": "배수 필터를 시계 반대 방향으로 돌려 빼 주세요."}]}'


def test_valid_answer_maps_chunk_to_page():
    a = parse_and_verify(VALID, CH)
    assert a.found and a.citations[0] == Citation("manual-washer-a", "manual", "A 세탁기 사용설명서", 32, "https://example.com/a.pdf", "배수 필터를 시계 반대 방향으로 돌려 빼 주세요.")
    assert a.citations[0].ref == "manual:32"


def test_guide_citation_has_no_page():
    raw = '{"found": true, "answer": "배수필터를 확인하세요.", "citations": [{"chunk_id": 8, "quote": "배수 에러는 배수필터 막힘으로 생길 수 있습니다."}]}'
    c = parse_and_verify(raw, CH).citations[0]
    assert c.doc_type == "guide" and c.page is None and c.ref == "guide:guide-drum-5c"


def test_code_fence_is_tolerated():
    assert parse_and_verify("```json\n" + VALID + "\n```", CH) is not None


def test_quote_whitespace_is_normalized():
    raw = VALID.replace("돌려 빼 주세요.", "돌려  빼\n주세요.")
    assert parse_and_verify(raw, CH) is not None


@pytest.mark.parametrize("raw", [
    "not json",
    '{"found": true, "answer": "x", "citations": []}',                                  # 근거 없음
    '{"found": true, "answer": "x", "citations": [{"chunk_id": 99, "quote": "배수"}]}',  # 검색 안 된 조각
    '{"found": true, "answer": "x", "citations": [{"chunk_id": 7, "quote": "필터를 매일 교체하세요."}]}',  # 지어낸 인용
    '{"found": true, "answer": "x", "citations": [{"chunk_id": 7, "quote": "' + "가" * 151 + '"}]}',     # 150자 초과
    '{"found": true, "answer": "", "citations": [{"chunk_id": 7, "quote": "배수 필터를"}]}',              # 빈 답
    '["found", true]',                                                                   # 객체가 아님
])
def test_invalid_outputs_rejected(raw):
    assert parse_and_verify(raw, CH) is None


def test_not_found_answer():
    a = parse_and_verify('{"found": false, "answer": "", "citations": []}', CH)
    assert a == Answer(False, NOT_FOUND_MESSAGE, [])
