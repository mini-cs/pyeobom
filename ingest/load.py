import json
from pathlib import Path

from ingest.chunk import chunk_pages
from ingest.clean import clean_text, drop_out_of_scope
from ingest.html import extract_html
from ingest.pdf import extract_pages

ROOT = Path(__file__).resolve().parents[1]


def load_documents(path: str = "data/documents.json") -> list[dict]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def build_chunks(doc: dict) -> tuple[list[tuple[int | None, str]], int]:
    """(쪽 번호 또는 None, 조각 글자) 목록과 적용 범위 밖이라 뺀 문단 수."""
    path = str(ROOT / doc["file"])
    if doc["doc_type"] == "manual":
        return chunk_pages([(page, clean_text(text)) for page, text in extract_pages(path)]), 0
    text = extract_html(path, doc["content_selector"], doc["title"])
    text, dropped = drop_out_of_scope(text, doc.get("exclude_keywords", []))
    return [(None, t) for _, t in chunk_pages([(0, text)])], dropped  # 가이드는 쪽이 없어 page = NULL


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
