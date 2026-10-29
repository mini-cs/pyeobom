import os

import pytest

from app.core.config import get_settings
from ingest.__main__ import load_env


@pytest.fixture(scope="module")
def conn():
    load_env()  # 로컬 .env의 접속 주소·키를 읽는다(값은 출력하지 않음)
    if not os.environ.get("DATABASE_URL") or not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("DATABASE_URL·OPENAI_API_KEY가 없으면 Neon 검색 테스트를 건너뛴다")
    get_settings.cache_clear()
    from app.core.db import get_conn
    with get_conn() as c:
        yield c


@pytest.fixture(scope="module")
def docs_of(conn):
    def _docs(model_id: str) -> set[str]:
        return {r[0] for r in conn.execute("SELECT doc_id FROM document_models WHERE model_id = %s", (model_id,))}
    return _docs
