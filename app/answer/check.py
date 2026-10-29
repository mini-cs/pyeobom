import json
import re
from dataclasses import dataclass

from app.retrieval.search import Chunk

GUIDE_WARNING = "공용 콘텐츠라 모델에 따라 다를 수 있어요"
NOT_FOUND_MESSAGE = "설명서에서 찾지 못했어요. 공식 고객센터에 문의해 보세요."
MAX_QUOTE = 150  # 화면에 원문 통째 노출 금지(인용 150자 이내)


@dataclass
class Citation:
    doc_id: str
    doc_type: str
    title: str
    page: int | None
    url: str
    quote: str

    @property
    def ref(self) -> str:
        return f"manual:{self.page}" if self.doc_type == "manual" else f"guide:{self.doc_id}"


@dataclass
class Answer:
    found: bool
    answer: str
    citations: list[Citation]


def _squash(text: str) -> str:
    return " ".join(text.split())


def parse_and_verify(raw: str, chunks: list[Chunk]) -> Answer | None:
    """AI 출력을 읽고, 인용이 실제로 검색된 조각에 그대로 있는지 확인한다. 하나라도 어긋나면 None."""
    raw = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("found"), bool):
        return None
    if not data["found"]:
        return Answer(False, NOT_FOUND_MESSAGE, [])
    answer, cited = data.get("answer"), data.get("citations")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(cited, list) or not cited:
        return None
    by_id = {c.id: c for c in chunks}
    citations = []
    for item in cited:
        chunk = by_id.get(item.get("chunk_id")) if isinstance(item, dict) else None
        quote = item.get("quote") if chunk else None
        if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE:
            return None
        if _squash(quote) not in _squash(chunk.content):
            return None  # 지어낸 인용
        citations.append(Citation(chunk.doc_id, chunk.doc_type, chunk.title, chunk.page, chunk.source_url, quote))
    return Answer(True, answer.strip(), citations)
