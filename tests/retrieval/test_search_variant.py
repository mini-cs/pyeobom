import pytest

from app.retrieval import search as S
from app.retrieval.search import search_vector


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return []


def test_default_is_exactly_the_production_query():
    conn = FakeConn()
    search_vector(conn, "washer-lg-fx25", [0.1], 5)
    assert conn.calls == [(S.SQL, {"q": [0.1], "model_id": "washer-lg-fx25", "k": 5})]


@pytest.mark.parametrize("variant, with_original", [("m1_title", False), ("m2_question", True)])
def test_variant_uses_experiment_index(variant, with_original):
    conn = FakeConn()
    search_vector(conn, "washer-lg-fx25", [0.1], 5, variant=variant)
    sql, params = conn.calls[0]
    assert "chunk_variants" in sql and sql != S.SQL
    assert params == {"q": [0.1], "model_id": "washer-lg-fx25", "k": 5, "variant": variant, "with_original": with_original}


def test_unknown_variant_is_rejected():
    with pytest.raises(ValueError):
        search_vector(FakeConn(), "washer-lg-fx25", [0.1], 5, variant="m9")


@pytest.mark.integration
@pytest.mark.parametrize("variant", ["m1_title", "m2_question"])
def test_variant_query_runs_and_keeps_model_filter(conn, docs_of, variant):
    # 실험 행이 없어도 SQL이 돌아야 하고, 결과는 고른 모델 문서의 원래 조각(본문 그대로)이다
    from app.retrieval.embeddings import embed_query
    chunks = search_vector(conn, "washer-lg-fx25", embed_query("세탁조 청소"), 5, variant=variant)
    assert len(chunks) <= 5 and {c.doc_id for c in chunks} <= docs_of("washer-lg-fx25")
    for c in chunks:
        assert conn.execute("SELECT content FROM chunks WHERE id = %s", (c.id,)).fetchone()[0] == c.content
    assert [c.score for c in chunks] == sorted(c.score for c in chunks)
