from dataclasses import replace
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.answer.llm import complete_json
from app.core.config import Settings
from app.core.errors import AppError

MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
REQ = httpx.Request("POST", "https://api.openai.com/v1/responses")


def settings(**kw) -> Settings:
    base = Settings(openai_api_key="sk-test", database_url="", openai_embed_model="text-embedding-3-small",
                    openai_chat_model="gpt-6-luna", embed_dim=1536)
    return replace(base, **kw)


def rate_limit(code):
    return openai.RateLimitError("rate limited", response=httpx.Response(429, request=REQ), body={"code": code} if code else None)


class FakeClient:
    def __init__(self):
        self.script, self.calls, self.kwargs = ["ok-json"], 0, None
        self.responses = self

    def create(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return SimpleNamespace(output_text=item)


@pytest.fixture
def fake_client():
    return FakeClient()


def test_missing_key_is_service_unavailable_without_call(fake_client):
    with pytest.raises(AppError) as e:
        complete_json(MSGS, settings(openai_api_key=""), fake_client)
    assert e.value.code == "SERVICE_UNAVAILABLE" and fake_client.calls == 0


def test_sends_model_effort_limit_and_json_schema(fake_client):
    assert complete_json(MSGS, settings(), fake_client) == "ok-json"
    k = fake_client.kwargs
    assert (k["model"], k["input"], k["max_output_tokens"], k["reasoning"]) == ("gpt-6-luna", MSGS, 600, {"effort": "low"})
    assert k["text"]["format"]["type"] == "json_schema" and k["text"]["format"]["strict"] is True


def test_retries_once_then_succeeds(fake_client):
    fake_client.script = [TimeoutError(), "ok-json"]
    assert complete_json(MSGS, settings(), fake_client) == "ok-json" and fake_client.calls == 2


def test_two_timeouts_raise_ai_timeout(fake_client):
    fake_client.script = [TimeoutError(), TimeoutError()]
    with pytest.raises(AppError) as e:
        complete_json(MSGS, settings(), fake_client)
    assert e.value.code == "AI_TIMEOUT" and fake_client.calls == 2


def test_sdk_timeout_is_retried(fake_client):
    fake_client.script = [openai.APITimeoutError(request=REQ), "ok-json"]
    assert complete_json(MSGS, settings(), fake_client) == "ok-json" and fake_client.calls == 2


def test_5xx_is_retried_once(fake_client):
    err = openai.InternalServerError("boom", response=httpx.Response(500, request=REQ), body=None)
    fake_client.script = [err, err]
    with pytest.raises(AppError) as e:
        complete_json(MSGS, settings(), fake_client)
    assert e.value.code == "SERVICE_UNAVAILABLE" and fake_client.calls == 2


# 결정기록 017 "429 처리": 일반 속도 제한(문서상 코드 없음)과 slow_down만 1회 재시도
@pytest.mark.parametrize("code,calls", [
    (None, 2), ("slow_down", 2),
    ("credit_balance_exhausted", 1), ("organization_spend_limit_exceeded", 1), ("project_spend_limit_exceeded", 1),
    ("organization_usage_limit_exceeded", 1), ("unknown_code", 1),
])
def test_429_retry_only_for_rate_limits(fake_client, code, calls):
    fake_client.script = [rate_limit(code), rate_limit(code)]
    with pytest.raises(AppError) as e:
        complete_json(MSGS, settings(), fake_client)
    assert e.value.code == "SERVICE_UNAVAILABLE" and fake_client.calls == calls


def test_force_fail_switch(fake_client):
    with pytest.raises(AppError) as e:
        complete_json(MSGS, settings(force_fail=True), fake_client)
    assert e.value.code == "AI_TIMEOUT" and fake_client.calls == 0


def test_api_key_never_in_error(fake_client):
    fake_client.script = [RuntimeError("boom sk-secret")]
    with pytest.raises(AppError) as e:
        complete_json(MSGS, settings(openai_api_key="sk-secret"), fake_client)
    assert "sk-secret" not in str(e.value) and "sk-secret" not in e.value.message and e.value.__cause__ is None
