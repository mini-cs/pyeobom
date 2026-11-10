import pytest
from fastapi.testclient import TestClient

from app.ask.routes import get_deps
from app.answer.rewrite import RewriteResult
from app.ask.service import Deps, answer_question
from app.core.config import HISTORY_ANSWER_KEEP_LEN, MAX_HISTORY_ANSWER_LEN, Settings
from app.input_guard.pii import mask_history
from app.retrieval.search import Chunk
from app.web import create_app

VALID = '{"found": true, "answer": "통살균 코스로 하세요.", "citations": [{"chunk_id": 7, "quote": "통살균 코스"}]}'
FIRST_FIELDS = {"found", "answer", "citations", "official_url", "latency_ms", "pii_masked"}


@pytest.fixture
def client():
    chunk = Chunk(7, "manual-washer-a", "manual", "A 세탁기 사용설명서", "https://example.com/a.pdf", 32, "통세척은 통살균 코스로 하세요.", 0.1)
    deps = Deps(embed_query=lambda q: [0.1], search=lambda m, v, q, k: [chunk], complete=lambda msgs: VALID,
                supported_ids={"washer-a"}, official_url=lambda m: "https://example.com/support")
    app = create_app()
    app.dependency_overrides[get_deps] = lambda: deps
    return TestClient(app, raise_server_exceptions=False)


def _turns(n, question="통세척은요?", answer="통살균 코스로 하세요."):
    return [{"question": question, "answer": answer} for _ in range(n)]


def test_without_history_keeps_first_fields_and_adds_masked_question(client):
    body = client.post("/api/ask", json={"model_id": "washer-a", "question": "통세척"}).json()
    assert set(body) == FIRST_FIELDS | {"question_masked", "rewritten_question", "reason"}
    assert body["question_masked"] == "통세척"
    assert body["rewritten_question"] is None
    assert body["reason"] is None


def test_history_within_limits_is_accepted(client):
    resp = client.post("/api/ask", json={"model_id": "washer-a", "question": "그건 얼마나 걸려요?", "history": _turns(3)})
    assert resp.status_code == 200
    assert resp.json()["rewritten_question"] is None  # 이 fixture의 Deps.rewrite는 기본값(no_history 결과)이라 바꾸지 않는다


@pytest.mark.parametrize("history", [
    _turns(4),                       # 4개
    _turns(1, question="가" * 501),  # 질문 501자
    _turns(1, answer="가" * 4001),   # 답 4,001자(상한 초과)
    "통세척은요?",                     # 형식 틀림(문자열 하나)
    [{"question": "통세척은요?"}],      # 답 빠짐
])
def test_invalid_history_is_rejected(client, history):
    resp = client.post("/api/ask", json={"model_id": "washer-a", "question": "통세척", "history": history})
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_REQUEST"


def test_mask_history_masks_question_and_answer():
    masked = mask_history([{"question": "기사님 010-1234-5678로 연락했어요", "answer": "test@example.com으로 보내세요"}])
    assert "010-1234-5678" not in masked[0]["question"] and "010-****-****" in masked[0]["question"]
    assert "test@example.com" not in masked[0]["answer"] and masked[0]["answer"] == "[이메일]으로 보내세요"


def test_new_question_phone_is_masked_in_response(client):
    body = client.post("/api/ask", json={"model_id": "washer-a", "question": "010-1234-5678 통세척"}).json()
    assert body["question_masked"] == "010-****-**** 통세척"
    assert body["pii_masked"] is True


# ── 앞 대화 답 길이: 상한(4,000자)까지 받고, 가린 뒤 1,000자로 자른다 ──
S = Settings(openai_api_key="", database_url="", openai_embed_model="m", openai_chat_model="m", embed_dim=3)


def _recording_deps(rewrite_calls):
    chunk = Chunk(7, "manual-washer-a", "manual", "A 세탁기 사용설명서", "https://example.com/a.pdf", 32, "통세척은 통살균 코스로 하세요.", 0.1)

    def rewrite(q, h):
        rewrite_calls.append(h)
        return RewriteResult(q, False, "api_error")

    return Deps(embed_query=lambda q: [0.1], search=lambda m, v, q, k: [chunk], complete=lambda msgs: VALID,
                supported_ids={"washer-a"}, official_url=lambda m: "https://example.com/support", rewrite=rewrite)


def test_history_answer_over_cap_is_rejected_and_at_cap_is_truncated(client):
    over = client.post("/api/ask", json={"model_id": "washer-a", "question": "통세척", "history": _turns(1, answer="가" * 4001)})
    assert over.status_code == 400 and over.json()["error_code"] == "INVALID_REQUEST"
    ok = client.post("/api/ask", json={"model_id": "washer-a", "question": "통세척", "history": _turns(1, answer="가" * 4000)})
    assert ok.status_code == 200


def test_long_history_answer_is_truncated_to_keep_len_for_rewrite():
    calls = []
    answer_question("washer-a", "그건요?", _recording_deps(calls), S, history=_turns(1, answer="가" * MAX_HISTORY_ANSWER_LEN))
    assert len(calls[0][0]["answer"]) == HISTORY_ANSWER_KEEP_LEN == 1000


def test_history_answer_is_masked_before_truncation():
    calls = []
    answer = "가" * 985 + "test@example.com" + "나" * 100  # 이메일이 자르는 경계(1,000자) 근처에 걸친다
    answer_question("washer-a", "그건요?", _recording_deps(calls), S, history=_turns(1, answer=answer))
    sent = calls[0][0]["answer"]
    assert "test@" not in sent and "[이메일]" in sent and len(sent) <= HISTORY_ANSWER_KEEP_LEN


def test_history_question_over_500_is_still_rejected(client):
    resp = client.post("/api/ask", json={"model_id": "washer-a", "question": "통세척", "history": _turns(1, question="가" * 501)})
    assert resp.status_code == 400 and resp.json()["error_code"] == "INVALID_REQUEST"


def test_new_question_over_500_is_still_rejected(client):
    resp = client.post("/api/ask", json={"model_id": "washer-a", "question": "가" * 501})
    assert resp.status_code == 400 and resp.json()["error_code"] == "QUESTION_TOO_LONG"  # 지금 동작 그대로


def test_history_answer_cap_covers_answer_output_tokens():
    # 토큰당 4자는 영문·숫자 위주의 넉넉한 가정. 출력 토큰 제한을 올렸을 때 정상 답이 거절되지 않게(최종 검토 Minor 1)
    assert MAX_HISTORY_ANSWER_LEN >= Settings.max_output_tokens * 4


def test_force_fail_skips_rewrite_and_fails_like_before():
    from dataclasses import replace

    from app.answer.llm import complete_json
    from app.core.errors import AppError

    calls = []
    settings = replace(S, force_fail=True)
    deps = _recording_deps(calls)
    deps.complete = lambda msgs: complete_json(msgs, settings)
    with pytest.raises(AppError) as e:
        answer_question("washer-a", "그건요?", deps, settings, history=_turns(1))
    assert calls == [] and e.value.code == "AI_TIMEOUT"
