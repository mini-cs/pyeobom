from evaluation.scoring import score_case, summarize


def case(keywords="배수|필터", ref="manual:32", found="true", type_="usage"):
    return {"id": "q01", "type": type_, "expected_found": found, "expected_keywords": keywords, "expected_ref": ref}


def resp(answer="배수 필터를 청소하세요", found=True, cited=None, retrieved=None, latency=1000):
    return {"found": found, "answer": answer, "latency_ms": latency,
            "cited_refs": cited if cited is not None else ["manual:32"],
            "retrieved_refs": retrieved if retrieved is not None else ["manual:32"]}


def ans(correct):
    return {"type": "usage", "expected_found": "true", "correct": correct, "ref_hit": correct, "hallucinated": None,
            "error": False, "latency_ms": 1000, "failure": None if correct else "answer"}


def trap(hallucinated):
    return {"type": "trap_none", "expected_found": "false", "correct": None, "ref_hit": None, "hallucinated": hallucinated,
            "error": False, "latency_ms": 3000, "failure": None}


def test_accuracy_denominator_is_answerable_only():
    s = summarize([ans(correct=True), ans(correct=False), trap(hallucinated=False)])
    assert s["accuracy"] == 50.0 and s["hallucination_rate"] == 0.0
    assert (s["latency_avg_ms"], s["latency_max_ms"], s["failures"]) == (1667, 3000, {"retrieval": 0, "answer": 1})


def test_keywords_all_required():
    assert score_case(case(keywords="배수|필터"), resp(answer="배수 필터 청소"))["correct"] is True
    assert score_case(case(keywords="배수|필터"), resp(answer="배수 호스 확인"))["correct"] is False
    assert score_case(case(keywords="AAA"), resp(answer="aaa 건전지"))["correct"] is True   # 대소문자 무시


def test_failure_classification():
    assert score_case(case(ref="manual:32"), resp(found=False, retrieved=["manual:10", "guide:x"]))["failure"] == "retrieval"
    assert score_case(case(ref="guide:samsung-5c"), resp(found=False, retrieved=["guide:samsung-5c"]))["failure"] == "answer"
    assert score_case(case(), resp())["failure"] is None


def test_ref_hit_accepts_any_listed_ref():
    assert score_case(case(ref="manual:55|guide:samsung-5c"), resp(cited=["guide:samsung-5c"]))["ref_hit"] is True
    assert score_case(case(ref="manual:55"), resp(cited=["manual:54"]))["ref_hit"] is False


def test_trap_found_is_hallucination():
    r = score_case(case(found="false", ref="", keywords="", type_="trap_none"), resp(found=True))
    assert r["hallucinated"] is True and r["correct"] is None and r["ref_hit"] is None
    assert score_case(case(found="false", ref="", keywords="", type_="trap_none"), resp(found=False))["hallucinated"] is False


def test_error_counts_as_incorrect_and_error():
    r = score_case(case(), {"error_code": "AI_TIMEOUT"})
    assert r["error"] is True and r["correct"] is False and r["latency_ms"] is None
    assert summarize([r, ans(correct=True)])["error_rate"] == 50.0


def test_human_verdict_left_blank():
    assert score_case(case(), resp())["human_verdict"] == ""
