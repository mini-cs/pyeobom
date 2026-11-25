import os
from dataclasses import dataclass
from functools import lru_cache

# 앞 대화 답: 상한까지 받고(넘으면 INVALID_REQUEST), 가린 뒤 질문 바꾸기에는 앞 N자만 보낸다. 상한은 답변 출력 토큰 제한(600) x 4자 이상
MAX_HISTORY_ANSWER_LEN = 4000
HISTORY_ANSWER_KEEP_LEN = 1000


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    database_url: str
    openai_embed_model: str
    openai_chat_model: str
    embed_dim: int
    top_k: int = 5
    max_question_len: int = 500
    max_output_tokens: int = 600
    prompt_version: str = "v1"
    search_mode: str = "vector"
    force_fail: bool = False
    reasoning_effort: str = "low"
    rewrite_model: str = ""  # 비면 답변 모델(get_settings가 채움)
    rewrite_timeout_s: float = 5
    rewrite_max_output_tokens: int = 300  # 추론 토큰 포함. 실제 사용분만 과금되므로 여유 있게
    rewrite_reasoning_effort: str = "none"  # 계획 2 Task 6 채택(B): 같은 정확도에서 추론 토큰을 쓰지 않음(결정기록 023)
    openai_embed_dimensions: int | None = None  # 비면 임베딩 요청에 dimensions를 넣지 않는다(v1.9, 지금 운영 그대로)
    chunk_context_model: str = ""  # 조각 설명(v1.95)을 쓰는 모델. 비면 적재 때 설명을 붙이지 않는다(지금 운영). 답변 모델과 따로 고정
    chunk_context_reasoning_effort: str = "low"
    refine_model: str = ""  # 첫 질문 다듬기(v1.96) 모델. 비면 다듬지 않는다(지금 운영). 답변 모델과 따로 고정
    refine_reasoning_effort: str = "none"
    refine_timeout_s: float = 3.0
    refine_max_output_tokens: int = 300
    # 2차 요청 흐름(Task 5). 화면에 내려가는 것은 supabase_url·supabase_anon_key 둘뿐(/api/public-config)
    supabase_url: str = ""
    supabase_anon_key: str = ""  # 공개 키(sb_publishable_…)
    supabase_service_key: str = ""  # 서버 전용(sb_secret_…)
    resend_api_key: str = ""
    notify_webhook_secret: str = ""
    operator_email: str = ""
    mail_from: str = ""


@lru_cache
def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        openai_api_key=env("OPENAI_API_KEY", ""),
        database_url=env("DATABASE_URL", ""),
        openai_embed_model=env("OPENAI_EMBED_MODEL", ""),
        openai_chat_model=env("OPENAI_CHAT_MODEL", ""),
        embed_dim=int(env("EMBED_DIM") or 0),
        openai_embed_dimensions=int(env("OPENAI_EMBED_DIMENSIONS") or 0) or None,
        top_k=int(env("TOP_K") or 5),
        max_question_len=int(env("MAX_QUESTION_LEN") or 500),
        # .env.example은 OpenAI 쪽 이름(OPENAI_MAX_OUTPUT_TOKENS)을 쓴다
        max_output_tokens=int(env("OPENAI_MAX_OUTPUT_TOKENS") or 600),
        prompt_version=env("PROMPT_VERSION") or "v1",
        search_mode=env("SEARCH_MODE") or "vector",
        force_fail=env("FORCE_FAIL", "").strip().lower() in ("1", "true", "yes"),
        reasoning_effort=env("OPENAI_REASONING_EFFORT") or "low",
        rewrite_model=env("REWRITE_MODEL") or env("OPENAI_CHAT_MODEL", ""),
        rewrite_timeout_s=float(env("REWRITE_TIMEOUT_S") or 5),
        rewrite_max_output_tokens=int(env("REWRITE_MAX_OUTPUT_TOKENS") or 300),
        rewrite_reasoning_effort=env("REWRITE_REASONING_EFFORT") or "none",
        chunk_context_model=env("CHUNK_CONTEXT_MODEL", ""),
        chunk_context_reasoning_effort=env("CHUNK_CONTEXT_REASONING_EFFORT") or "low",
        refine_model=env("REFINE_MODEL", ""),
        refine_reasoning_effort=env("REFINE_REASONING_EFFORT") or "none",
        refine_timeout_s=float(env("REFINE_TIMEOUT_S") or 3),
        refine_max_output_tokens=int(env("REFINE_MAX_OUTPUT_TOKENS") or 300),
        supabase_url=env("SUPABASE_URL", ""),
        supabase_anon_key=env("SUPABASE_ANON_KEY", ""),
        supabase_service_key=env("SUPABASE_SERVICE_KEY", ""),
        resend_api_key=env("RESEND_API_KEY", ""),
        notify_webhook_secret=env("NOTIFY_WEBHOOK_SECRET", ""),
        operator_email=env("OPERATOR_EMAIL", ""),
        mail_from=env("MAIL_FROM", ""),
    )
