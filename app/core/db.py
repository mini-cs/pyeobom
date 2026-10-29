import psycopg
from pgvector.psycopg import register_vector

from app.core.config import get_settings
from app.core.errors import make_error


def get_conn() -> psycopg.Connection:
    url = get_settings().database_url
    if not url:
        raise make_error("DB_UNAVAILABLE")
    try:
        conn = psycopg.connect(url, connect_timeout=10)
        register_vector(conn)  # vector 확장이 없으면(스키마 미실행) 여기서 실패한다
        return conn
    except Exception:
        raise make_error("DB_UNAVAILABLE") from None  # 원인 메시지에 접속 주소가 섞일 수 있어 끊는다
