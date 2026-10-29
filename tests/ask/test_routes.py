import pytest
from fastapi.testclient import TestClient

from app.ask.routes import get_deps
from app.ask.service import Deps
from app.core.errors import make_error
from app.web import create_app

OK_BODY = {"model_id": "washer-a", "question": "통세척"}
VALID = '{"found": true, "answer": "통살균 코스로 하세요.", "citations": [{"chunk_id": 7, "quote": "통살균 코스"}]}'


def deps(search=None, embed=None):
    from app.retrieval.search import Chunk
    chunk = Chunk(7, "manual-washer-a", "manual", "A 세탁기 사용설명서", "https://example.com/a.pdf", 32, "통세척은 통살균 코스로 하세요.", 0.1)
    return Deps(embed_query=embed or (lambda q: [0.1]), search=search or (lambda m, v, q, k: [chunk]),
                complete=lambda msgs: VALID, supported_ids={"washer-a"}, official_url=lambda m: "https://example.com/support")


def client_for(d):
    app = create_app()
    app.dependency_overrides[get_deps] = lambda: d
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_with_fake():
    return client_for(deps())


@pytest.fixture
def client_with_db_down():
    def down(*_):
        raise make_error("DB_UNAVAILABLE")
    return client_for(deps(search=down))


@pytest.fixture
def client_with_crash():
    def crash(_):
        raise RuntimeError("boom postgresql://user:secret@host/db")
    return client_for(deps(embed=crash))


def test_ask_ok(client_with_fake):
    r = client_with_fake.post("/api/ask", json=OK_BODY)
    assert r.status_code == 200 and r.json()["found"] is True and r.json()["citations"][0]["page"] == 32


def test_ask_input_error_json(client_with_fake):
    r = client_with_fake.post("/api/ask", json={"model_id": "washer-a", "question": " "})
    assert r.status_code == 400 and r.json() == {"error_code": "EMPTY_QUESTION", "message": "질문을 입력해 주세요"}


def test_missing_fields_are_input_errors_not_422(client_with_fake):
    r = client_with_fake.post("/api/ask", json={})
    assert r.status_code == 400 and r.json()["error_code"] == "INVALID_MODEL"


def test_db_failure_is_json_503(client_with_db_down):
    r = client_with_db_down.post("/api/ask", json=OK_BODY)
    assert r.status_code == 503 and r.json()["error_code"] == "DB_UNAVAILABLE"


def test_unexpected_error_hides_trace(client_with_crash):
    r = client_with_crash.post("/api/ask", json=OK_BODY)
    assert r.status_code == 500 and r.json()["error_code"] == "SERVICE_UNAVAILABLE"
    assert "Traceback" not in r.text and "secret" not in r.text


def test_debug_query_param_adds_timings(client_with_fake):
    r = client_with_fake.post("/api/ask?debug=true", json=OK_BODY).json()
    assert {"retrieved_refs", "embed_ms", "db_connect_ms", "search_ms", "llm_ms"} <= r.keys()
    assert "llm_ms" not in client_with_fake.post("/api/ask", json=OK_BODY).json()


INVALID_REQUEST = {"error_code": "INVALID_REQUEST", "message": "요청 형식이 올바르지 않아요. 새로고침한 뒤 다시 시도해 주세요"}


def test_non_json_body_is_invalid_request(client_with_fake):
    r = client_with_fake.post("/api/ask", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json() == INVALID_REQUEST


def test_broken_encoding_is_invalid_request(client_with_fake):
    # Windows 코드 페이지로 보낸 한글처럼 UTF-8이 아닌 바이트
    r = client_with_fake.post("/api/ask", content='{"model_id":"washer-a","question":"탈수"}'.encode("cp949"),
                              headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json() == INVALID_REQUEST


def test_wrong_field_type_is_invalid_request(client_with_fake):
    r = client_with_fake.post("/api/ask", json={"model_id": "washer-a", "question": 123})
    assert r.status_code == 400 and r.json() == INVALID_REQUEST
