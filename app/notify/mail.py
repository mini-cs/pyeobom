"""Resend 보내기 API(계획 Task 7). 실패·시간 초과는 모두 MailError로 바꾼다(메시지에 주소·키를 넣지 않음)."""
import httpx

from app.core.config import get_settings

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_S = 10


class MailError(Exception):
    """메일을 보내지 못함(받는 사람 찾기 실패 포함). 알림 주소는 502로 답한다."""


def send_mail(to: str, subject: str, text: str, *, reply_to: str | None = None, post=httpx.post) -> None:
    s = get_settings()
    if not (s.resend_api_key and s.mail_from):
        raise MailError("not_configured")
    body = {"from": s.mail_from, "to": [to], "subject": subject, "text": text}
    if reply_to:
        body["reply_to"] = [reply_to]
    try:
        res = post(RESEND_URL, headers={"Authorization": f"Bearer {s.resend_api_key}"}, json=body, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:  # 시간 초과·연결 실패
        raise MailError(type(e).__name__) from None
    if res.status_code >= 300:
        raise MailError(f"resend_{res.status_code}")
