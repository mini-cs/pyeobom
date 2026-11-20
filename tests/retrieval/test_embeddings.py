from types import SimpleNamespace

from app.retrieval.embeddings import embed_query, embed_texts


class FakeClient:
    def __init__(self):
        self.calls = []
        self.embeddings = self

    def create(self, model, input):
        self.calls.append((model, list(input)))
        return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(t))]) for t in input])


def test_embed_texts_batches_and_keeps_order(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    from app.core.config import get_settings
    get_settings.cache_clear()
    client = FakeClient()
    texts = ["가" * (i % 7 + 1) for i in range(250)]
    assert embed_texts(texts, client) == [[float(len(t))] for t in texts]
    assert [len(batch) for _, batch in client.calls] == [100, 100, 50]
    assert all(model == "text-embedding-3-small" for model, _ in client.calls)
    get_settings.cache_clear()


def test_embed_query_returns_one_vector():
    assert embed_query("통세척", FakeClient()) == [3.0]


# --- 임베딩 모델 바꾸기(v1.9) Task 1: 모델·차원 지정 ---
import pytest


class RecordingClient:
    """요청 인자를 그대로 기록한다(dimensions 키가 붙었는지 보려고)."""
    def __init__(self):
        self.calls = []
        self.embeddings = self

    def create(self, **kwargs):
        self.calls.append({k: (list(v) if k == "input" else v) for k, v in kwargs.items()})
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0]) for _ in kwargs["input"]])


@pytest.fixture
def fake_client():
    return RecordingClient()


@pytest.fixture
def settings_small(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.delenv("OPENAI_EMBED_DIMENSIONS", raising=False)
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def test_request_has_no_dimensions_by_default(fake_client, settings_small):
    embed_texts(["가"], client=fake_client)
    assert fake_client.calls == [{"model": "text-embedding-3-small", "input": ["가"]}]


def test_dimensions_and_model_override_are_sent(fake_client, settings_small):
    embed_query("가", client=fake_client, model="text-embedding-3-large", dimensions=1536)
    assert fake_client.calls == [{"model": "text-embedding-3-large", "input": ["가"], "dimensions": 1536}]


def test_dimensions_from_settings_are_sent(fake_client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("OPENAI_EMBED_DIMENSIONS", "1536")
    get_settings.cache_clear()
    embed_texts(["가"], client=fake_client)
    get_settings.cache_clear()
    assert fake_client.calls == [{"model": "text-embedding-3-large", "input": ["가"], "dimensions": 1536}]
