import pytest

from app.core import observability


@pytest.fixture(autouse=True)
def _tracing_off(monkeypatch):
    """테스트에서는 Langfuse 추적을 강제로 끈다(.env 키가 올라와도 외부로 보내지 않음).

    추적을 확인하는 테스트는 자기 fixture에서 _make_client를 가짜로 다시 바꾼다(tests/core/test_observability.py).
    """
    monkeypatch.setattr(observability, "_make_client", lambda: None)
