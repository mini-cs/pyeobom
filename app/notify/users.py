"""요청자 이메일 찾기: Supabase 관리 API(비밀 키). 이메일은 Supabase Auth에만 있고 요청 표에는 없다(Global 2)."""
import uuid

import httpx

from app.core.config import get_settings
from app.notify.mail import TIMEOUT_S, MailError


def get_user_email(user_id: str, *, get=httpx.get) -> str:
    try:
        uid = str(uuid.UUID(str(user_id)))  # 주소 경로에 그대로 넣으므로 uuid 모양만 받는다
    except ValueError:
        raise MailError("bad_user_id") from None
    s = get_settings()
    # 새 비밀 키(sb_secret_)는 JWT가 아니라 apikey 머리글에만 넣는다(Supabase 문서 API keys, tests/requests와 같음)
    try:
        res = get(f"{s.supabase_url}/auth/v1/admin/users/{uid}", headers={"apikey": s.supabase_service_key},
                  timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        raise MailError(type(e).__name__) from None
    email = res.json().get("email") if res.status_code == 200 else None
    if not email:
        raise MailError(f"user_lookup_{res.status_code}")
    return email
