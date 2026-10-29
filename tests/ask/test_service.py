import pytest

from app.answer.check import GUIDE_WARNING, NOT_FOUND_MESSAGE
from app.ask.service import Deps, answer_question
from app.core.config import Settings
from app.core.errors import AppError
from app.retrieval.search import Chunk

S = Settings(openai_api_key="", database_url="", openai_embed_model="m", openai_chat_model="m", embed_dim=3)
CH = [Chunk(7, "manual-washer-a", "manual", "A 세탁기 사용설명서", "https://example.com/a.pdf", 32, "통세척은 통살균 코스로 하세요. 세탁조 클리너를 넣습니다.", 0.1),
      Chunk(8, "guide-drum-5c", "guide", "드럼 세탁기 배수 에러", "https://example.com/g", None, "5C 에러는 배수필터 막힘으로 생길 수 있습니다.", 0.2)]
VALID = '{"found": true, "answer": "통살균 코스로 하세요.", "citations": [{"chunk_id": 7, "quote": "통세척은 통살균 코스로 하세요."}]}'
GUIDE_ONLY_ANSWER = '{"found": true, "answer": "배수필터를 확인하세요.", "citations": [{"chunk_id": 8, "quote": "5C 에러는 배수필터 막힘으로 생길 수 있습니다."}]}'


class Fake:
    def __init__(self):
        self.chunks, self.outputs = list(CH), [VALID]
        self.embed_calls, self.search_calls, self.complete_calls = [], [], []
        self.deps = Deps(embed_query=self.embed, search=self.search, complete=self.complete,
                         supported_ids={"washer-a"}, official_url=lambda m: f"https://example.com/support/{m}")

    def embed(self, text):
        self.embed_calls.append(text)
        return [0.1, 0.2, 0.3]

    def search(self, model_id, query_vec, question, k):
        self.search_calls.append((model_id, question, k))
        return self.chunks

    def complete(self, messages):
        self.complete_calls.append(messages)
        return self.outputs.pop(0)


@pytest.fixture
def fake():
    return Fake()


def test_too_long_question_never_reaches_ai(fake):
    with pytest.raises(AppError):
        answer_question("washer-a", "가" * 10_000, fake.deps, S)
    assert fake.embed_calls == [] and fake.complete_calls == []


def test_unknown_model_rejected_before_search(fake):
    with pytest.raises(AppError) as e:
        answer_question("washer-zzz", "통세척", fake.deps, S)
    assert e.value.code == "INVALID_MODEL" and fake.embed_calls == []


def test_pii_masked_before_embed_and_ai(fake):
    r = answer_question("washer-a", "010-1234-5678 기사님 불러 주세요", fake.deps, S)
    assert all("1234-5678" not in str(x) for x in fake.embed_calls + fake.search_calls + fake.complete_calls)
    assert r["pii_masked"] is True


def test_no_chunks_means_not_found_without_ai(fake):
    fake.chunks = []
    r = answer_question("washer-a", "중고 시세", fake.deps, S)
    assert r["found"] is False and r["answer"] == NOT_FOUND_MESSAGE and fake.complete_calls == []


def test_invalid_ai_output_twice_becomes_not_found(fake):
    fake.outputs = ["garbage", '{"found": true, "answer": "x", "citations": []}']
    r = answer_question("washer-a", "통세척", fake.deps, S)
    assert r["found"] is False and r["citations"] == [] and len(fake.complete_calls) == 2


def test_invalid_then_valid_output_is_used(fake):
    fake.outputs = ["garbage", VALID]
    assert answer_question("washer-a", "통세척", fake.deps, S)["found"] is True


def test_valid_answer_shape(fake):
    r = answer_question("washer-a", "통세척", fake.deps, S, debug=True)
    assert r["found"] and r["citations"][0] == {"doc_type": "manual", "title": "A 세탁기 사용설명서", "page": 32,
                                                "url": "https://example.com/a.pdf", "quote": "통세척은 통살균 코스로 하세요."}
    assert isinstance(r["latency_ms"], int) and r["pii_masked"] is False
    assert r["official_url"].startswith("https://") and r["retrieved_refs"] == ["manual:32", "guide:guide-drum-5c"]
    assert fake.search_calls == [("washer-a", "통세척", S.top_k)]


def test_debug_fields_hidden_by_default(fake):
    assert "retrieved_refs" not in answer_question("washer-a", "통세척", fake.deps, S)


def test_guide_citation_carries_warning(fake):
    fake.outputs = [GUIDE_ONLY_ANSWER]
    c = answer_question("washer-a", "5C 에러", fake.deps, S)["citations"][0]
    assert c["page"] is None and c["warning"] == GUIDE_WARNING == "공용 콘텐츠라 모델에 따라 다를 수 있어요"


TIMING_KEYS = {"embed_ms", "db_connect_ms", "search_ms", "llm_ms"}


def test_debug_has_stage_timings(fake):
    fake.deps.timings["db_connect_ms"] = 5  # 실제 검색(get_deps)이 DB 연결 시간을 여기 적는다
    r = answer_question("washer-a", "통세척", fake.deps, S, debug=True)
    assert TIMING_KEYS <= r.keys() and all(isinstance(r[k], int) and r[k] >= 0 for k in TIMING_KEYS)
    assert r["db_connect_ms"] == 5


def test_stage_timings_hidden_without_debug(fake):
    assert not TIMING_KEYS & answer_question("washer-a", "통세척", fake.deps, S).keys()
