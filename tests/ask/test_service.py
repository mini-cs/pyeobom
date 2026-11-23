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


def test_debug_has_cited_refs(fake):
    # 평가(Task 13)가 인용의 근거 표기(manual:<쪽>·guide:<id>)로 근거 적중을 채점한다
    fake.outputs = [GUIDE_ONLY_ANSWER]
    r = answer_question("washer-a", "5C 에러", fake.deps, S, debug=True)
    assert r["cited_refs"] == ["guide:guide-drum-5c"]
    assert "cited_refs" not in answer_question("washer-a", "통세척", Fake().deps, S)


DIAG = Chunk(9, "manual-washer-a", "manual", "A 세탁기 사용설명서", "https://example.com/a.pdf", 54, "고장 진단하기: 앱으로 고장 원인을 진단할 수 있습니다.", 0.0)


def with_diagnostic(fake, chunks):
    fake.diag_calls = []
    def diagnostic(model_id):
        fake.diag_calls.append(model_id)
        return chunks
    fake.deps.diagnostic = diagnostic
    return fake


def test_code_in_chunks_adds_no_diagnostic(fake):
    with_diagnostic(fake, [DIAG])
    r = answer_question("washer-a", "5C 에러가 떴어요", fake.deps, S, debug=True)
    assert r["retrieved_refs"] == ["manual:32", "guide:guide-drum-5c"] and r["diagnostic_added"] is False


def test_code_missing_appends_diagnostic_chunks(fake):
    with_diagnostic(fake, [DIAG, CH[0]])   # 이미 검색된 조각(id 7)은 겹쳐서 빠진다
    r = answer_question("washer-a", "CH10이 떴어요", fake.deps, S, debug=True)
    assert r["retrieved_refs"] == ["manual:32", "guide:guide-drum-5c", "manual:54"] and r["diagnostic_added"] is True
    assert 'chunk_id="9"' in fake.complete_calls[0][-1]["content"]   # 덧붙인 조각이 AI 맥락에 들어감
    # 받은 조각은 문서 단위 표기(guide:…)와 별도로 조각 번호로도 남긴다(가이드는 문서 단위라 어느 조각인지 알 수 없었음)
    assert r["retrieved_chunk_ids"] == [7, 8, 9]
    assert "retrieved_chunk_ids" not in answer_question("washer-a", "통세척", Fake().deps, S)


def test_model_without_diagnostic_refs_is_unchanged(fake):
    with_diagnostic(fake, [])
    r = answer_question("washer-a", "IE 에러가 떴어요", fake.deps, S, debug=True)
    assert r["retrieved_refs"] == ["manual:32", "guide:guide-drum-5c"] and r["diagnostic_added"] is False


def test_question_without_code_never_looks_up_diagnostic(fake):
    with_diagnostic(fake, [DIAG])
    answer_question("washer-a", "통세척", fake.deps, S)
    assert fake.diag_calls == []


# ── 첫 질문 다듬기(v1.96) ──
from dataclasses import replace

import app.ask.service as service
from app.answer.refine import RefineResult

Q = "문이 안 열려요"
REFINED = "문이 안 열려요 도어 잠김"
BODY_KEYS = {"found", "answer", "citations", "official_url", "latency_ms", "pii_masked", "question_masked",
             "rewritten_question", "reason"}


class RefineFake(Fake):
    def __init__(self, result=None, brand="LG"):
        super().__init__()
        self.result = result or RefineResult(REFINED, True, "ok", {"input_tokens": 100, "output_tokens": 10})
        self.refine_calls, self.embeds_calls, self.searches_calls = [], [], []
        self.deps.refine, self.deps.embed_queries, self.deps.search_queries = self.refine, self.embed_many, self.search_many
        self.deps.brand = lambda m: brand

    def refine(self, question, model_id):
        self.refine_calls.append((question, model_id))
        return self.result

    def embed_many(self, texts):
        self.embeds_calls.append(texts)
        return [[0.1], [0.2]]

    def search_many(self, model_id, query_vecs, k):
        self.searches_calls.append((model_id, query_vecs, k))
        return self.chunks


def test_refine_off_keeps_current_flow(fake):
    r = answer_question("washer-a", Q, fake.deps, S, debug=True)
    assert fake.embed_calls == [Q] and fake.search_calls == [("washer-a", Q, 5)] and len(fake.complete_calls) == 1
    assert (r["refine_reason"], r["refine_ms"], r["refined_question"]) == ("off", None, None)
    assert (r["refine_input_tokens"], r["refine_output_tokens"]) == (0, 0)
    for unwired in (lambda: fake.deps.embed_queries([Q]), lambda: fake.deps.search_queries("washer-a", [[0.1]], 5)):
        with pytest.raises(RuntimeError):  # 기본값은 연결하지 않으면 부를 수 없다(꺼짐에서 몰래 쓰이지 않게)
            unwired()


def test_first_question_refined_and_searched_with_both():
    rf = RefineFake()
    r = answer_question("washer-a", Q, rf.deps, S, debug=True)
    assert rf.refine_calls == [(Q, "washer-a")]
    assert rf.embeds_calls == [[Q, REFINED]] and rf.searches_calls == [("washer-a", [[0.1], [0.2]], 5)]
    assert rf.embed_calls == [] and rf.search_calls == []
    assert (r["refined_question"], r["refine_reason"]) == (REFINED, "ok") and isinstance(r["refine_ms"], int)
    assert (r["refine_input_tokens"], r["refine_output_tokens"]) == (100, 10) and r["found"] is True


def test_answer_ai_and_diagnostic_use_original_question(monkeypatch):
    seen = []
    monkeypatch.setattr(service, "needs_diagnostic", lambda question, chunks: seen.append(question) or False)
    rf = RefineFake()
    answer_question("washer-a", Q, rf.deps, S)
    assert seen == [Q]
    sent = str(rf.complete_calls)
    assert Q in sent and "도어 잠김" not in sent


def test_refine_receives_masked_question():
    rf = RefineFake()
    answer_question("washer-a", "010-0000-0000 문이 안 열려요", rf.deps, S)
    assert "0000-0000" not in rf.refine_calls[0][0] and rf.refine_calls[0][1] == "washer-a"


def test_followup_is_not_refined():
    rf = RefineFake()
    r = answer_question("washer-a", "그건 얼마나 걸려요?", rf.deps, S, debug=True,
                        history=[{"question": "통세척은 어떻게 해요?", "answer": "통살균 코스를 선택하세요."}])
    assert rf.refine_calls == [] and rf.embeds_calls == [] and len(rf.search_calls) == 1
    assert (r["refine_reason"], r["refine_ms"], r["refined_question"]) == (None, None, None)


def test_blocked_and_force_fail_are_not_refined():
    rf = RefineFake(brand="LG")
    r = answer_question("washer-a", "삼성 세탁기 문이 안 열려요", rf.deps, S)
    assert r["reason"] == "other_brand" and rf.refine_calls == []
    rf = RefineFake()
    answer_question("washer-a", Q, rf.deps, replace(S, force_fail=True))
    assert rf.refine_calls == []


def test_refined_other_brand_falls_back_not_blocked():
    rf = RefineFake(RefineResult("문이 안 열려요 삼성 세탁기 도어", True, "ok"), brand="LG")
    r = answer_question("washer-a", Q, rf.deps, S, debug=True)
    assert r["refine_reason"] == "other_brand" and r["refined_question"] is None
    assert r["reason"] is None and r["found"] is True
    assert rf.embed_calls == [Q] and len(rf.search_calls) == 1 and rf.embeds_calls == [] and rf.searches_calls == []


def test_refine_failure_answers_with_original_search():
    rf = RefineFake(RefineResult(Q, False, "timeout"))
    r = answer_question("washer-a", Q, rf.deps, S, debug=True)
    assert len(rf.search_calls) == 1 and rf.searches_calls == [] and r["found"] is True
    assert r["refine_reason"] == "timeout" and isinstance(r["refine_ms"], int) and r["refined_question"] is None


def test_refine_same_text_uses_single_search():
    rf = RefineFake(RefineResult(Q, False, "same"))
    r = answer_question("washer-a", Q, rf.deps, S, debug=True)
    assert rf.embeds_calls == [] and rf.embed_calls == [Q] and r["refine_reason"] == "same"


def test_non_debug_body_keys_unchanged(fake):
    assert set(answer_question("washer-a", Q, fake.deps, S)) == BODY_KEYS
    assert set(answer_question("washer-a", Q, RefineFake().deps, S)) == BODY_KEYS
