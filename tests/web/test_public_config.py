import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.web import create_app

FAKE = {  # 값은 모두 가짜. 서버 전용 값이 응답에 새지 않는지 본다
    "SUPABASE_URL": "https://fake-project.supabase.co",
    "SUPABASE_ANON_KEY": "sb_publishable_fake-public-key",
    "SUPABASE_SERVICE_KEY": "sb_secret_fake-server-key",
    "RESEND_API_KEY": "re_fake-resend-key",
    "NOTIFY_WEBHOOK_SECRET": "fake-webhook-secret",
    "OPERATOR_EMAIL": "operator@example.com",
    "MAIL_FROM": "펴봄 <noreply@mail.pyeobom.help>",
}
SERVER_ONLY = ("SUPABASE_SERVICE_KEY", "RESEND_API_KEY", "NOTIFY_WEBHOOK_SECRET", "OPERATOR_EMAIL", "MAIL_FROM")


@pytest.fixture
def client(monkeypatch):
    for key, value in FAKE.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield TestClient(create_app())
    get_settings.cache_clear()


def test_public_config_returns_only_public_values(client):
    res = client.get("/api/public-config")
    assert res.status_code == 200
    assert res.json() == {"supabase_url": FAKE["SUPABASE_URL"], "supabase_anon_key": FAKE["SUPABASE_ANON_KEY"]}
    for key in SERVER_ONLY:
        assert FAKE[key] not in res.text


@pytest.mark.parametrize("missing", ["SUPABASE_URL", "SUPABASE_ANON_KEY"])
def test_public_config_503_when_missing(client, monkeypatch, missing):
    monkeypatch.setenv(missing, "")
    get_settings.cache_clear()
    res = client.get("/api/public-config")
    assert res.status_code == 503
    assert res.json()["error_code"] == "LOGIN_UNAVAILABLE"
