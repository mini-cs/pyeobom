import time
from collections.abc import Callable
from dataclasses import dataclass, field

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
    timings: dict[str, int] = field(default_factory=dict)  # 실제 검색이 db_connect_ms를 적는다


def _ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)


def answer_question(model_id: str, question: str, deps: Deps, settings: Settings, debug: bool = False) -> dict:
    start = time.perf_counter()
    model_id = validate_model_id(model_id, deps.supported_ids)
    question = validate_question(question, settings.max_question_len)
    question, pii_masked = mask_pii(question)  # 이후 임베딩·검색·AI에는 가린 질문만 간다

    t = time.perf_counter()
    query_vec = deps.embed_query(question)
    embed_ms = _ms(t)
    t = time.perf_counter()
    chunks = deps.search(model_id, query_vec, question, settings.top_k)
    search_total_ms = _ms(t)
    result, llm_ms = None, 0
    if chunks:
        messages = build_messages(question, chunks, settings.prompt_version)
        for _ in range(2):  # 검증에 실패하면 한 번 더 묻고, 또 실패하면 찾지 못함
            t = time.perf_counter()
            raw = deps.complete(messages)
            llm_ms += _ms(t)
            result = parse_and_verify(raw, chunks)
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
        db_connect_ms = deps.timings.get("db_connect_ms", 0)
        body |= {"retrieved_refs": [c.ref for c in chunks], "embed_ms": embed_ms, "db_connect_ms": db_connect_ms,
                 "search_ms": max(search_total_ms - db_connect_ms, 0), "llm_ms": llm_ms}
    return body
