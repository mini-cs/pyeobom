import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.answer.check import GUIDE_WARNING, NOT_FOUND_MESSAGE, Answer, parse_and_verify
from app.answer.prompting import build_messages
from app.answer.rewrite import RewriteResult
from app.core.brand_guard import guard_message
from app.core.config import Settings
from app.core.observability import get_tracer
from app.input_guard.pii import mask_history, mask_pii
from app.input_guard.validation import validate_model_id, validate_question
from app.retrieval.search import Chunk, needs_diagnostic


@dataclass
class Deps:
    embed_query: Callable[[str], list[float]]
    search: Callable[[str, list[float], str, int], list[Chunk]]  # (model_id, query_vec, question, k) — Task 14에서 hybrid로 교체
    complete: Callable[[list[dict]], str]
    supported_ids: set[str]
    official_url: Callable[[str], str]
    timings: dict[str, int] = field(default_factory=dict)  # 실제 검색이 db_connect_ms를, AI 호출이 토큰 수를 적는다
    diagnostic: Callable[[str], list[Chunk]] = lambda model_id: []  # 모델의 진단 안내 쪽 조각(결정기록 019)
    brand: Callable[[str], str] = lambda model_id: ""  # 모델의 제조사(models.json brand). 다른 브랜드 규칙에 쓴다
    rewrite: Callable[[str, list[dict]], RewriteResult] = lambda q, h: RewriteResult(q, False, "no_history")  # 질문 바꾸기(계획 2)


def _ms(since: float) -> int:
    return int((time.perf_counter() - since) * 1000)


def answer_question(model_id: str, question: str, deps: Deps, settings: Settings, debug: bool = False,
                    history: list[dict] | None = None) -> dict:
    start = time.perf_counter()
    model_id = validate_model_id(model_id, deps.supported_ids)
    question = validate_question(question, settings.max_question_len)
    question, pii_masked = mask_pii(question)  # 이후 임베딩·검색·AI에는 가린 질문만 간다
    history = mask_history(history or [])  # 앞 대화도 가린 뒤에만 질문 바꾸기 AI에 보낸다
    tracer = get_tracer()  # 키가 없으면 무동작. 단계 시간·토큰·가린 질문만 기록한다

    with tracer.span("ask", question_masked=question, model_id=model_id):
        embed_ms = search_total_ms = llm_ms = 0
        chunks, diagnostic_added, result = [], False, None
        rewritten, rewrite_ms = None, None  # 바꾸기를 시도하지 않으면 rewrite_ms는 null(측정 평균 왜곡 방지)
        blocked = guard_message(question, deps.brand(model_id))  # 다른 제조사 이름·코드 질문은 AI 없이 안내(결정 A)
        if history and not blocked:
            # 앞 대화는 질문 바꾸기에만 쓰고 답변 AI에는 넘기지 않는다(바뀐 질문 + 조각만)
            t = time.perf_counter()
            with tracer.span("rewrite", model=settings.rewrite_model) as span:
                r = deps.rewrite(question, history)
                span.update(rewrite_used=r.used, rewrite_reason=r.reason, **r.usage)  # 토큰 수는 숫자만
            rewrite_ms = _ms(t)
            if r.used:
                rewritten = r.text
                blocked = guard_message(rewritten, deps.brand(model_id))  # 바꾼 질문에도 다시 적용
        query = rewritten or question
        if blocked:
            result = Answer(False, blocked, [])
        else:
            t = time.perf_counter()
            with tracer.span("embed"):
                query_vec = deps.embed_query(query)
            embed_ms = _ms(t)
            t = time.perf_counter()
            with tracer.span("search"):
                chunks = deps.search(model_id, query_vec, query, settings.top_k)
                # 질문의 에러 코드가 검색된 조각 어디에도 없으면 진단 안내 쪽을 덧붙인다(프롬프트 규칙 4가 진단 안내를 지시)
                diagnostic_added = False
                if needs_diagnostic(query, chunks):
                    seen = {c.id for c in chunks}
                    extra = [c for c in deps.diagnostic(model_id) if c.id not in seen]
                    chunks, diagnostic_added = chunks + extra, bool(extra)
            search_total_ms = _ms(t)
            if chunks:
                messages = build_messages(query, chunks, settings.prompt_version)
                with tracer.span("llm", model=settings.openai_chat_model) as span:
                    for _ in range(2):  # 검증에 실패하면 한 번 더 묻고, 또 실패하면 찾지 못함
                        t = time.perf_counter()
                        raw = deps.complete(messages)
                        llm_ms += _ms(t)
                        result = parse_and_verify(raw, chunks)
                        if result:
                            break
                    span.update(input_tokens=deps.timings.get("input_tokens", 0),
                                output_tokens=deps.timings.get("output_tokens", 0))
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
        "question_masked": question,
        "rewritten_question": rewritten,
    }
    if debug:
        db_connect_ms = deps.timings.get("db_connect_ms", 0)
        body |= {"retrieved_refs": [c.ref for c in chunks], "retrieved_chunk_ids": [c.id for c in chunks],
                 "cited_refs": [c.ref for c in result.citations],
                 "diagnostic_added": diagnostic_added, "embed_ms": embed_ms, "db_connect_ms": db_connect_ms,
                 "search_ms": max(search_total_ms - db_connect_ms, 0), "llm_ms": llm_ms, "rewrite_ms": rewrite_ms}
    return body
