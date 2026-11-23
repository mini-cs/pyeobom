import pytest

from app.retrieval.embeddings import embed_query
from app.retrieval.search import SQL, search_vector, search_vectors

MODELS = ["washer-samsung-wd90h25", "washer-lg-fx25", "aircon-lg-sq06fa1wds"]


@pytest.mark.integration
def test_plain_list_query_vector_is_accepted(conn):
    # embed_query는 파이썬 list를 돌려준다. 형 지정 없이 넘기면 "vector <=> double precision[]" 오류가 났다
    query_vec = embed_query("필터 청소")
    assert isinstance(query_vec, list)
    assert search_vector(conn, MODELS[0], query_vec, k=3)


@pytest.mark.integration
@pytest.mark.parametrize("model_id", MODELS)
@pytest.mark.parametrize("question", ["필터 청소", "에러 코드 CH05가 떴어요", "OE 에러가 떠요", "이불 코스 최대 용량"])
def test_results_only_from_selected_model(conn, docs_of, model_id, question):
    chunks = search_vector(conn, model_id, embed_query(question), k=5)
    assert chunks and {c.doc_id for c in chunks} <= docs_of(model_id)   # 다른 모델 문서의 조각은 절대 섞이지 않음


@pytest.mark.integration
def test_returns_at_most_k_sorted_by_distance(conn):
    chunks = search_vector(conn, MODELS[0], embed_query("통세척"), k=5)
    assert len(chunks) == 5 and [c.score for c in chunks] == sorted(c.score for c in chunks)


@pytest.mark.integration
def test_chunk_carries_citation_fields(conn):
    chunks = search_vector(conn, "washer-samsung-wd90h25", embed_query("이불 코스 최대 용량"), k=1)
    c = chunks[0]
    assert (c.doc_type, c.page, c.ref) == ("manual", 38, "manual:38") and "4.0 kg" in c.content
    assert c.title and c.source_url.startswith("https://")


@pytest.mark.integration
def test_fetch_manual_pages_returns_only_that_models_manual(conn):
    from app.retrieval.search import fetch_manual_pages
    chunks = fetch_manual_pages(conn, "aircon-lg-sq06fa1wds", [34, 49])
    assert chunks and {c.page for c in chunks} == {34, 49} and {c.doc_type for c in chunks} == {"manual"}
    assert fetch_manual_pages(conn, "washer-samsung-wd90h25", []) == []


# ── 첫 질문 다듬기(v1.96): 두 질문 검색 ──
class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return []


LEAST = "LEAST(c.embedding <=> %(q1)s::vector, c.embedding <=> %(q2)s::vector)"


def test_search_vectors_one_vector_equals_search_vector():
    a, b = FakeConn(), FakeConn()
    search_vectors(a, "washer-lg-fx25", [[0.1]], 5)
    search_vector(b, "washer-lg-fx25", [0.1], 5)
    assert a.calls == b.calls == [(SQL, {"q": [0.1], "model_id": "washer-lg-fx25", "k": 5})]


def test_search_vectors_two_vectors_uses_least():
    conn = FakeConn()
    search_vectors(conn, "washer-lg-fx25", [[0.1], [0.2]], 5)
    sql, params = conn.calls[0]
    assert LEAST + " AS score" in sql
    assert sql.replace(LEAST, "c.embedding <=> %(q)s::vector") == SQL  # 점수 말고는 운영 SQL과 같은 모양(모델 필터 포함)
    assert params == {"q1": [0.1], "q2": [0.2], "model_id": "washer-lg-fx25", "k": 5}


@pytest.mark.parametrize("n", [0, 3])
def test_search_vectors_rejects_zero_or_three(n):
    with pytest.raises(ValueError):
        search_vectors(FakeConn(), "washer-lg-fx25", [[0.1]] * n, 5)
