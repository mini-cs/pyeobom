"""알림 주소 /api/notify(계획 Task 7). 메일·관리 API는 가짜 함수로 바꿔 네트워크·실제 메일 0. 값은 모두 가짜."""
import asyncio
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.notify.mail import MailError
from app.notify.routes import NotifyDeps, get_notify_deps
from app.web import create_app

SECRET = "fake-webhook-secret"
OPERATOR = "operator@example.com"
REQUESTER = "requester@example.com"
USER_ID = "00000000-0000-4000-8000-000000000001"
DEPLOYED = {"washer-fake-a": "가짜 세탁기 A"}   # 이 배포의 models.json에 있는 모델(가짜)

RECORD = {"id": 7, "user_id": USER_ID, "category": "dryer", "brand": "가짜브랜드", "model_text": "DV90-FAKE1",
          "model_key": "DV90FAKE1", "status": "대기", "reason": None, "model_id": None,
          "created_at": "2026-11-25T05:03:00.123456+00:00", "updated_at": "2026-11-25T05:03:00.123456+00:00"}


def insert_body(record=RECORD):
    # Supabase 데이터베이스 웹훅 본문(INSERT): type·table·schema·record·old_record(null)
    return {"type": "INSERT", "table": "model_requests", "schema": "public", "record": record, "old_record": None}


def update_body(old, new):
    return {"type": "UPDATE", "table": "model_requests", "schema": "public", "record": {**RECORD, **new},
            "old_record": {**RECORD, **old}}


class Fake:
    def __init__(self):
        self.mails = []
        self.lookups = []
        self.fail = None   # 보내기·찾기에서 던질 예외

    def send_mail(self, to, subject, text, *, reply_to=None):
        if self.fail:
            raise self.fail
        self.mails.append({"to": to, "subject": subject, "text": text, "reply_to": reply_to})

    def get_user_email(self, user_id):
        self.lookups.append(user_id)
        if self.fail:
            raise self.fail
        return REQUESTER


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("OPERATOR_EMAIL", OPERATOR)
    get_settings.cache_clear()
    f = Fake()
    app = create_app()
    app.dependency_overrides[get_notify_deps] = lambda: NotifyDeps(
        send_mail=f.send_mail, get_user_email=f.get_user_email, deployed_models=lambda: DEPLOYED)
    f.client = TestClient(app)
    yield f
    get_settings.cache_clear()


def post(fake, body, secret=SECRET):
    headers = {} if secret is None else {"x-pyeobom-webhook-secret": secret}
    return fake.client.post("/api/notify", json=body, headers=headers)


def test_rejects_missing_or_wrong_secret(fake):
    for secret in (None, "", "wrong-secret"):
        assert post(fake, insert_body(), secret).status_code == 401
    # 비밀 값이 틀리면 본문을 읽지 않는다: 깨진 본문이어도 401(본문 오류 400·422가 아님)
    res = fake.client.post("/api/notify", content=b"{not json", headers={"x-pyeobom-webhook-secret": "wrong-secret"})
    assert res.status_code == 401
    assert fake.mails == [] and fake.lookups == []


def test_rejects_when_secret_not_configured(fake, monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK_SECRET", "")   # hmac.compare_digest("", "")는 참이라 따로 막아야 한다
    get_settings.cache_clear()
    for secret in (None, "", "anything"):
        assert post(fake, insert_body(), secret).status_code == 401
    assert fake.client.post("/api/notify", content=b"{not json", headers={"x-pyeobom-webhook-secret": ""}).status_code == 401
    assert fake.mails == []


def test_insert_sends_operator_mail_without_requester_email(fake):
    res = post(fake, insert_body())
    assert res.status_code == 200 and res.json()["sent"] == "operator"
    assert fake.lookups == []   # 운영자 메일에는 요청자를 찾지 않는다
    [mail] = fake.mails
    assert mail["to"] == OPERATOR
    assert REQUESTER not in mail["text"] and USER_ID not in mail["text"] and USER_ID not in mail["subject"]


def test_status_added_sends_requester_mail_with_reply_to_operator(fake):
    res = post(fake, update_body({"status": "확인 중"}, {"status": "추가됨", "model_id": "washer-fake-a"}))
    assert res.status_code == 200 and res.json()["sent"] == "requester"
    assert fake.lookups == [USER_ID]
    [mail] = fake.mails
    assert mail["to"] == REQUESTER and mail["reply_to"] == OPERATOR
    assert mail["subject"] == "요청하신 모델이 펴봄에 추가됐어요"


def test_status_hard_sends_reason(fake):
    res = post(fake, update_body({"status": "확인 중"}, {"status": "추가 어려움", "reason": "공식 설명서를 찾지 못했어요(테스트)"}))
    assert res.status_code == 200 and res.json()["sent"] == "requester"
    [mail] = fake.mails
    assert mail["to"] == REQUESTER and mail["reply_to"] == OPERATOR
    assert "공식 설명서를 찾지 못했어요(테스트)" in mail["text"]


def test_update_same_status_sends_nothing(fake):
    # 같은 웹훅이 다시 오거나 같은 값으로 다시 저장해도 메일은 한 번(바뀐 경우에만)
    res = post(fake, update_body({"status": "추가됨", "model_id": "washer-fake-a"}, {"status": "추가됨", "model_id": "washer-fake-a"}))
    assert res.status_code == 200 and res.json() == {"sent": "none", "reason": "status_unchanged"}
    assert fake.mails == [] and fake.lookups == []


def test_update_other_column_sends_nothing(fake):
    res = post(fake, update_body({"status": "추가 어려움", "reason": "예전 사유(테스트)"},
                                 {"status": "추가 어려움", "reason": "고친 사유(테스트)"}))
    assert res.json() == {"sent": "none", "reason": "status_unchanged"}
    assert fake.mails == []


def test_update_to_checking_sends_nothing(fake):
    res = post(fake, update_body({"status": "대기"}, {"status": "확인 중"}))
    assert res.json() == {"sent": "none", "reason": "status_not_final"}
    assert fake.mails == []


def test_added_but_not_deployed_sends_nothing(fake):
    # "추가됨"을 배포 전에 눌렀을 때: 이 배포의 models.json에 그 모델이 없으면 보내지 않는다(Review Focus 5)
    res = post(fake, update_body({"status": "확인 중"}, {"status": "추가됨", "model_id": "dryer-not-deployed"}))
    assert res.json() == {"sent": "none", "reason": "not_deployed"}
    assert fake.mails == [] and fake.lookups == []


def test_other_table_sends_nothing(fake):
    res = post(fake, {**insert_body(), "table": "other_table"})
    assert res.json() == {"sent": "none", "reason": "other_table"}
    assert fake.mails == []


def test_mail_failure_returns_502_and_logs_no_address(fake, caplog):
    fake.fail = MailError("가짜 실패(테스트)")
    with caplog.at_level(logging.INFO, logger="app.notify.routes"):
        res = post(fake, update_body({"status": "확인 중"}, {"status": "추가됨", "model_id": "washer-fake-a"}))
    assert res.status_code == 502 and res.json()["error_code"] == "MAIL_FAILED"
    assert "request_id=7" in caplog.text and "status=추가됨" in caplog.text   # 요청 id·status·결과만
    for secret in (REQUESTER, OPERATOR, SECRET, "DV90-FAKE1", "가짜브랜드", USER_ID):
        assert secret not in caplog.text and secret not in res.text


def test_operator_mail_failure_returns_502(fake):
    fake.fail = MailError("가짜 시간 초과(테스트)")
    res = post(fake, insert_body())
    assert res.status_code == 502 and OPERATOR not in res.text


def test_success_log_has_id_status_result_only(fake, caplog):
    with caplog.at_level(logging.INFO, logger="app.notify.routes"):
        post(fake, update_body({"status": "확인 중"}, {"status": "추가됨", "model_id": "washer-fake-a"}))
    assert "requester" in caplog.text
    for secret in (REQUESTER, OPERATOR, "DV90-FAKE1", "가짜브랜드", USER_ID, "washer-fake-a"):
        assert secret not in caplog.text



# ── Step 6 지적 처리(2026-11-25) ──
def test_mail_and_lookup_run_off_event_loop(fake):
    # ① 메일 보내기·관리 API 조회(동기 httpx, 최대 10초)는 이벤트 루프 밖(스레드)에서 돈다
    where = []

    def on_loop():
        try:
            asyncio.get_running_loop()
            return "event_loop"
        except RuntimeError:
            return "thread"

    send, lookup = fake.send_mail, fake.get_user_email
    fake.send_mail = lambda *a, **k: (where.append(("send", on_loop())), send(*a, **k))[1]
    fake.get_user_email = lambda uid: (where.append(("lookup", on_loop())), lookup(uid))[1]
    res = post(fake, update_body({"status": "확인 중"}, {"status": "추가됨", "model_id": "washer-fake-a"}))
    assert res.status_code == 200
    assert where == [("lookup", "thread"), ("send", "thread")]


def test_operator_email_not_configured_returns_502_not_configured(fake, monkeypatch):
    # ⑥ OPERATOR_EMAIL이 비면 보내지 않고 502 not_configured(Resend 422로 보이지 않게)
    monkeypatch.setenv("OPERATOR_EMAIL", "")
    get_settings.cache_clear()
    res = post(fake, insert_body())
    assert res.status_code == 502 and res.json()["reason"] == "not_configured"
    assert fake.mails == []


@pytest.mark.parametrize("body", [
    insert_body({k: v for k, v in RECORD.items() if k != "brand"}),
    {"type": "UPDATE", "table": "model_requests", "schema": "public",
     "record": {k: v for k, v in {**RECORD, "status": "추가됨", "model_id": "washer-fake-a"}.items() if k != "user_id"},
     "old_record": {**RECORD, "status": "확인 중"}},
])
def test_missing_record_field_returns_400(fake, body):
    # ⑥ 웹훅 본문에 필요한 필드가 빠지면 500이 아니라 400, 메일·조회 없음
    res = post(fake, body)
    assert res.status_code == 400
    assert fake.mails == [] and fake.lookups == []
