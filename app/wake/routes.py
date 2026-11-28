"""Supabase 깨우기 주소 GET /api/wake(2차 Task 11 ③): Vercel Cron이 하루 3번 부른다(vercel.json crons).

Vercel은 CRON_SECRET이 있으면 Authorization: Bearer <값>으로 보낸다. 맞을 때만 Supabase를 부른다.
"""
import hmac
import logging
from collections.abc import Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.wake.ping import WakeError, ping_supabase

log = logging.getLogger(__name__)
router = APIRouter()


def get_wake_ping() -> Callable[[], None]:
    return ping_supabase


def _authorized(request: Request) -> bool:
    secret = get_settings().cron_secret
    given = request.headers.get("authorization", "")
    # 설정이 비면 모두 거절한다(빈 "Bearer "로 누구나 Supabase를 부를 수 없게). 알림 주소 _authorized와 같은 모양
    return bool(secret) and hmac.compare_digest(given.encode(), f"Bearer {secret}".encode())


@router.get("/api/wake")
async def wake(request: Request, ping: Callable[[], None] = Depends(get_wake_ping)):
    if not _authorized(request):  # 머리글 값은 로그에 남기지 않는다
        log.info("wake: result=unauthorized")
        return JSONResponse(status_code=401, content={"error_code": "UNAUTHORIZED", "message": "인증이 필요해요"})
    try:
        await run_in_threadpool(ping)  # 동기 httpx(최대 10초)라 스레드에서 돌려 이벤트 루프를 막지 않는다
    except WakeError as e:
        log.error("wake 실패: reason=%s", e)
        return JSONResponse(status_code=502,
                            content={"error_code": "WAKE_FAILED", "message": "깨우지 못했어요", "reason": str(e)})
    log.info("wake: result=ok")
    return {"ok": True}
