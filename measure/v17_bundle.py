"""v1.7 실험 조각 한 벌 만들기·저장(계획 2026-11-16-v17-extraction-chunking-plan Task 5).

한 벌 = 설명서 조각(새 경계·본문, 번호 MANUAL_ID_BASE부터) + 운영 가이드 조각(번호·본문·쪽·임베딩 그대로 복사).
저장소는 measure/bundle_chunks.sql. 운영 chunks는 읽기만 한다.
"""
from collections.abc import Callable
from dataclasses import dataclass

from ingest.chunk import chunk_pages
from ingest.clean import clean_text
from ingest.page_marker import strip_page_marker, strip_plain_page
from ingest.plaintext import PlainPage, clean_plain_page, markdown_to_plain

MANUAL_ID_BASE = 1_000_000  # 운영 chunks.id(2026-11-16 최대 335)와 겹치지 않게


@dataclass
class BundleChunk:
    id: int
    doc_id: str
    page: int | None
    content: str


def chunk_plain_800(pages: list[tuple[int, PlainPage]]) -> list[tuple[int, str]]:
    return chunk_pages([(p, pp.text) for p, pp in pages], max_chars=800, overlap=100)


def manual_pages_from_pypdfium2(raw: dict[str, list[tuple[int, str]]]) -> dict[str, list[tuple[int, PlainPage]]]:
    """pypdfium2 쪽 글: 운영과 같은 clean_text → 쪽 표시 지우기."""
    return {doc_id: [(p, PlainPage(strip_page_marker(clean_text(t), p)[0], [])) for p, t in pages]
            for doc_id, pages in raw.items()}


def manual_pages_from_tool(md: dict[str, list[tuple[int, str]]]) -> dict[str, list[tuple[int, PlainPage]]]:
    """추출 도구의 쪽 마크다운: 평문 → clean_text → 쪽 표시 지우기(끝 검사 포함)."""
    return {doc_id: [(p, strip_plain_page(clean_plain_page(markdown_to_plain(t)), p, check_tail=True)[0]) for p, t in pages]
            for doc_id, pages in md.items()}


def load_guide_chunks(conn) -> list[BundleChunk]:
    rows = conn.execute("""SELECT c.id, c.doc_id, c.page, c.content FROM chunks c JOIN documents d ON d.id = c.doc_id
                           WHERE d.doc_type = 'guide' ORDER BY c.id""").fetchall()
    return [BundleChunk(*r) for r in rows]


def build_bundle(name: str, manual_pages: dict[str, list[tuple[int, PlainPage]]],
                 chunker: Callable[[list[tuple[int, PlainPage]]], list[tuple[int, str]]], *,
                 guides: list[BundleChunk]) -> list[BundleChunk]:
    if any(g.id >= MANUAL_ID_BASE for g in guides):
        raise ValueError("가이드 조각 번호가 설명서 조각 번호 범위와 겹친다")
    chunks: list[BundleChunk] = []
    for doc_id in sorted(manual_pages):
        for page, text in chunker(manual_pages[doc_id]):
            chunks.append(BundleChunk(MANUAL_ID_BASE + len(chunks), doc_id, page, text))
    return chunks + list(guides)


def bundle_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM bundle_chunks WHERE bundle = %s LIMIT 1", (name,)).fetchone() is not None


GUIDE_COPY_SQL = """INSERT INTO bundle_chunks (bundle, id, doc_id, page, content, embedding)
SELECT %s, id, doc_id, page, content, embedding FROM chunks WHERE id = ANY(%s)"""


def store_bundle(name: str, chunks: list[BundleChunk], *, apply: bool, conn=None, embed=None) -> int:
    """apply=False: 설명서 조각 본문 글자 수 합(예상 비용용, DB·API 호출 없음). apply=True: 넣은 행 수."""
    manual = [c for c in chunks if c.id >= MANUAL_ID_BASE]
    guide_ids = [c.id for c in chunks if c.id < MANUAL_ID_BASE]
    if not apply:
        return sum(len(c.content) for c in manual)
    if conn is None:
        from app.core.db import get_conn
        with get_conn() as conn:
            return store_bundle(name, chunks, apply=True, conn=conn, embed=embed)
    exists = bundle_exists(conn, name)
    # autocommit이 아니면 위 SELECT가 암묵 트랜잭션을 연다. 닫지 않으면 아래 transaction()이 SAVEPOINT가 되어
    # 부르는 쪽이 commit하지 않을 때 넣은 행이 되돌아가고, 임베딩 동안 트랜잭션이 열린 채로 남는다
    conn.commit()
    if exists:
        raise RuntimeError(f"이미 저장된 실험 조각 한 벌: {name} (지우기는 사용자 확인 뒤)")
    if embed is None:
        from app.retrieval.embeddings import embed_texts as embed
    vectors = embed([c.content for c in manual])  # 아무것도 붙이지 않고 순서·글자 그대로(ingest/__main__.py와 같음)
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany("INSERT INTO bundle_chunks (bundle, id, doc_id, page, content, embedding) VALUES (%s, %s, %s, %s, %s, %s)",
                        [(name, c.id, c.doc_id, c.page, c.content, v) for c, v in zip(manual, vectors, strict=True)])
        cur.execute(GUIDE_COPY_SQL, (name, guide_ids))
        if cur.rowcount != len(guide_ids):  # 운영에 없는 가이드 번호면 한 벌 전체를 되돌린다
            raise RuntimeError(f"가이드 조각 복사 수가 다름: {cur.rowcount} / {len(guide_ids)}")
    return len(manual) + len(guide_ids)
