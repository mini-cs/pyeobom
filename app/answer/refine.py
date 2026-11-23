"""첫 질문 다듬기(v1.96): 앞 대화가 없는 질문을 설명서 검색용 한 문장으로 다듬는다. 다듬은 문장은 검색에만 쓴다.

실패(시간 초과·API 오류·형식 오류)하거나 원래 질문과 같으면 원래 질문만으로 검색한다. 다시 시도하지 않는다.
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field

import openai

from app.answer.prompting import PROMPTS, _data
from app.core.config import Settings

log = logging.getLogger(__name__)
PROMPT_FILE = "refine_v1.txt"
PROMPT_SHA256 = "e3f297b726df7b359c830c79c9119b8f8973f322b8d8a5de486ecd7931c562a3"  # 측정 전 고정(결정기록 039)
MAX_REFINED_LEN = 200

REFINE_FORMAT = {
    "type": "json_schema",
    "name": "refine",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"search_question": {"type": "string"}},
        "required": ["search_question"],
        "additionalProperties": False,
    },
}


@dataclass(frozen=True)
class RefineResult:
    text: str
    used: bool
    reason: str  # ok · same · off · timeout · api_error · invalid_output · other_brand
    usage: dict = field(default_factory=dict, compare=False)  # 토큰 수(입력·출력·추론). 추적에는 숫자로만


def prompt_sha256() -> str:
    return hashlib.sha256((PROMPTS / PROMPT_FILE).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build_refine_messages(question: str, product: str) -> list[dict]:
    system = (PROMPTS / PROMPT_FILE).read_text(encoding="utf-8")
    user = f"<product>{_data(product)}</product>\n<question>{_data(question)}</question>"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse(text: str) -> str | None:
    try:
        value = json.loads(text).get("search_question")
    except (ValueError, AttributeError):
        return None
    value = " ".join(value.split()) if isinstance(value, str) else ""
    return value if 0 < len(value) <= MAX_REFINED_LEN else None


def refine_question(question: str, product: str, model_name: str, settings: Settings, client=None) -> RefineResult:
    try:
        client = client or openai.OpenAI(api_key=settings.openai_api_key, timeout=settings.refine_timeout_s, max_retries=0)
        resp = client.responses.create(
            model=model_name,
            input=build_refine_messages(question, product),
            max_output_tokens=settings.refine_max_output_tokens,
            reasoning={"effort": settings.refine_reasoning_effort},
            text={"format": REFINE_FORMAT},
        )
    except (TimeoutError, openai.APITimeoutError):
        return RefineResult(question, False, "timeout")
    except Exception as e:
        log.warning("첫 질문 다듬기 실패: %s", type(e).__name__)  # 메시지에 키가 섞일 수 있어 종류만 남긴다
        return RefineResult(question, False, "api_error")
    u = getattr(resp, "usage", None)
    usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
             "reasoning_tokens": getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", 0) or 0} if u else {}
    refined = _parse(resp.output_text or "")
    if refined is None:
        return RefineResult(question, False, "invalid_output", usage)
    if refined == " ".join(question.split()):
        return RefineResult(question, False, "same", usage)
    return RefineResult(refined, True, "ok", usage)
