import pytest

from measure.load_common import assert_not_production, bypass_headers, question_pool


def test_question_pool_drops_trap_questions():
    pool = question_pool("evaluation/questions.csv")
    assert len(pool) == 25
    assert set(pool[0]) == {"model_id", "question"}


def test_bypass_headers_empty_without_secret():
    assert bypass_headers(None) == {}
    assert bypass_headers("") == {}


def test_bypass_headers_sends_one_header():
    headers = bypass_headers("s")
    assert headers == {"x-vercel-protection-bypass": "s"}


@pytest.mark.parametrize("url", ["https://pyeobom.vercel.app", "https://pyeobom.vercel.app/api/ask", "pyeobom.vercel.app"])
def test_assert_not_production_rejects_production(url):
    with pytest.raises(ValueError):
        assert_not_production(url)


def test_assert_not_production_allows_preview():
    assert_not_production("https://pyeobom-git-feat-measure-locust-mini-0fbe.vercel.app")
