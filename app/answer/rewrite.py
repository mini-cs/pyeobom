"""질문 바꾸기 단계(방법 A): 앞 대화를 참고해 이어지는 질문을 혼자 읽어도 되는 한 문장으로 바꾼다.

실패(시간 초과·API 오류·형식 오류)하면 원래 질문으로 진행한다. 서비스를 멈추지 않는다.
"""
import json
import logging
from dataclasses import dataclass

import openai

from app.answer.prompting import PROMPTS, _data
from app.core.config import Settings

log = logging.getLogger(__name__)
MAX_LEN = 500  # 1차 질문 길이 상한과 같다
PROMPT_FILE = "rewrite_v2.txt"  # v1은 기록용(docs/프롬프트.md 변경 기록)

REWRITE_FORMAT = {
    "type": "json_schema",
    "name": "rewrite",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"standalone_question": {"type": "string"}},
        "required": ["standalone_question"],
        "additionalProperties": False,
    },
}


@dataclass(frozen=True)
class RewriteResult:
    text: str
    used: bool
    reason: str  # ok · no_history · timeout · invalid_output · api_error


def build_rewrite_messages(question: str, history: list[dict]) -> list[dict]:
    system = (PROMPTS / PROMPT_FILE).read_text(encoding="utf-8")
    turns = "\n".join(f"<turn><question>{_data(t['question'])}</question><answer>{_data(t['answer'])}</answer></turn>"
                      for t in history)
    user = f"<history>\n{turns}\n</history>\n<question>{_data(question)}</question>"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse(text: str) -> str | None:
    try:
        value = json.loads(text).get("standalone_question")
    except (ValueError, AttributeError):
        return None
    value = value.strip() if isinstance(value, str) else ""
    return value if 0 < len(value) <= MAX_LEN else None


def rewrite_question(question: str, history: list[dict], model_name: str, settings: Settings, client=None) -> RewriteResult:
    if not history:
        return RewriteResult(question, False, "no_history")
    try:
        client = client or openai.OpenAI(api_key=settings.openai_api_key, timeout=settings.rewrite_timeout_s, max_retries=0)
        resp = client.responses.create(
            model=model_name,
            input=build_rewrite_messages(question, history),
            max_output_tokens=settings.rewrite_max_output_tokens,
            reasoning={"effort": settings.reasoning_effort},
            text={"format": REWRITE_FORMAT},
        )
    except (TimeoutError, openai.APITimeoutError):
        return RewriteResult(question, False, "timeout")
    except Exception as e:
        log.warning("질문 바꾸기 실패: %s", type(e).__name__)  # 메시지에 키가 섞일 수 있어 종류만 남긴다
        return RewriteResult(question, False, "api_error")
    rewritten = _parse(resp.output_text or "")
    return RewriteResult(rewritten, True, "ok") if rewritten else RewriteResult(question, False, "invalid_output")
