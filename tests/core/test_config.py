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


def test_settings_dimensions_from_env(monkeypatch):  # 임베딩 모델 바꾸기(v1.9) Task 1: "" → None, "1536" → 1536
    monkeypatch.setenv("OPENAI_EMBED_DIMENSIONS", "")
    get_settings.cache_clear()
    assert get_settings().openai_embed_dimensions is None
    monkeypatch.delenv("OPENAI_EMBED_DIMENSIONS")
    get_settings.cache_clear()
    assert get_settings().openai_embed_dimensions is None
    monkeypatch.setenv("OPENAI_EMBED_DIMENSIONS", "1536")
    get_settings.cache_clear()
    assert get_settings().openai_embed_dimensions == 1536
    get_settings.cache_clear()


def test_chunk_context_settings_from_env(monkeypatch):  # 조각 설명 붙이기(v1.95) Task 1: 없으면 꺼짐("")·추론 low
    monkeypatch.delenv("CHUNK_CONTEXT_MODEL", raising=False)
    monkeypatch.delenv("CHUNK_CONTEXT_REASONING_EFFORT", raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert (s.chunk_context_model, s.chunk_context_reasoning_effort) == ("", "low")
    monkeypatch.setenv("CHUNK_CONTEXT_MODEL", "gpt-6-luna")
    monkeypatch.setenv("CHUNK_CONTEXT_REASONING_EFFORT", "medium")
    get_settings.cache_clear()
    s = get_settings()
    assert (s.chunk_context_model, s.chunk_context_reasoning_effort) == ("gpt-6-luna", "medium")
    get_settings.cache_clear()



def test_refine_settings_from_env(monkeypatch):  # 첫 질문 다듬기(v1.96): 없으면 꺼짐("")·none·3초·300
    for key in ("REFINE_MODEL", "REFINE_REASONING_EFFORT", "REFINE_TIMEOUT_S", "REFINE_MAX_OUTPUT_TOKENS"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert (s.refine_model, s.refine_reasoning_effort, s.refine_timeout_s, s.refine_max_output_tokens) == ("", "none", 3.0, 300)
    for key, value in (("REFINE_MODEL", "gpt-6-luna"), ("REFINE_REASONING_EFFORT", "low"), ("REFINE_TIMEOUT_S", "2.5"),
                       ("REFINE_MAX_OUTPUT_TOKENS", "200")):
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    s = get_settings()
    assert (s.refine_model, s.refine_reasoning_effort, s.refine_timeout_s, s.refine_max_output_tokens) == ("gpt-6-luna", "low", 2.5, 200)
    get_settings.cache_clear()


SUPABASE_MAIL_ENV = {  # 2차 Task 5: 값은 모두 가짜
    "SUPABASE_URL": "https://fake-project.supabase.co",
    "SUPABASE_ANON_KEY": "sb_publishable_fake-public-key",
    "SUPABASE_SERVICE_KEY": "sb_secret_fake-server-key",
    "RESEND_API_KEY": "re_fake-resend-key",
    "NOTIFY_WEBHOOK_SECRET": "fake-webhook-secret",
    "OPERATOR_EMAIL": "operator@example.com",
    "MAIL_FROM": "펴봄 <noreply@mail.pyeobom.help>",
}


def test_supabase_and_mail_settings_from_env(monkeypatch):
    for key, value in SUPABASE_MAIL_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    s = get_settings()
    assert (s.supabase_url, s.supabase_anon_key, s.supabase_service_key, s.resend_api_key, s.notify_webhook_secret,
            s.operator_email, s.mail_from) == tuple(SUPABASE_MAIL_ENV.values())
    get_settings.cache_clear()


def test_supabase_and_mail_settings_default_empty(monkeypatch):
    for key in SUPABASE_MAIL_ENV:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert (s.supabase_url, s.supabase_anon_key, s.supabase_service_key, s.resend_api_key, s.notify_webhook_secret,
            s.operator_email, s.mail_from) == ("",) * 7
    get_settings.cache_clear()
