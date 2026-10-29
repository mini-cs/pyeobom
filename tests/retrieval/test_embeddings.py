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
