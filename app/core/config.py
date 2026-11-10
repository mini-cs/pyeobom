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


@lru_cache
def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        openai_api_key=env("OPENAI_API_KEY", ""),
        database_url=env("DATABASE_URL", ""),
        openai_embed_model=env("OPENAI_EMBED_MODEL", ""),
        openai_chat_model=env("OPENAI_CHAT_MODEL", ""),
        embed_dim=int(env("EMBED_DIM") or 0),
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
    )
