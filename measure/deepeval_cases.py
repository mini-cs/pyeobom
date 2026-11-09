"""평가 결과 CSV(1차 형식)와 근거 본문을 DeepEval 사례로 바꾼다. 답이 있고(함정 아님) 찾은 문항만 채점한다."""


def build_cases(rows: list[dict], contexts: dict[str, list[str]]) -> list[dict]:
    return [{"id": r["id"], "input": r["question"], "actual_output": r["answer"], "retrieval_context": contexts[r["id"]]}
            for r in rows if r["expected_found"] == "true" and r["got_found"] == "True"]


def build_followup_cases(rows: list[dict], contexts: dict[str, list[str]]) -> list[dict]:
    """새 세트(이어지는 질문) 결과: 답 있는·찾은 턴만. 답변 AI가 실제로 받은 질문(바꾼 질문, 없으면 가린 질문)을 input으로."""
    cases = []
    for r in rows:
        if r["expected_found"] == "true" and r["got_found"] == "True" and r["type"] != "trap":
            key = f"{r['dialog_id']}-{r['turn']}"
            cases.append({"id": key, "input": r["rewritten_question"] or r["question_masked"], "actual_output": r["answer"],
                          "retrieval_context": contexts[key]})
    return cases
