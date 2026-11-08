"""평가 결과 CSV(1차 형식)와 근거 본문을 DeepEval 사례로 바꾼다. 답이 있고(함정 아님) 찾은 문항만 채점한다."""


def build_cases(rows: list[dict], contexts: dict[str, list[str]]) -> list[dict]:
    return [{"id": r["id"], "input": r["question"], "actual_output": r["answer"], "retrieval_context": contexts[r["id"]]}
            for r in rows if r["expected_found"] == "true" and r["got_found"] == "True"]
