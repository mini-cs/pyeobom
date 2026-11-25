"""Resend 보내기·Supabase 관리 API(사용자 이메일 찾기). 가짜 post·get만 쓴다(네트워크 0). 값은 모두 가짜."""
import httpx
import pytest

from app.core.config import get_settings
from app.notify.mail import MailError, send_mail
from app.notify.users import get_user_email

USER_ID = "00000000-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch):
    for key, value in {"RESEND_API_KEY": "re_fake-resend-key", "MAIL_FROM": "펴봄 <noreply@mail.example.com>",
                       "SUPABASE_URL": "https://fake-project.supabase.co",
                       "SUPABASE_SERVICE_KEY": "sb_secret_fake-server-key"}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def response(status, data, method="GET", url="https://fake.test"):
    return httpx.Response(status, json=data, request=httpx.Request(method, url))


def test_send_mail_posts_to_resend_with_bearer_and_fields():
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response(200, {"id": "fake-id"}, "POST", url)

    send_mail("someone@example.com", "제목(테스트)", "본문(테스트)", reply_to="operator@example.com", post=post)
    [(url, kwargs)] = calls
    assert url == "https://api.resend.com/emails"
    assert kwargs["headers"]["Authorization"] == "Bearer re_fake-resend-key"
    assert kwargs["json"] == {"from": "펴봄 <noreply@mail.example.com>", "to": ["someone@example.com"],
                              "subject": "제목(테스트)", "text": "본문(테스트)", "reply_to": ["operator@example.com"]}
    assert kwargs["timeout"] == 10


def test_send_mail_without_reply_to_omits_it():
    calls = []
    send_mail("someone@example.com", "제목", "본문",
              post=lambda url, **kw: calls.append(kw) or response(200, {"id": "x"}, "POST", url))
    assert "reply_to" not in calls[0]["json"]


@pytest.mark.parametrize("post", [
    lambda url, **kw: response(422, {"message": "가짜 오류(테스트)"}, "POST", url),
    lambda url, **kw: (_ for _ in ()).throw(httpx.ReadTimeout("가짜 시간 초과")),
    lambda url, **kw: (_ for _ in ()).throw(httpx.ConnectError("가짜 연결 실패")),
])
def test_send_mail_failure_or_timeout_raises_mail_error(post):
    with pytest.raises(MailError):
        send_mail("someone@example.com", "제목", "본문", post=post)


def test_send_mail_without_key_raises_mail_error(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(MailError):
        send_mail("someone@example.com", "제목", "본문", post=lambda url, **kw: pytest.fail("보내면 안 됨"))


def test_get_user_email_uses_secret_key_on_apikey_header():
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response(200, {"id": USER_ID, "email": "requester@example.com"}, "GET", url)

    assert get_user_email(USER_ID, get=get) == "requester@example.com"
    [(url, kwargs)] = calls
    assert url == f"https://fake-project.supabase.co/auth/v1/admin/users/{USER_ID}"
    assert kwargs["headers"] == {"apikey": "sb_secret_fake-server-key"}   # 새 비밀 키는 JWT가 아니라 apikey 머리글에만
    assert kwargs["timeout"] == 10


def test_get_user_email_rejects_non_uuid_without_calling():
    with pytest.raises(MailError):
        get_user_email("../admin/users", get=lambda url, **kw: pytest.fail("부르면 안 됨"))


@pytest.mark.parametrize("get", [
    lambda url, **kw: response(404, {"msg": "User not found"}),
    lambda url, **kw: response(200, {"id": USER_ID}),   # 이메일 없음
    lambda url, **kw: (_ for _ in ()).throw(httpx.ReadTimeout("가짜 시간 초과")),
])
def test_get_user_email_failure_raises_mail_error(get):
    with pytest.raises(MailError):
        get_user_email(USER_ID, get=get)


def test_get_user_email_logs_never_contain_user_id(caplog):
    # 실제 httpx 요청 경로를 지나게 한다(MockTransport, 네트워크 0). 앱 시작(create_app)을 거친 뒤 INFO 이상 모든 로그를 본다
    import logging

    from app.web import create_app

    create_app()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"id": USER_ID, "email": "requester@example.com"}))
    with httpx.Client(transport=transport) as client, caplog.at_level(logging.INFO):
        assert get_user_email(USER_ID, get=client.get) == "requester@example.com"
    assert USER_ID not in caplog.text and "requester@example.com" not in caplog.text
