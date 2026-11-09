import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.ask import routes
from app.ask.routes import get_deps
from app.ask.service import Deps
from app.core import observability
from app.retrieval.search import Chunk
from app.web import create_app

RAW_PHONE = "010-1234-5678"
QUESTION = f"기사님 {RAW_PHONE} 통세척은 어떻게 해요?"
CHUNK_TEXT = "통세척은 통살균 코스로 하세요. 세탁조 클리너를 넣습니다."
QUOTE = "통세척은 통살균 코스로 하세요."
ANSWER_TEXT = "통살균 코스로 세탁조를 청소하세요."
VALID = json.dumps({"found": True, "answer": ANSWER_TEXT, "citations": [{"chunk_id": 7, "quote": QUOTE}]},
                   ensure_ascii=False)
KEYS = {"LANGFUSE_PUBLIC_KEY": "pk-lf-test", "LANGFUSE_SECRET_KEY": "sk-lf-test"}


class FakeObservation:
    def __init__(self, records):
        self.records = records

    def update(self, **kwargs):
        self.records.append({"update": kwargs})


class FakeLangfuse:
    """Langfuse 클라이언트 대신 보낼 값을 모두 기록한다."""

    def __init__(self):
        self.records = []

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.records.append(kwargs)
        yield FakeObservation(self.records)

    def names(self):
        return [r["name"] for r in self.records if "name" in r]

    def sent_text(self):
        return json.dumps(self.records, ensure_ascii=False, default=str)


def make_deps():
    chunk = Chunk(7, "manual-washer-a", "manual", "A 세탁기 사용설명서", "https://example.com/a.pdf", 32, CHUNK_TEXT, 0.1)
    timings = {}

    def complete(messages):
        timings["input_tokens"], timings["output_tokens"] = 1200, 80  # 실제 complete_json이 usage로 채우는 값
        return VALID

    return Deps(embed_query=lambda q: [0.1], search=lambda m, v, q, k: [chunk], complete=complete,
                supported_ids={"washer-a"}, official_url=lambda m: "https://example.com/support", timings=timings)


def ask(question=QUESTION):
    app = create_app()
    app.dependency_overrides[get_deps] = make_deps
    return TestClient(app).post("/api/ask", json={"model_id": "washer-a", "question": question})


@pytest.fixture
def no_keys(monkeypatch):
    for name in KEYS:
        monkeypatch.delenv(name, raising=False)

    def must_not_connect():
        raise AssertionError("키가 없으면 Langfuse 클라이언트를 만들면 안 된다")

    monkeypatch.setattr(observability, "_make_client", must_not_connect)


@pytest.fixture
def fake_langfuse(monkeypatch):
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)
    fake = FakeLangfuse()
    monkeypatch.setattr(observability, "_make_client", lambda: fake)
    return fake


def test_tracer_is_noop_without_keys(no_keys):
    with observability.get_tracer().span("embed") as span:
        span.update(input_tokens=1)
    assert ask().status_code == 200


def test_trace_never_contains_raw_question(fake_langfuse):
    assert ask().status_code == 200
    sent = fake_langfuse.sent_text()
    assert RAW_PHONE not in sent
    asked = [r for r in fake_langfuse.records if r.get("name") == "ask"][0]
    assert "기사님" in asked["metadata"]["question_masked"]


def test_trace_never_contains_chunk_prompt_or_answer_text(fake_langfuse):
    assert ask().status_code == 200
    sent = fake_langfuse.sent_text()
    for body in (CHUNK_TEXT, QUOTE, ANSWER_TEXT, "공식 문서 조각"):
        assert body not in sent
    assert all("input" not in r and "output" not in r for r in fake_langfuse.records)


def test_trace_records_stage_names_and_tokens(fake_langfuse):
    assert ask().status_code == 200
    assert fake_langfuse.names() == ["ask", "embed", "search", "llm"]
    llm = [r for r in fake_langfuse.records if r.get("name") == "llm"][0]
    assert llm["as_type"] == "generation"
    usage = [r["update"]["usage_details"] for r in fake_langfuse.records if "usage_details" in r.get("update", {})]
    assert usage == [{"input_tokens": 1200, "output_tokens": 80}]


def test_db_connect_span_recorded(fake_langfuse, monkeypatch):
    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(routes, "get_conn", lambda: Conn())
    monkeypatch.setattr(routes, "search_vector", lambda conn, m, v, k: [])
    routes.get_deps().search("washer-a", [0.1], "질문", 5)
    assert fake_langfuse.names() == ["db_connect"]


def test_tracer_rejects_unlisted_attributes(fake_langfuse):
    with pytest.raises(ValueError):
        with observability.get_tracer().span("embed", answer=ANSWER_TEXT):
            pass


def test_ask_response_unchanged_with_tracing(monkeypatch, fake_langfuse):
    traced = ask().json()
    for name in KEYS:
        monkeypatch.delenv(name)
    plain = ask().json()
    traced.pop("latency_ms"), plain.pop("latency_ms")
    assert traced == plain


HISTORY_Q = "세탁조 냄새는 어떻게 없애요?"
HISTORY_A = "세탁조 클리너를 넣고 고온 세탁을 돌려 주세요."
REWRITTEN = "세탁조 클리너 코스는 얼마나 걸려요?"


def ask_with_history():
    from app.answer.rewrite import RewriteResult

    def deps_with_rewrite():
        d = make_deps()
        d.rewrite = lambda q, h: RewriteResult(REWRITTEN, True, "ok")
        return d

    app = create_app()
    app.dependency_overrides[get_deps] = deps_with_rewrite
    return TestClient(app).post("/api/ask", json={"model_id": "washer-a", "question": "그건 얼마나 걸려요?",
                                                  "history": [{"question": HISTORY_Q, "answer": HISTORY_A}]})


def test_trace_records_rewrite_stage_without_texts(fake_langfuse):
    assert ask_with_history().status_code == 200
    assert fake_langfuse.names() == ["ask", "rewrite", "embed", "search", "llm"]
    meta = [r["update"]["metadata"] for r in fake_langfuse.records if "metadata" in r.get("update", {})]
    assert {"rewrite_used": True, "rewrite_reason": "ok"} in meta
    sent = fake_langfuse.sent_text()
    for text in (HISTORY_Q, HISTORY_A, REWRITTEN):
        assert text not in sent  # 앞 대화·바꾼 질문 본문은 보내지 않는다(가린 새 질문만)
