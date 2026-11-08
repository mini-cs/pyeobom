"""Langfuse 추적(기본 꺼짐). LANGFUSE_PUBLIC_KEY·LANGFUSE_SECRET_KEY가 없으면 아무것도 하지 않는다.

보내는 것은 단계 이름·시간, 토큰 수, 가린 질문뿐이다. 프롬프트·설명서 조각·답 본문은 보내지 않는다.
- OpenAI 자동 기록(래퍼·자동 계측)은 쓰지 않고, 이 모듈이 만든 기록만 내보낸다(should_export_span).
- 기록에 넣을 수 있는 속성은 ALLOWED_ATTRS로 제한해 본문이 실수로 들어가지 못하게 한다.
"""
import os
from contextlib import contextmanager
from functools import lru_cache

ALLOWED_ATTRS = {"question_masked", "model_id", "model", "input_tokens", "output_tokens"}
USAGE_KEYS = ("input_tokens", "output_tokens")


def _check(attrs: dict) -> dict:
    unknown = set(attrs) - ALLOWED_ATTRS
    if unknown:
        raise ValueError(f"추적에 넣을 수 없는 속성: {sorted(unknown)}")
    return attrs


class _NoopSpan:
    def update(self, **attrs) -> None:
        pass


class _Span:
    def __init__(self, observation):
        self._obs = observation

    def update(self, **attrs) -> None:
        attrs = _check(dict(attrs))
        usage = {k: attrs.pop(k) for k in USAGE_KEYS if k in attrs}
        kwargs = ({"usage_details": usage} if usage else {}) | ({"metadata": attrs} if attrs else {})
        if kwargs:
            self._obs.update(**kwargs)


class Tracer:
    def __init__(self, client=None):
        self._client = client

    @contextmanager
    def span(self, name: str, **attrs):
        attrs = _check(dict(attrs))
        if self._client is None:
            yield _NoopSpan()
            return
        model = attrs.pop("model", None)
        kwargs = {"as_type": "generation", "model": model} if name == "llm" else {"as_type": "span"}
        with self._client.start_as_current_observation(name=name, metadata=attrs, **kwargs) as obs:
            yield _Span(obs)


@lru_cache
def _make_client():
    from langfuse import Langfuse
    from langfuse.span_filter import is_langfuse_span

    # 키·주소는 환경 변수(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL)에서 읽는다
    return Langfuse(should_export_span=is_langfuse_span)


def get_tracer() -> Tracer:
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return Tracer(None)
    return Tracer(_make_client())
