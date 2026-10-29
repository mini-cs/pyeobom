import pytest

from app.retrieval.embeddings import embed_query
from app.retrieval.search import search_vector

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
