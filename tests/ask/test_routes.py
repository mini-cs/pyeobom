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
