"""알림 주소 POST /api/notify(계획 Task 7): Supabase 데이터베이스 웹훅 → 운영자·요청자 메일(Resend).

INSERT → 운영자. UPDATE → 상태가 바뀌었고 새 상태가 "추가됨"·"추가 어려움"일 때만 요청자.
"추가됨"인데 그 모델이 이 배포의 models.json에 없으면 보내지 않는다(Review Focus 5).
다시 보내기는 표 화면에서 상태를 "확인 중"으로 되돌렸다가 다시 바꾼다(설계 8.2-4).
"""
import hmac
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.catalog.registry import load_models
from app.core.config import get_settings
from app.notify.mail import MailError, send_mail
from app.notify.messages import operator_message, requester_message
from app.notify.users import get_user_email

log = logging.getLogger(__name__)
router = APIRouter()
FINAL = ("추가됨", "추가 어려움")


@dataclass
class NotifyDeps:
    send_mail: Callable
    get_user_email: Callable[[str], str]
    deployed_models: Callable[[], dict[str, str]]  # 이 배포의 모델 id → 이름


def get_notify_deps() -> NotifyDeps:
    return NotifyDeps(send_mail=send_mail, get_user_email=get_user_email,
                      deployed_models=lambda: {m["id"]: m["name"] for m in load_models()})


def _authorized(request: Request) -> bool:
    secret = get_settings().notify_webhook_secret
    given = request.headers.get("x-pyeobom-webhook-secret", "")
    # 설정이 비면 모두 거절한다(compare_digest("", "")는 참)
    return bool(secret) and hmac.compare_digest(given.encode(), secret.encode())


def _decide(body: dict, deps: NotifyDeps) -> tuple[str, str, str | None]:
    """(보낼 곳, 이유, 받는 사람 user_id) — 메일은 아직 보내지 않는다."""
    if body.get("table") != "model_requests":
        return "none", "other_table", None
    record, old = body.get("record") or {}, body.get("old_record") or {}
    if body.get("type") == "INSERT":
        return "operator", "inserted", None
    if body.get("type") != "UPDATE":
        return "none", "ignored_type", None
    status = record.get("status")
    if old.get("status") == status:
        return "none", "status_unchanged", None
    if status not in FINAL:
        return "none", "status_not_final", None
    if status == "추가됨" and record.get("model_id") not in deps.deployed_models():
        return "none", "not_deployed", None
    return "requester", "status_changed", record.get("user_id")


@router.post("/api/notify")
async def notify(request: Request, deps: NotifyDeps = Depends(get_notify_deps)):
    if not _authorized(request):  # 비밀 값을 먼저 보고, 맞을 때만 본문을 읽는다
        return JSONResponse(status_code=401, content={"error_code": "UNAUTHORIZED", "message": "인증이 필요해요"})
    try:
        body = json.loads(await request.body())
        if not isinstance(body, dict):
            raise ValueError("not an object")
    except ValueError:
        return JSONResponse(status_code=400, content={"error_code": "INVALID_REQUEST", "message": "본문을 읽지 못했어요"})
    record = body.get("record") or {}
    request_id, status = record.get("id"), record.get("status")
    sent, reason, user_id = _decide(body, deps)
    try:  # 문구를 먼저 만든다: 필요한 필드가 빠졌으면 500이 아니라 400(메일·조회 없음)
        message = None
        if sent == "operator":
            message = operator_message(record)
        elif sent == "requester":
            message = requester_message(record)
            if not user_id:
                raise KeyError("user_id")
    except (KeyError, TypeError):
        return JSONResponse(status_code=400, content={"error_code": "INVALID_REQUEST", "message": "필요한 값이 빠졌어요"})
    operator = get_settings().operator_email
    try:
        if sent != "none" and not operator:
            raise MailError("not_configured")
        # 메일 보내기·관리 API 조회는 동기 httpx(최대 10초)라 스레드에서 돌려 서버(이벤트 루프)를 막지 않는다
        if sent == "operator":
            await run_in_threadpool(deps.send_mail, operator, *message)
        elif sent == "requester":
            email = await run_in_threadpool(deps.get_user_email, user_id)
            await run_in_threadpool(deps.send_mail, email, *message, reply_to=operator)
    except MailError as e:
        # 로그에는 요청 id·status·결과만(이메일·모델명·키 없음). MailError 메시지에도 주소를 넣지 않는다(정해진 코드만)
        log.error("notify 실패: request_id=%s status=%s result=mail_failed(%s)", request_id, status, e)
        return JSONResponse(status_code=502,
                            content={"error_code": "MAIL_FAILED", "message": "메일을 보내지 못했어요", "reason": str(e)})
    log.info("notify: request_id=%s status=%s result=%s(%s)", request_id, status, sent, reason)
    return {"sent": sent, "reason": reason}
