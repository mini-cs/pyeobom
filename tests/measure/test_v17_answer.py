"""v1.7 Task 9: 실험 조각 한 벌로 서비스 흐름 전체(가리기 → 질문 바꾸기 → 검색 → 답변 → 검증)를 돌린다. 가짜 연결·가짜 AI만 쓴다."""
import json

from app.answer.rewrite import RewriteResult
from app.ask.service import Deps, answer_question
from app.core.config import Settings
from app.retrieval.search import Chunk
from measure.v17_answer import bundle_deps

S = Settings(openai_api_key="", database_url="", openai_embed_model="m", openai_chat_model="answer-model", embed_dim=3,
             rewrite_model="rewrite-model")
MODEL = "aircon-lg-sq06fa1wds"
MODELS = {MODEL: {"id": MODEL, "diagnostic_refs": ["manual:34"]}}
PROD_TEXT = "운영 본문: 필터는 한 달에 한 번 청소하세요."
BUNDLE_TEXT = "실험 본문: 필터는 2주마다 물로 씻어 그늘에 말리세요."
DIAG_TEXT = "CH10 실내기 팬 모터 이상. 서비스센터에 문의하세요."
PROD_CHUNK = Chunk(7, "manual-lg-sq06fa1wds", "manual", "t", "https://x", 20, PROD_TEXT, 0.1)


class BundleConn:
    """bundle_chunks를 읽으면 실험 본문(1,000,000대 번호), 아니면 운영 본문을 돌려주는 가짜 연결."""
    def __init__(self):
        self.calls, self._rows = [], []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if "SELECT 1" in sql:
            self._rows = [(1,)] if params[0] == "v17-a" else []
        elif "bundle_chunks" not in sql:
            self._rows = [(7, "manual-lg-sq06fa1wds", "manual", "t", "https://x", 20, PROD_TEXT, 0.1)]
        elif isinstance(params, tuple):  # 진단 안내 쪽(쪽 번호로 찾기)
            self._rows = [(1000034, "manual-lg-sq06fa1wds", "manual", "t", "https://x", 34, DIAG_TEXT, 0.0)]
        else:  # 벡터 검색
            self._rows = [(1000007, "manual-lg-sq06fa1wds", "manual", "t", "https://x", 20, BUNDLE_TEXT, 0.1)]
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def answer(chunk_id, quote):
    return json.dumps({"found": True, "answer": "필터를 씻으세요.", "citations": [{"chunk_id": chunk_id, "quote": quote}]},
                      ensure_ascii=False)


class Recorder:
    """운영 검색·진단(운영 본문)을 가진 가짜 deps. 보낸 프롬프트와 임베딩한 질문을 적어 둔다"""
    def __init__(self, raw=None, rewritten=None):
        self.messages, self.embedded = [], []
        self.raw = raw or answer(1000007, "필터는 2주마다 물로 씻어")
        self.rewritten = rewritten

    def deps(self):
        def embed(q):
            self.embedded.append(q)
            return [0.1]

        def complete(messages):
            self.messages.append(messages)
            return self.raw

        rewrite = (lambda q, h: RewriteResult(self.rewritten, True, "ok")) if self.rewritten else \
            (lambda q, h: RewriteResult(q, False, "no_history"))
        return Deps(embed_query=embed, search=lambda m, v, q, k: [PROD_CHUNK], complete=complete, supported_ids={MODEL},
                    official_url=lambda m: "https://example.com/support", brand=lambda m: "LG", rewrite=rewrite,
                    diagnostic=lambda m: [Chunk(34, "manual-lg-sq06fa1wds", "manual", "t", "https://x", 34, "운영 진단", 0.0)])

    def prompt(self):
        return json.dumps(self.messages[-1], ensure_ascii=False)


def test_bundle_content_reaches_prompt():
    rec, conn = Recorder(), BundleConn()
    body = answer_question(MODEL, "필터 청소는 어떻게 해요?", bundle_deps(rec.deps(), "v17-a", MODELS, lambda: conn), S, debug=True)
    prompt = rec.prompt()
    assert '<chunk chunk_id=\\"1000007\\"' in prompt and BUNDLE_TEXT in prompt
    assert PROD_TEXT not in prompt
    assert body["retrieved_chunk_ids"] == [1000007]


def test_quote_checked_against_bundle_content():
    ok = Recorder(answer(1000007, "필터는 2주마다 물로 씻어"))
    body = answer_question(MODEL, "필터 청소는?", bundle_deps(ok.deps(), "v17-a", MODELS, lambda: BundleConn()), S)
    assert body["found"] and body["citations"][0]["quote"] == "필터는 2주마다 물로 씻어"
    # 운영 본문에만 있는 인용은 실험 조각 본문 기준 검사에서 지어낸 인용으로 걸린다(두 번 다 실패 → 찾지 못함)
    bad = Recorder(answer(1000007, "필터는 한 달에 한 번 청소하세요."))
    body = answer_question(MODEL, "필터 청소는?", bundle_deps(bad.deps(), "v17-a", MODELS, lambda: BundleConn()), S)
    assert not body["found"] and len(bad.messages) == 2


def test_default_path_unchanged():
    rec = Recorder(answer(7, "필터는 한 달에 한 번"))
    base = rec.deps()
    same = bundle_deps(base, None, MODELS, lambda: BundleConn())
    assert same.search is base.search and same.diagnostic is base.diagnostic
    drop = lambda b: {k: v for k, v in b.items() if not k.endswith("_ms")}
    a = answer_question(MODEL, "필터 청소는?", base, S, debug=True)
    b = answer_question(MODEL, "필터 청소는?", same, S, debug=True)
    assert drop(a) == drop(b) and a["found"] and a["retrieved_chunk_ids"] == [7]


def test_followup_turn_uses_bundle():
    rewritten = "에어컨 필터 청소는 어떻게 해요?"
    rec, conn = Recorder(rewritten=rewritten), BundleConn()
    history = [{"question": "에어컨 필터는 어디 있어요?", "answer": "앞면 패널을 열면 있어요."}]
    body = answer_question(MODEL, "그거 청소는요?", bundle_deps(rec.deps(), "v17-a", MODELS, lambda: conn), S,
                           debug=True, history=history)
    assert rec.embedded == [rewritten] and body["rewritten_question"] == rewritten
    sql, params = conn.calls[-1]
    assert "bundle_chunks" in sql and params["bundle"] == "v17-a" and params["model_id"] == MODEL
    prompt = rec.prompt()
    assert BUNDLE_TEXT in prompt and PROD_TEXT not in prompt and rewritten in prompt
    assert body["found"] and body["retrieved_chunk_ids"] == [1000007]


def test_diagnostic_pages_from_bundle():
    rec, conn = Recorder(answer(1000034, "서비스센터에 문의하세요.")), BundleConn()
    body = answer_question(MODEL, "CH10이 떴어요", bundle_deps(rec.deps(), "v17-a", MODELS, lambda: conn), S, debug=True)
    assert body["diagnostic_added"] and body["retrieved_chunk_ids"] == [1000007, 1000034]
    assert conn.calls[-1][1] == ("v17-a", MODEL, [34])
    assert DIAG_TEXT in rec.prompt() and "운영 진단" not in rec.prompt()
    assert body["found"]
