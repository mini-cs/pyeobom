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


def test_followup_pool_uses_previous_turn_as_history(tmp_path):
    from measure.load_common import followup_pool
    path = tmp_path / "fu.csv"
    path.write_text(
        "dialog_id,turn,model_id,question,question_masked,rewritten_question,answer\n"
        "d01,1,washer-a,세탁조 청소는?,세탁조 청소는?,,통살균 코스로 하세요.\n"
        "d01,2,washer-a,그건 얼마나 자주?,그건 얼마나 자주?,세탁조 청소는 얼마나 자주?,월 1회 이상.\n"
        "d09,1,washer-b,5C가 떠요,5C가 떠요,,배수 필터를 청소하세요.\n"
        "d09,2,washer-b,LG도 같아요?,LG도 같아요?,,지금 고른 모델은 삼성 제품이에요.\n",
        encoding="utf-8-sig")
    pool = followup_pool(str(path))
    # 바꾸기가 일어난 이어지는 턴만(다른 브랜드 규칙으로 막힌 턴 제외), 앞 대화는 직전 턴 1개
    assert pool == [{"model_id": "washer-a", "question": "그건 얼마나 자주?",
                     "history": [{"question": "세탁조 청소는?", "answer": "통살균 코스로 하세요."}]}]
