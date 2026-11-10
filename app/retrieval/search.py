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


# 검색 개선 실험 색인(measure/chunk_variants.sql). 값: (후보로 쓸 실험 행 종류, 원래 조각 임베딩도 후보에 넣는지)
# M2는 max(조각, 만든 질문), 조합 m1_m2는 max(M1 제목 붙인 조각, 그 조각의 M2 질문들)
VARIANTS = {"m1_title": (["m1_title"], False), "m2_question": (["m2_question"], True),
            "m1_m2": (["m1_title", "m2_question"], False)}

VARIANT_SQL = """
WITH cand AS (
  SELECT v.chunk_id, v.embedding <=> %(q)s::vector AS score FROM chunk_variants v WHERE v.variant = ANY(%(kinds)s)
  UNION ALL
  SELECT c.id, c.embedding <=> %(q)s::vector FROM chunks c WHERE %(with_original)s
), best AS (SELECT chunk_id, min(score) AS score FROM cand GROUP BY chunk_id)
SELECT c.id, c.doc_id, d.doc_type, d.title, d.source_url, c.page, c.content, b.score
FROM best b
JOIN chunks c ON c.id = b.chunk_id
JOIN document_models dm ON dm.doc_id = c.doc_id
JOIN documents d ON d.id = c.doc_id
WHERE dm.model_id = %(model_id)s
ORDER BY b.score
LIMIT %(k)s
"""


def search_vector(conn, model_id: str, query_vec: list[float], k: int, variant: str | None = None) -> list[Chunk]:
    # 모델 필터는 SQL에서 한다(프롬프트에 맡기지 않음). list는 double precision[]로 넘어가므로 ::vector로 형을 정한다
    params = {"q": query_vec, "model_id": model_id, "k": k}
    if variant is None:  # 운영
        return [Chunk(*row) for row in conn.execute(SQL, params).fetchall()]
    if variant not in VARIANTS:
        raise ValueError(f"모르는 실험 색인: {variant}")
    # 조각마다 가장 가까운 거리를 점수로 쓰고, 답변에는 원래 조각 본문이 간다
    kinds, with_original = VARIANTS[variant]
    rows = conn.execute(VARIANT_SQL, params | {"kinds": kinds, "with_original": with_original}).fetchall()
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


def needs_diagnostic(question: str, chunks: list) -> bool:
    """질문의 에러 코드 중 하나라도 검색된 조각 어디에도 없으면 진단 안내 쪽을 덧붙인다(결정기록 019)."""
    tokens = extract_code_tokens(question)
    return bool(tokens) and not all(any(contains_code(code, c.content) for c in chunks) for code in tokens)


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


# ── v2b 하이브리드: 질문 단어 + 코드 키워드 ──
_NOUN_PARTICLE = re.compile(r"(에서|으로|은|는|을|를|에|로|만|도|과|와|의)$")
_DO_SUFFIX = re.compile(r"(했어요|해요|하고|하면|해서|하는)$")   # "청소해요" → "청소"
_VERB_END = re.compile(r"(요|고|게|서|면|죠|까)$")               # 남은 동사·어미("싶어요", "빼고")는 버린다
_STOP_WORDS = {"매번", "무슨", "에어컨", "세탁기", "제품", "다음", "어떻게"}
KEYWORD_K = 2  # 키워드 결과는 최대 2개만 앞에 넣고 나머지는 벡터 검색으로 채운다


def extract_keywords(question: str) -> list[str]:
    """질문에서 조사·어미·흔한 말을 빼고 남은 2글자 이상 한글 단어(코드는 extract_code_tokens가 맡는다)."""
    words = []
    for raw in re.findall(r"[가-힣]+", question):
        w = _NOUN_PARTICLE.sub("", raw)
        w = _DO_SUFFIX.sub("", w)
        if len(w) < 2 or _VERB_END.search(w) or w in _STOP_WORDS or w in words:
            continue
        words.append(w)
    return words


def search_keyword(conn, model_id: str, terms: list[str], query_vec: list[float], k: int) -> list[Chunk]:
    """선택 모델 문서 안에서 단어가 그대로 든 조각. 맞은 단어 수가 많은 순, 같으면 벡터 거리 순."""
    rows = conn.execute(
        """SELECT c.id, c.doc_id, d.doc_type, d.title, d.source_url, c.page, c.content, c.embedding <=> %s::vector
           FROM chunks c JOIN document_models dm ON dm.doc_id = c.doc_id JOIN documents d ON d.id = c.doc_id
           WHERE dm.model_id = %s AND c.content ILIKE ANY(%s)""",
        (query_vec, model_id, [f"%{t}%" for t in terms])).fetchall()
    def hits(c: Chunk) -> int:
        return sum(contains_code(t, c.content) if re.fullmatch(r"[A-Z0-9]+", t) else t in c.content for t in terms)
    scored = [(hits(c), c) for c in (Chunk(*r) for r in rows)]
    return [c for n, c in sorted(scored, key=lambda x: (-x[0], x[1].score)) if n > 0][:k]


def merge_results(keyword: list[Chunk], vector: list[Chunk], k: int) -> list[Chunk]:
    seen, merged = set(), []
    for c in keyword + vector:
        if c.id not in seen:
            seen.add(c.id)
            merged.append(c)
    return merged[:k]


def search_hybrid(conn, model_id: str, query_vec: list[float], question: str, k: int) -> list[Chunk]:
    terms = extract_code_tokens(question) + extract_keywords(question)
    keyword = search_keyword(conn, model_id, terms, query_vec, KEYWORD_K) if terms else []
    return merge_results(keyword, search_vector(conn, model_id, query_vec, k), k)
