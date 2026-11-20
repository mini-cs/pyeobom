import json
from pathlib import Path

from ingest.chunk import chunk_pages
from ingest.clean import clean_text, drop_out_of_scope
from ingest.html import extract_html
from ingest.page_marker import strip_page_marker
from ingest.pdf import extract_pages

ROOT = Path(__file__).resolve().parents[1]


def load_documents(path: str = "data/documents.json") -> list[dict]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def chunks_with_sources(doc: dict) -> tuple[list[tuple[int | None, str, str]], int]:
    """(쪽 번호 또는 None, 조각 글자, 그 조각이 잘려 나온 글) 목록과 적용 범위 밖이라 뺀 문단 수.
    잘려 나온 글은 조각 설명(v1.95)을 쓸 때 AI에게 주는 글이다: 설명서는 그 쪽 글, 가이드는 가이드 글 전체."""
    path = str(ROOT / doc["file"])
    if doc["doc_type"] == "manual":
        # 쪽 표시(앞 20자 안 쪽 번호)를 지운다: v1.7 결정기록 032, 측정한 strip_800과 같은 흐름(끝 검사 끔)
        pages = [(page, strip_page_marker(clean_text(text), page)[0]) for page, text in extract_pages(path)]
        source = dict(pages)
        return [(page, t, source[page]) for page, t in chunk_pages(pages)], 0  # 조각은 쪽을 넘지 않는다
    text = extract_html(path, doc["content_selector"], doc["title"])
    text, dropped = drop_out_of_scope(text, doc.get("exclude_keywords", []))
    return [(None, t, text) for _, t in chunk_pages([(0, text)])], dropped  # 가이드는 쪽이 없어 page = NULL


def build_chunks(doc: dict) -> tuple[list[tuple[int | None, str]], int]:
    """(쪽 번호 또는 None, 조각 글자) 목록과 적용 범위 밖이라 뺀 문단 수."""
    items, dropped = chunks_with_sources(doc)
    return [(page, t) for page, t, _ in items], dropped


def save(conn, doc: dict, chunks: list[tuple[int | None, str]], embeddings: list[list[float]]) -> None:
    """같은 doc_id를 다시 넣으면 기존 조각·모델 연결을 지우고 새로 넣는다(한 트랜잭션)."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """INSERT INTO documents (id, doc_type, title, source_url, scope_note, fetched_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET doc_type = EXCLUDED.doc_type, title = EXCLUDED.title,
                 source_url = EXCLUDED.source_url, scope_note = EXCLUDED.scope_note, fetched_at = EXCLUDED.fetched_at""",
            (doc["id"], doc["doc_type"], doc["title"], doc["source_url"], doc["scope_note"], doc["fetched_at"]))
        cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc["id"],))
        cur.execute("DELETE FROM document_models WHERE doc_id = %s", (doc["id"],))
        cur.executemany("INSERT INTO document_models (doc_id, model_id) VALUES (%s, %s)",
                        [(doc["id"], m) for m in doc["model_ids"]])
        cur.executemany("INSERT INTO chunks (doc_id, page, content, embedding) VALUES (%s, %s, %s, %s)",
                        [(doc["id"], page, text, vec) for (page, text), vec in zip(chunks, embeddings, strict=True)])
