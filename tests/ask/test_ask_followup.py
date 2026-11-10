import json

from app.answer.rewrite import RewriteResult
from app.ask import routes
from app.ask.service import Deps, answer_question
from app.core.config import Settings
from app.retrieval.search import Chunk

S = Settings(openai_api_key="", database_url="", openai_embed_model="m", openai_chat_model="answer-model", embed_dim=3,
             rewrite_model="rewrite-model")
CHUNK = Chunk(7, "manual-washer-a", "manual", "A 세탁기 사용설명서", "https://example.com/a.pdf", 32, "통세척은 통살균 코스로 하세요.", 0.1)
VALID = '{"found": true, "answer": "통살균 코스로 하세요.", "citations": [{"chunk_id": 7, "quote": "통살균 코스로 하세요."}]}'
HISTORY = [{"question": "기사님 010-1234-5678 왔다 갔는데 세탁조 냄새는 어떻게 없애요?",
            "answer": "세탁조 클리너를 넣고 고온 세탁을 한 번 돌려 주세요."}]
REWRITTEN = "통세척은 얼마나 걸려요?"


class Recorder:
    def __init__(self, rewrite_result=None):
        self.calls = []
        self.rewrite_result = rewrite_result or RewriteResult(REWRITTEN, True, "ok")

    def deps(self, brand="LG"):
        def embed(q):
            self.calls.append(("embed", q))
            return [0.1]

        def search(m, v, q, k):
            self.calls.append(("search", q))
            return [CHUNK]

        def complete(messages):
            self.calls.append(("complete", messages))
            return VALID

        def rewrite(question, history):
            self.calls.append(("rewrite", question, history))
            return self.rewrite_result

        return Deps(embed_query=embed, search=search, complete=complete, supported_ids={"washer-a"},
                    official_url=lambda m: "https://example.com/support", brand=lambda m: brand, rewrite=rewrite)

    def names(self):
        return [c[0] for c in self.calls]

    def first(self, name):
        return next(c for c in self.calls if c[0] == name)


def test_history_searches_with_rewritten_question():
    rec = Recorder()
    body = answer_question("washer-a", "그건 얼마나 걸려요?", rec.deps(), S, history=HISTORY)
    assert rec.names() == ["rewrite", "embed", "search", "complete"]
    assert rec.first("embed")[1] == REWRITTEN and rec.first("search")[1] == REWRITTEN
    assert body["rewritten_question"] == REWRITTEN
    assert body["question_masked"] == "그건 얼마나 걸려요?"


def test_answer_ai_never_receives_history_text():
    rec = Recorder()
    answer_question("washer-a", "그건 얼마나 걸려요?", rec.deps(), S, history=HISTORY)
    sent = json.dumps(rec.first("complete")[1], ensure_ascii=False)
    for text in (HISTORY[0]["question"], HISTORY[0]["answer"], "세탁조 냄새", "고온 세탁", "기사님"):
        assert text not in sent
    assert REWRITTEN in sent


def test_history_is_masked_before_rewrite():
    rec = Recorder()
    answer_question("washer-a", "그건 얼마나 걸려요?", rec.deps(), S, history=HISTORY)
    sent_history = rec.first("rewrite")[2]
    assert "010-1234-5678" not in json.dumps(sent_history, ensure_ascii=False)
    assert "010-****-****" in sent_history[0]["question"]


def test_rewrite_failure_uses_original_question():
    rec = Recorder(RewriteResult("그건 얼마나 걸려요?", False, "timeout"))
    body = answer_question("washer-a", "그건 얼마나 걸려요?", rec.deps(), S, history=HISTORY, debug=True)
    assert rec.first("search")[1] == "그건 얼마나 걸려요?"
    assert body["rewritten_question"] is None
    assert isinstance(body["rewrite_ms"], int)  # 시도했으므로 걸린 시간은 남긴다


def test_rewritten_question_is_checked_for_other_brand_again():
    rec = Recorder(RewriteResult("삼성 세탁기 IE 에러는 뭐예요?", True, "ok"))
    body = answer_question("washer-a", "그건 뭐예요?", rec.deps(brand="LG"), S, history=HISTORY)
    assert rec.names() == ["rewrite"]  # 검색·답변 AI를 부르지 않는다
    assert body["found"] is False
    assert body["answer"].startswith("지금 고른 모델은 LG 제품이에요")



def test_rewritten_question_is_checked_for_other_brand_code_again():
    rec = Recorder(RewriteResult("세탁기에 5C 에러가 뜨면 어떻게 해요?", True, "ok"))
    body = answer_question("washer-a", "그건 어떻게 해요?", rec.deps(brand="LG"), S, history=HISTORY)
    assert rec.names() == ["rewrite"]  # 검색·답변 AI를 부르지 않는다
    assert body["found"] is False
    assert body["answer"].startswith("이 코드는 지금 고른 LG 모델 설명서에 없는 코드예요")

def test_other_brand_question_skips_rewrite():
    rec = Recorder()
    body = answer_question("washer-a", "삼성 세탁기도 그래요?", rec.deps(brand="LG"), S, history=HISTORY, debug=True)
    assert rec.calls == []
    assert body["found"] is False and body["rewrite_ms"] is None


def test_without_history_order_is_unchanged_and_rewrite_ms_is_null():
    rec = Recorder()
    body = answer_question("washer-a", "통세척은 어떻게 해요?", rec.deps(), S, debug=True)
    assert rec.names() == ["embed", "search", "complete"]
    assert body["rewritten_question"] is None
    assert body["rewrite_ms"] is None


def test_get_deps_rewrites_with_rewrite_model(monkeypatch):
    seen = {}

    def fake_rewrite(question, history, model_name, settings):
        seen.update(question=question, model=model_name)
        return RewriteResult(question, False, "api_error")

    monkeypatch.setattr(routes, "rewrite_question", fake_rewrite)
    monkeypatch.setattr(routes, "get_settings", lambda: S)
    routes.get_deps().rewrite("그건요?", HISTORY)
    assert seen == {"question": "그건요?", "model": "rewrite-model"}
