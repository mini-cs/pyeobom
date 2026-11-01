import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    id: int
    doc_id: str
    doc_type: str           # "manual" | "guide"
    title: str              # 설명서 이름 또는 가이드 제목
    source_url: str         # 공식 문서 주소
    page: int | None        # 설명서 쪽 번호, 가이드는 None
    content: str
    score: float  # 코사인 거리(작을수록 가까움), 키워드 결과는 0.0

    @property
    def ref(self) -> str:  # "manual:32" 또는 "guide:<doc_id>"
        return f"manual:{self.page}" if self.doc_type == "manual" else f"guide:{self.doc_id}"


SQL = """
SELECT c.id, c.doc_id, d.doc_type, d.title, d.source_url, c.page, c.content, c.embedding <=> %(q)s::vector AS score
FROM chunks c
JOIN document_models dm ON dm.doc_id = c.doc_id
JOIN documents d ON d.id = c.doc_id
WHERE dm.model_id = %(model_id)s
ORDER BY score
LIMIT %(k)s
"""


def search_vector(conn, model_id: str, query_vec: list[float], k: int) -> list[Chunk]:
    # 모델 필터는 SQL에서 한다(프롬프트에 맡기지 않음). list는 double precision[]로 넘어가므로 ::vector로 형을 정한다

    rows = conn.execute(SQL, {"q": query_vec, "model_id": model_id, "k": k}).fetchall()
    return [Chunk(*row) for row in rows]


# ── 에러 코드 (결정기록 019) ──
_CODE = re.compile(r"(?<![A-Za-z0-9.])(?:([A-Za-z]{1,3})\s?(\d{1,3})|(\d{1,2})\s?([A-Za-z]{1,2})|([A-Za-z]{2,3}))(?![A-Za-z0-9])")
_ERROR_CONTEXT = re.compile(r"에러|코드|떴|떠|뜨|표시|라고")
_UNITS = {"V", "W", "A", "L", "G", "M", "KG", "ML", "CM", "MM", "HZ", "KW"}
_NOT_CODES = {"LG", "AI", "OK", "TV", "PC", "LED", "LCD", "USB", "APP", "WI", "FI"}  # 흔한 영문 약어


def extract_code_tokens(question: str) -> list[str]:
    """질문에서 에러 코드 후보를 뽑아 대문자·공백 없이 정규화한다("4 e" → "4E"). 글자만인 코드(OE·IE)는 에러 맥락이 있을 때만."""
    tokens = []
    for m in _CODE.finditer(question):
        letters_digits, digits_letters, letters_only = m[1] and m[1] + m[2], m[3] and m[3] + m[4], m[5]
        if digits_letters and m[4].upper() in _UNITS:
            continue
        token = (letters_digits or digits_letters or "").upper()
        if letters_only and letters_only.upper() not in _NOT_CODES and _ERROR_CONTEXT.search(question):
            token = letters_only.upper()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def contains_code(token: str, text: str) -> bool:
    """단어 경계로 코드를 찾는다(IEEE·IEC 안의 IE는 아님, "CH 05"처럼 글자와 숫자 사이 공백은 허용)."""
    pattern = r"\s?".join(re.escape(p) for p in re.findall(r"[A-Z]+|\d+", token))
    return re.search(rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None


def fetch_manual_pages(conn, model_id: str, pages: list[int]) -> list[Chunk]:
    """그 모델 설명서의 지정한 쪽 조각(진단 안내 쪽 덧붙이기용)."""
    if not pages:
        return []
    rows = conn.execute(
        """SELECT c.id, c.doc_id, d.doc_type, d.title, d.source_url, c.page, c.content, 0.0
           FROM chunks c JOIN document_models dm ON dm.doc_id = c.doc_id JOIN documents d ON d.id = c.doc_id
           WHERE dm.model_id = %s AND d.doc_type = 'manual' AND c.page = ANY(%s) ORDER BY c.page, c.id""",
        (model_id, pages)).fetchall()
    return [Chunk(*row) for row in rows]
