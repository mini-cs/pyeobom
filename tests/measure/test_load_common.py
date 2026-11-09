import pytest

from measure.load_common import assert_not_production, bypass_headers, question_pool, warm_up, answer_failure


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


def test_warm_up_sends_two_questions_from_pool():
    sent = []
    pool = [{"model_id": "a", "question": "q1"}, {"model_id": "b", "question": "q2"}, {"model_id": "c", "question": "q3"}]
    warm_up(lambda body: sent.append(body), pool)
    assert sent == pool[:2]


def test_answer_failure_accepts_answer_json():
    assert answer_failure(200, '{"found": true, "answer": "통살균 코스"}') is None


@pytest.mark.parametrize("status, body", [(302, ""), (200, "<!doctype html><title>Login</title>"), (200, '{"error_code": "X"}')])
def test_answer_failure_rejects_non_answer(status, body):
    assert answer_failure(status, body)
