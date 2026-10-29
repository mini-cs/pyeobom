from app.core.config import get_settings


def test_settings_read_env_names_from_env_example(monkeypatch):
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "300")
    monkeypatch.setenv("EMBED_DIM", "1536")
    monkeypatch.setenv("FORCE_FAIL", "true")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "medium")
    get_settings.cache_clear()
    s = get_settings()
    assert (s.max_output_tokens, s.embed_dim, s.force_fail, s.reasoning_effort) == (300, 1536, True, "medium")
    get_settings.cache_clear()


def test_settings_defaults(monkeypatch):
    for key in ("TOP_K", "MAX_QUESTION_LEN", "OPENAI_MAX_OUTPUT_TOKENS", "PROMPT_VERSION", "SEARCH_MODE", "FORCE_FAIL",
                "OPENAI_REASONING_EFFORT"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert (s.top_k, s.max_question_len, s.max_output_tokens, s.prompt_version, s.search_mode, s.force_fail) == (5, 500, 600, "v1", "vector", False)
    assert s.reasoning_effort == "low"   # 결정기록 017: v1은 low
    get_settings.cache_clear()
