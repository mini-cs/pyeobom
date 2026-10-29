import logging

import openai

from app.core.config import Settings
from app.core.errors import make_error

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20
RETRYABLE_429 = {None, "slow_down"}  # 결정기록 017: 일반 속도 제한만 재시도, 한도·크레딧·모르는 코드는 재시도 없음

# AI 출력 형식(app/answer/check.py가 검증). strict json_schema로 형식부터 강제한다
ANSWER_FORMAT = {
    "type": "json_schema",
    "name": "answer",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "found": {"type": "boolean"},
            "answer": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"chunk_id": {"type": "integer"}, "quote": {"type": "string"}},
                    "required": ["chunk_id", "quote"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["found", "answer", "citations"],
        "additionalProperties": False,
    },
}


def complete_json(messages: list[dict], settings: Settings, client=None) -> str:
    if settings.force_fail:
        raise make_error("AI_TIMEOUT")  # 시연용 실패 흉내(운영 배포에서는 켜지 않음)
    if not settings.openai_api_key:
        raise make_error("SERVICE_UNAVAILABLE")
    client = client or openai.OpenAI(api_key=settings.openai_api_key, timeout=TIMEOUT_SECONDS, max_retries=0)
    error = "SERVICE_UNAVAILABLE"
    for _ in range(2):  # 처음 1번 + 재시도 1번
        try:
            resp = client.responses.create(
                model=settings.openai_chat_model,
                input=messages,
                max_output_tokens=settings.max_output_tokens,
                reasoning={"effort": settings.reasoning_effort},
                text={"format": ANSWER_FORMAT},
            )
            return resp.output_text
        except (TimeoutError, openai.APITimeoutError):
            error = "AI_TIMEOUT"
        except openai.RateLimitError as e:
            log.warning("OpenAI 429 code=%s", e.code)  # 코드 값만 남긴다(키·본문 없음)
            if e.code not in RETRYABLE_429:
                raise make_error("SERVICE_UNAVAILABLE") from None
            error = "SERVICE_UNAVAILABLE"
        except openai.APIStatusError as e:
            if e.status_code < 500:
                log.warning("OpenAI status=%s", e.status_code)
                raise make_error("SERVICE_UNAVAILABLE") from None
            error = "SERVICE_UNAVAILABLE"
        except Exception as e:
            log.warning("OpenAI 호출 실패: %s", type(e).__name__)  # 메시지에 키가 섞일 수 있어 종류만 남긴다
            raise make_error("SERVICE_UNAVAILABLE") from None
    raise make_error(error) from None
