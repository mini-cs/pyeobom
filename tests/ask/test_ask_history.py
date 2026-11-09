import pytest
from fastapi.testclient import TestClient

from app.ask.routes import get_deps
from app.ask.service import Deps
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
    assert set(body) == FIRST_FIELDS | {"question_masked", "rewritten_question"}
    assert body["question_masked"] == "통세척"
    assert body["rewritten_question"] is None


def test_history_within_limits_is_accepted(client):
    resp = client.post("/api/ask", json={"model_id": "washer-a", "question": "그건 얼마나 걸려요?", "history": _turns(3)})
    assert resp.status_code == 200
    assert resp.json()["rewritten_question"] is None  # 이 Task에서는 아직 바꾸지 않는다


@pytest.mark.parametrize("history", [
    _turns(4),                       # 4개
    _turns(1, question="가" * 501),  # 질문 501자
    _turns(1, answer="가" * 1001),   # 답 1,001자
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
    assert "test@example.com" not in masked[0]["answer"] and masked[0]["answer"].startswith("[이메일]")


def test_new_question_phone_is_masked_in_response(client):
    body = client.post("/api/ask", json={"model_id": "washer-a", "question": "010-1234-5678 통세척"}).json()
    assert body["question_masked"] == "010-****-**** 통세척"
    assert body["pii_masked"] is True
