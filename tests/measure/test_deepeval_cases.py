from app.ask.service import Deps
from app.retrieval.search import Chunk
from evaluation.contexts import capture_contexts
from measure.deepeval_cases import build_cases

ROWS = [
    {"id": "q01", "expected_found": "true", "got_found": "True", "question": "세탁조 청소는?", "answer": "통살균 코스로 하세요."},
    {"id": "q02", "expected_found": "true", "got_found": "False", "question": "물 온도는?", "answer": "찾지 못했어요"},
    {"id": "q28", "expected_found": "false", "got_found": "False", "question": "렌탈 가격은?", "answer": "찾지 못했어요"},
]
CONTEXTS = {"q01": ["통세척은 통살균 코스로 하세요."], "q02": ["온도 안내"], "q28": ["다른 내용"]}


def test_build_cases_keeps_only_answered_and_found():
    cases = build_cases(ROWS, CONTEXTS)
    assert len(cases) == 1
    assert cases[0] == {"id": "q01", "input": "세탁조 청소는?", "actual_output": "통살균 코스로 하세요.",
                        "retrieval_context": ["통세척은 통살균 코스로 하세요."]}


def _chunk(cid, text):
    return Chunk(cid, "manual-a", "manual", "A", "https://example.com", 1, text, 0.1)


def test_capture_contexts_records_search_and_diagnostic_chunks_once():
    found, diag = [_chunk(1, "검색 조각")], [_chunk(1, "검색 조각"), _chunk(2, "진단 조각")]
    deps = Deps(embed_query=lambda q: [0.1], search=lambda m, v, q, k: found, complete=lambda m: "",
                supported_ids={"a"}, official_url=lambda m: "", diagnostic=lambda m: diag)
    store = []
    wrapped = capture_contexts(deps, store)
    assert wrapped.search("a", [0.1], "q", 5) == found
    assert wrapped.diagnostic("a") == diag
    assert store == ["검색 조각", "진단 조각"]


def test_build_followup_cases_uses_rewritten_question_and_skips_traps():
    from measure.deepeval_cases import build_followup_cases
    rows = [
        {"dialog_id": "d01", "turn": "1", "type": "base", "expected_found": "true", "got_found": "True",
         "question_masked": "세탁조 청소는?", "rewritten_question": "", "answer": "통살균 코스로 하세요."},
        {"dialog_id": "d01", "turn": "2", "type": "pronoun", "expected_found": "true", "got_found": "True",
         "question_masked": "그건 얼마나 자주?", "rewritten_question": "세탁조 청소는 얼마나 자주?", "answer": "월 1회 이상."},
        {"dialog_id": "d07", "turn": "2", "type": "trap", "expected_found": "false", "got_found": "False",
         "question_masked": "그 필터 얼마예요?", "rewritten_question": "먼지 필터 얼마예요?", "answer": "찾지 못했어요"},
        {"dialog_id": "d03", "turn": "2", "type": "pronoun", "expected_found": "true", "got_found": "False",
         "question_masked": "그 거름망은?", "rewritten_question": "배수 필터는?", "answer": "찾지 못했어요"},
    ]
    contexts = {"d01-1": ["조각1"], "d01-2": ["조각2"], "d07-2": ["조각3"], "d03-2": ["조각4"]}
    cases = build_followup_cases(rows, contexts)
    assert [c["id"] for c in cases] == ["d01-1", "d01-2"]
    assert cases[1] == {"id": "d01-2", "input": "세탁조 청소는 얼마나 자주?", "actual_output": "월 1회 이상.", "retrieval_context": ["조각2"]}
    assert cases[0]["input"] == "세탁조 청소는?"
