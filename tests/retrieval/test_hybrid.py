import pytest

from app.retrieval.embeddings import embed_query
from app.retrieval.search import Chunk, extract_keywords, merge_results, search_hybrid, search_keyword


def chunk(i, page=1):
    return Chunk(i, "manual-x", "manual", "제목", "https://example.com", page, f"내용 {i}", 0.1 * i)


@pytest.mark.parametrize("q,words", [
    ("장마철에 습기만 빼고 싶어요", ["장마철", "습기"]),
    ("통세척은 어떻게 해요?", ["통세척"]),
    ("세제를 매번 안 넣고 자동으로 들어가게 할 수 있어요?", ["세제", "자동"]),
    ("에어컨 필터는 어떻게 빼서 청소해요?", ["필터", "청소"]),
    ("에어컨에 CH10이 떴어요. 무슨 뜻이에요?", []),   # 코드는 extract_code_tokens가 맡는다
])
def test_extract_keywords_strips_particles_and_common_words(q, words):
    assert extract_keywords(q) == words


def test_merge_keyword_first_dedup_and_limit():
    kw = [chunk(1), chunk(2)]
    vec = [chunk(2), chunk(3), chunk(4), chunk(5), chunk(6)]
    assert [c.id for c in merge_results(kw, vec, k=5)] == [1, 2, 3, 4, 5]


def test_merge_without_keyword_hits_is_vector_only():
    assert [c.id for c in merge_results([], [chunk(3), chunk(4)], k=5)] == [3, 4]


@pytest.mark.integration
def test_keyword_search_finds_exact_word_in_selected_model_only(conn, docs_of):
    chunks = search_keyword(conn, "washer-samsung-wd90h25", ["통세척"], embed_query("통세척은 어떻게 해요?"), k=2)
    assert chunks and all("통세척" in c.content for c in chunks) and {c.doc_id for c in chunks} <= docs_of("washer-samsung-wd90h25")


@pytest.mark.integration
@pytest.mark.xfail(strict=True, reason="v2b 미채택 기록: 키워드로는 26쪽이 4위라 상위 5개에 못 들어옴(docs/평가/2026-11-01-v2b.md)")
def test_hybrid_brings_q20_dehumidify_page_into_top_k(conn):
    q = "장마철에 습기만 빼고 싶어요"
    chunks = search_hybrid(conn, "aircon-lg-sq06fa1wds", embed_query(q), q, k=5)
    assert len(chunks) == 5 and "manual:26" in [c.ref for c in chunks]   # v1 벡터 검색에서는 20위 밖
