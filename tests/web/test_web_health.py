from fastapi.testclient import TestClient
from app.web import create_app

def test_health_returns_ok():
    res = TestClient(create_app()).get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
