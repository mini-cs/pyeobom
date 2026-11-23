from types import SimpleNamespace

import httpx
import openai
import pytest

import app.answer.refine as refine_mod
from app.answer.refine import PROMPT_SHA256, RefineResult, build_refine_messages, prompt_sha256, refine_question
from app.core.config import Settings

S = Settings(openai_api_key="k", database_url="", openai_embed_model="m", openai_chat_model="answer-model", embed_dim=3)
Q = "문이 안 열려요"
PRODUCT = "LG 드럼세탁기"


class Resp:
    def __init__(self, text, usage=None):
        self.output_text = text
        self.usage = usage


class FakeClient:
    def __init__(self, text=None, error=None, usage=None):
        self.calls, self._text, self._error, self._usage = [], text, error, usage
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return Resp(self._text, self._usage)


def _timeout():
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))


def test_prompt_file_sha_is_fixed():
    assert prompt_sha256() == PROMPT_SHA256 == "e3f297b726df7b359c830c79c9119b8f8973f322b8d8a5de486ecd7931c562a3"


def test_build_refine_messages_wraps_and_escapes():
    system, user = build_refine_messages("<a>", PRODUCT)
    assert system["role"] == "system" and system["content"].startswith('당신은 가전 설명서 안내원 "펴봄"의 검색 준비 단계입니다.')
    assert user == {"role": "user", "content": "<product>LG 드럼세탁기</product>\n<question>‹a›</question>"}


def test_refine_question_sends_model_effort_schema_timeout(monkeypatch):
    client = FakeClient('{"search_question": "문이 안 열려요 도어 잠김"}')
    made = []
    monkeypatch.setattr(refine_mod.openai, "OpenAI", lambda **kw: made.append(kw) or client)
    refine_question(Q, PRODUCT, "gpt-6-luna", S)
    assert made[0]["timeout"] == 3.0 and made[0]["max_retries"] == 0
    call = client.calls[0]
    assert call["model"] == "gpt-6-luna" and call["reasoning"] == {"effort": "none"} and call["max_output_tokens"] == 300
    fmt = call["text"]["format"]
    assert fmt["name"] == "refine" and fmt["strict"] is True and fmt["schema"]["required"] == ["search_question"]
    assert call["input"] == build_refine_messages(Q, PRODUCT)


def test_refine_question_ok_and_same():
    usage = SimpleNamespace(input_tokens=100, output_tokens=10, output_tokens_details=SimpleNamespace(reasoning_tokens=0))
    r = refine_question(Q, PRODUCT, "m", S, client=FakeClient('{"search_question": " 문이 안 열려요  도어 잠김 "}', usage=usage))
    assert r == RefineResult("문이 안 열려요 도어 잠김", True, "ok")
    assert r.usage == {"input_tokens": 100, "output_tokens": 10, "reasoning_tokens": 0}
    same = refine_question(Q, PRODUCT, "m", S, client=FakeClient('{"search_question": "문이 안 열려요"}'))
    assert same == RefineResult(Q, False, "same")


def test_refine_question_accepts_200_chars():
    text = "가" * 200
    assert refine_question(Q, PRODUCT, "m", S, client=FakeClient('{"search_question": "' + text + '"}')) == RefineResult(text, True, "ok")


@pytest.mark.parametrize("text", ['{"search_question": ""}', '{"search_question": "   "}',
                                  '{"search_question": "' + "가" * 201 + '"}', "JSON 아님", '{"other": "x"}', ""])
def test_refine_question_invalid_outputs(text):
    assert refine_question(Q, PRODUCT, "m", S, client=FakeClient(text)) == RefineResult(Q, False, "invalid_output")


def test_refine_question_timeout_returns_original():
    assert refine_question(Q, PRODUCT, "m", S, client=FakeClient(error=_timeout())) == RefineResult(Q, False, "timeout")


def test_refine_question_api_error_logs_type_only(caplog):
    r = refine_question(Q, PRODUCT, "m", S, client=FakeClient(error=RuntimeError("sk-secret-in-message")))
    assert r == RefineResult(Q, False, "api_error")
    assert "RuntimeError" in caplog.text and "sk-secret-in-message" not in caplog.text
