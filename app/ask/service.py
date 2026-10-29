import time
from collections.abc import Callable
from dataclasses import dataclass

from app.answer.check import GUIDE_WARNING, NOT_FOUND_MESSAGE, Answer, parse_and_verify
from app.answer.prompting import build_messages
from app.core.config import Settings
from app.input_guard.pii import mask_pii
from app.input_guard.validation import validate_model_id, validate_question
from app.retrieval.search import Chunk


@dataclass
class Deps:
    embed_query: Callable[[str], list[float]]
    search: Callable[[str, list[float], str, int], list[Chunk]]  # (model_id, query_vec, question, k) — Task 14에서 hybrid로 교체
    complete: Callable[[list[dict]], str]
    supported_ids: set[str]
    official_url: Callable[[str], str]


def answer_question(model_id: str, question: str, deps: Deps, settings: Settings, debug: bool = False) -> dict:
    start = time.perf_counter()
    model_id = validate_model_id(model_id, deps.supported_ids)
    question = validate_question(question, settings.max_question_len)
    question, pii_masked = mask_pii(question)  # 이후 임베딩·검색·AI에는 가린 질문만 간다

    chunks = deps.search(model_id, deps.embed_query(question), question, settings.top_k)
    result = None
    if chunks:
        messages = build_messages(question, chunks, settings.prompt_version)
        for _ in range(2):  # 검증에 실패하면 한 번 더 묻고, 또 실패하면 찾지 못함
            result = parse_and_verify(deps.complete(messages), chunks)
            if result:
                break
    result = result or Answer(False, NOT_FOUND_MESSAGE, [])

    body = {
        "found": result.found,
        "answer": result.answer,
        "citations": [
            {"doc_type": c.doc_type, "title": c.title, "page": c.page, "url": c.url, "quote": c.quote}
            | ({"warning": GUIDE_WARNING} if c.doc_type == "guide" else {})
            for c in result.citations
        ],
        "official_url": deps.official_url(model_id),
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "pii_masked": pii_masked,
    }
    if debug:
        body["retrieved_refs"] = [c.ref for c in chunks]
    return body
