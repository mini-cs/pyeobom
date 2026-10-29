import pytest

from app.core.config import get_settings
from app.core.db import get_conn
from app.core.errors import AppError


@pytest.mark.parametrize("url", ["", "postgresql://user:secret-pw@127.0.0.1:1/nodb"])
def test_unreachable_db_is_db_unavailable_without_leaking_url(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    with pytest.raises(AppError) as e:
        get_conn()
    assert e.value.code == "DB_UNAVAILABLE" and e.value.__cause__ is None
    assert "secret-pw" not in str(e.value) and "secret-pw" not in e.value.message
    get_settings.cache_clear()
