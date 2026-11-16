"""v1.6 "찾지 못함" 원인 조사 도구(docs/평가/v16-not-found.md).

답변 AI 출력을 app/answer/check.py와 같은 순서로 분류하고, 인용마다 따로 판정한다.
서비스 코드는 바꾸지 않고 감싸기만 한다. 설명서 본문과 AI 원래 출력은 measure/out/v16-not-found/(git 제외)에만 저장한다.
"""
import json
import re
from dataclasses import replace

from app.answer.check import MAX_QUOTE, parse_and_verify
from app.answer.prompting import build_messages

PASS, JSON_ERROR, FOUND_FALSE, EMPTY = "통과", "JSON 오류", "found false", "답·인용 비어 있음"
UNRETRIEVED, BAD_QUOTE, NOT_IN_CHUNK = "검색 안 된 chunk_id", "인용 비어 있음·150자 초과", "인용이 조각에 없음"
HEAD = 20  # "본문 맨 앞 쪽 표시": 앞 20자 안


def _num(page: int) -> str:
    return rf"(?<!\d){page}(?!\d)"


def _squash(text: str) -> str:
    return " ".join(text.split())


def page_marker(content: str, page: int | None) -> bool:
    return page is not None and re.search(_num(page), content[:HEAD]) is not None


def marker_shape(content: str, page: int | None) -> str | None:
    if not page_marker(content, page):
        return None
    head = content[:HEAD]
    if re.search(rf"한국어\s+{_num(page)}", head):
        return "한국어 N"
    if re.search(rf"{_num(page)}\s+한국어", head):
        return "N 한국어"
    return "그 밖"


def strip_page_marker(content: str, page: int | None) -> tuple[str, str]:
    """본문 맨 앞에서 쪽 번호 끝까지와 바로 뒤 공백·줄바꿈을 지운다. (남은 본문, 지운 글자)"""
    m = re.search(_num(page), content[:HEAD]) if page is not None else None
    if not m:
        return content, ""
    end = m.end()
    while end < len(content) and content[end].isspace():
        end += 1
    return content[end:], content[:end]


def _judge(item, by_id: dict, chunks: list) -> dict:
    if not isinstance(item, dict):
        return {"chunk_id": None, "alone_ok": False, "alone_reason": JSON_ERROR}
    cid, quote = item.get("chunk_id"), item.get("quote")
    chunk = by_id.get(cid)
    if chunk is None:  # check.py 54줄: 검색된 조각 번호가 아님
        quote_in = []
        if isinstance(quote, str) and quote.strip():
            quote_in = [{"id": c.id, "page": c.page, "id_is_page": c.page == cid, "page_marker": page_marker(c.content, c.page)}
                        for c in chunks if _squash(quote) in _squash(c.content)]
        return {"chunk_id": cid, "alone_ok": False, "alone_reason": UNRETRIEVED, "quote_in": quote_in,
                "page_with_marker": any(q["id_is_page"] and q["page_marker"] for q in quote_in)}
    if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE:
        reason = BAD_QUOTE
    elif _squash(quote) not in _squash(chunk.content):
        reason = NOT_IN_CHUNK
    else:
        reason = PASS
    return {"chunk_id": cid, "alone_ok": reason == PASS, "alone_reason": reason}


def classify(raw: str, chunks: list) -> dict:
    """check.py parse_and_verify와 같은 순서로 처음 걸린 검사(reason)와 인용별 판정(citations)."""
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"reason": JSON_ERROR, "citations": []}
    if not isinstance(data, dict) or not isinstance(data.get("found"), bool):
        return {"reason": JSON_ERROR, "citations": []}
    if not data["found"]:
        return {"reason": FOUND_FALSE, "citations": []}
    answer, cited = data.get("answer"), data.get("citations")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(cited, list) or not cited:
        return {"reason": EMPTY, "citations": []}
    by_id = {c.id: c for c in chunks}
    cites = [_judge(item, by_id, chunks) for item in cited]
    return {"reason": next((c["alone_reason"] for c in cites if not c["alone_ok"]), PASS), "citations": cites}


def ask_fixed(question: str, chunks: list, complete, prompt_version: str, classify_chunks: list | None = None) -> dict:
    """service.py 77~85줄과 같은 흐름(같은 messages로 최대 2번)을 고정 조각으로. 모든 출력을 남긴다.

    classify_chunks: 분류·쪽 대조에 쓸 조각(태그의 page만 비운 실험에서 원래 쪽으로 대조하려고)
    """
    messages = build_messages(question, chunks, prompt_version)
    outputs, classes, result = [], [], None
    for _ in range(2):
        raw = complete(messages)
        outputs.append(raw)
        classes.append(classify(raw, classify_chunks or chunks))
        result = parse_and_verify(raw, chunks)
        if result:
            break
    return {"outputs": outputs, "classes": classes, "found": bool(result and result.found)}


def capture_deps(deps, rec: dict):
    """answer_question에 넘길 Deps를 감싸 답변 AI 출력·답변 AI에 간 조각·바꾸기 결과를 rec에 모은다."""
    rec.update(outputs=[], chunks=[], rewrite=None)

    def search(*args):
        found = deps.search(*args)
        rec["chunks"] = list(found)
        return found

    def diagnostic(model_id):
        extra = deps.diagnostic(model_id)
        seen = {c.id for c in rec["chunks"]}
        rec["chunks"] += [c for c in extra if c.id not in seen]  # service.py 72~74줄과 같은 덧붙임
        return extra

    def complete(messages):
        raw = deps.complete(messages)
        rec["outputs"].append(raw)
        return raw

    def rewrite(question, history):
        rec["rewrite"] = deps.rewrite(question, history)
        return rec["rewrite"]

    return replace(deps, search=search, diagnostic=diagnostic, complete=complete, rewrite=rewrite)
