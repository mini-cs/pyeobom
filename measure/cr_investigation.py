"""근거 관련성(Contextual Relevancy) 0.297 원인 조사 집계(조사 전용, 서비스 코드는 바꾸지 않음).

DeepEval 4.3.3의 근거 관련성 판정은 조각마다 여러 문장(statement)에 yes/no를 매기는 **문장 단위**다.
조각 안에 관련(yes) 문장이 하나라도 있으면 그 조각을 "관련 있음"으로 본다.
"""


def count_relevant_chunks(deepeval_record: dict) -> int:
    return sum(1 for chunk in deepeval_record["contextual_relevancy_verdicts"]
               if any(str(v["verdict"]).lower() == "yes" for v in chunk))


def _refs(text: str) -> list[str]:
    return [r for r in (text or "").split("|") if r]


def hit_rate(rows: list[dict]) -> float:
    """기대 근거가 인용 또는 검색 상위 5개에 있는 행의 비율(기대 근거가 없는 행은 제외)."""
    scored = [r for r in rows if _refs(r["expected_ref"])]
    hits = [r for r in scored
            if set(_refs(r["expected_ref"])) & (set(_refs(r["cited_refs"])) | set(_refs(r["retrieved_refs"])[:5]))]
    return len(hits) / len(scored) if scored else 0.0
