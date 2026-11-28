"""Supabase 깨우기를 실제 Supabase에 대고 확인한다(2차 Task 11 ③ 후속, OpenAI 비용 0).

운영 /api/wake가 비밀 값 확인은 통과했지만 Supabase가 403("permission denied for table model_requests")을 돌려줘
502로 끝났다(service_role에 이 표 SELECT 권한이 없음). 흉내 응답 테스트(test_wake.py)로는 알 수 없어서,
로컬 .env의 SUPABASE_URL·SUPABASE_SERVICE_KEY로 ping_supabase()를 그대로 불러 REST 200(예외 없음)인지 본다.
키·주소는 출력하지 않는다: 실패 문구에는 WakeError의 이유 코드(rest_<상태숫자> 등)만 넣는다.
"""
import os

import pytest

from app.core.config import get_settings
from app.wake.ping import WakeError, ping_supabase
from ingest.__main__ import load_env

pytestmark = pytest.mark.integration


def test_ping_supabase_reads_one_row_with_service_key():
    load_env()  # 로컬 .env를 읽는다(값은 출력하지 않음)
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")):
        pytest.skip("SUPABASE_URL·SUPABASE_SERVICE_KEY가 없으면 깨우기 실제 테스트를 건너뛴다")
    get_settings.cache_clear()  # 다른 테스트가 바꾼 설정이 남지 않게 .env 값으로 다시 읽는다
    try:
        ping_supabase()
    except WakeError as e:
        pytest.fail(f"ping_supabase 실패: reason={e}", pytrace=False)
    finally:
        get_settings.cache_clear()
