"""Supabase 깨우기: 요청 표를 1줄 읽고 결과는 버린다(2차 Task 11 ③). 무료 프로젝트가 활동 부족으로 멈추지 않게.

실패는 WakeError(이유 코드)로만 알린다: not_configured · rest_<상태숫자> · <httpx 예외 클래스 이름>.
키·주소·응답 본문은 이유에 넣지 않는다.
"""
import httpx

from app.core.config import get_settings

TIMEOUT_S = 10


class WakeError(Exception):
    """str(e)가 이유 코드."""


def ping_supabase(*, get=httpx.get) -> None:
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_key):
        raise WakeError("not_configured")
    # 새 비밀 키(sb_secret_)는 JWT가 아니라 apikey 머리글에만 넣는다(app/notify/users.py와 같음)
    try:
        res = get(f"{s.supabase_url}/rest/v1/model_requests", params={"select": "id", "limit": "1"},
                  headers={"apikey": s.supabase_service_key}, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        raise WakeError(type(e).__name__) from None
    if res.status_code != 200:
        raise WakeError(f"rest_{res.status_code}")
