from app.core import observability


def test_tracing_is_forced_off_in_tests_even_with_keys(monkeypatch):
    # 통합 테스트의 load_env()가 .env의 Langfuse 키를 환경 변수에 올려도 테스트 기록이 외부로 나가면 안 된다
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    assert observability.get_tracer()._client is None
