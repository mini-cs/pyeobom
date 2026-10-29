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
