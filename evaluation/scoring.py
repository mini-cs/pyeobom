def _refs(text: str) -> list[str]:
    return [r for r in text.split("|") if r]


def score_case(case: dict, resp: dict) -> dict:
    """문항 하나를 채점한다. 답 있는 문항은 correct·ref_hit, 함정 문항은 hallucinated를 쓴다(나머지는 None)."""
    answerable = case["expected_found"] == "true"
    error = "error_code" in resp
    got_found = None if error else resp["found"]
    refs = _refs(case["expected_ref"])
    correct = ref_hit = hallucinated = failure = None
    if answerable:
        answer = (resp.get("answer") or "").lower()
        correct = bool(got_found) and all(k.lower() in answer for k in _refs(case["expected_keywords"]))
        ref_hit = any(r in resp.get("cited_refs", []) for r in refs)
        if not correct and not error:
            # 인정 근거가 검색 결과에 하나도 없으면 검색 실패, 있었는데 틀리면 답변 실패
            failure = "answer" if any(r in resp.get("retrieved_refs", []) for r in refs) else "retrieval"
    elif not error:
        hallucinated = got_found is True
    return {
        "id": case["id"], "type": case["type"], "expected_found": case["expected_found"], "got_found": got_found,
        "correct": correct, "ref_hit": ref_hit, "hallucinated": hallucinated, "error": error,
        "latency_ms": None if error else resp.get("latency_ms"), "failure": failure, "human_verdict": "",
        # 규칙(다른 브랜드 등)으로 막혀 임베딩·AI를 부르지 않은 응답. 디버그 시간이 있을 때만 판단한다
        "rule_blocked": not error and resp.get("embed_ms") == 0 and resp.get("llm_ms") == 0,
    }


def _rate(values: list) -> float:
    return round(100 * sum(1 for v in values if v) / len(values), 1) if values else 0.0


def summarize(results: list[dict]) -> dict:
    answerable = [r for r in results if r["expected_found"] == "true"]
    traps = [r for r in results if r["expected_found"] != "true"]
    latencies = [r["latency_ms"] for r in results if r["latency_ms"] is not None and not r.get("rule_blocked")]
    return {
        "accuracy": _rate([r["correct"] for r in answerable]),
        "ref_hit_rate": _rate([r["ref_hit"] for r in answerable]),
        "hallucination_rate": _rate([r["hallucinated"] for r in traps]),
        "error_rate": _rate([r["error"] for r in results]),
        "latency_avg_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "latency_max_ms": max(latencies, default=0),
        "failures": {k: sum(1 for r in results if r["failure"] == k) for k in ("retrieval", "answer")},
    }
