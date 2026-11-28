"""Supabase 깨우기 /api/wake(2차 Task 11 ③). Supabase는 가짜 get·가짜 ping으로 바꿔 네트워크 0. 값은 모두 가짜."""
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.wake.ping import WakeError, ping_supabase
from app.wake.routes import get_wake_ping
from app.web import create_app

URL = "https://fake-project.supabase.co"
KEY = "sb_secret_fake-server-key"
SECRET = "fake-cron-secret-0123456789abcdef"


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch):
    for k, v in {"SUPABASE_URL": URL, "SUPABASE_SERVICE_KEY": KEY, "CRON_SECRET": SECRET}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def wake():
    calls, state = [], {"fail": None}

    def ping():
        calls.append(1)
        if state["fail"]:
            raise state["fail"]

    app = create_app()
    app.dependency_overrides[get_wake_ping] = lambda: ping
    return TestClient(app), calls, state


def call(client, auth=f"Bearer {SECRET}"):
    return client.get("/api/wake", headers={} if auth is None else {"Authorization": auth})


def test_rejects_missing_or_wrong_authorization(wake):
    client, calls, _ = wake
    for auth in (None, "", "Bearer wrong", SECRET, f"bearer {SECRET}", f"Bearer  {SECRET}", f"Bearer {SECRET}x"):
        res = call(client, auth)
        assert res.status_code == 401
        assert res.json()["error_code"] == "UNAUTHORIZED"
    assert calls == []


def test_rejects_when_cron_secret_not_configured(wake, monkeypatch):
    client, calls, _ = wake
    monkeypatch.setenv("CRON_SECRET", "")
    get_settings.cache_clear()
    assert call(client, "Bearer ").status_code == 401
    assert call(client).status_code == 401
    assert calls == []


def test_pings_supabase_and_returns_ok(wake):
    client, calls, _ = wake
    res = call(client)
    assert res.status_code == 200 and res.json() == {"ok": True}
    assert calls == [1]


def test_ping_failure_returns_502_reason_only(wake):
    client, calls, state = wake
    state["fail"] = WakeError("rest_503")
    res = call(client)
    assert res.status_code == 502
    assert res.json() == {"error_code": "WAKE_FAILED", "message": "깨우지 못했어요", "reason": "rest_503"}
    assert all(s not in res.text for s in (SECRET, KEY, URL))


def test_logs_never_contain_secrets(wake, caplog):
    client, _, state = wake
    caplog.set_level(logging.INFO)
    call(client)
    call(client, "Bearer wrong")
    state["fail"] = WakeError("ConnectTimeout")
    call(client)
    assert "wake: result=ok" in caplog.text and "wake 실패: reason=ConnectTimeout" in caplog.text
    assert "wake: result=unauthorized" in caplog.text
    assert all(s not in caplog.text for s in (SECRET, KEY, URL, "Bearer"))


def test_secret_with_surrounding_spaces_in_env_still_matches(wake, monkeypatch):
    client, calls, _ = wake
    monkeypatch.setenv("CRON_SECRET", f" {SECRET}\n")
    get_settings.cache_clear()
    assert call(client).status_code == 200
    assert calls == [1]


def test_post_not_allowed(wake):
    client, calls, _ = wake
    assert client.post("/api/wake", headers={"Authorization": f"Bearer {SECRET}"}).status_code == 405
    assert calls == []


def response(status, data):
    return httpx.Response(status, json=data, request=httpx.Request("GET", f"{URL}/rest/v1/model_requests"))


def test_ping_reads_one_row_with_secret_key_on_apikey_only():
    seen = {}

    def get(url, **kwargs):
        seen.update(url=url, **kwargs)
        return response(200, [{"id": 1}])

    assert ping_supabase(get=get) is None
    assert seen["url"] == f"{URL}/rest/v1/model_requests"
    assert seen["params"] == {"select": "id", "limit": "1"}
    assert seen["headers"] == {"apikey": KEY}
    assert seen["timeout"] == 10


@pytest.mark.parametrize("status", [401, 500, 503])
def test_ping_raises_rest_status(status):
    with pytest.raises(WakeError, match=f"^rest_{status}$"):
        ping_supabase(get=lambda url, **kw: response(status, {"message": "fake"}))


def test_ping_raises_exception_name_on_http_error():
    def get(url, **kwargs):
        raise httpx.ConnectTimeout("fake timeout", request=httpx.Request("GET", url))

    with pytest.raises(WakeError, match="^ConnectTimeout$"):
        ping_supabase(get=get)


def test_ping_not_configured_does_not_call(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")
    get_settings.cache_clear()
    called = []
    with pytest.raises(WakeError, match="^not_configured$"):
        ping_supabase(get=lambda url, **kw: called.append(1))
    assert called == []
