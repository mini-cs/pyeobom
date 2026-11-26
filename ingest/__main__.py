"""python -m ingest --doc-id <id> : documents.json의 문서 하나를 조각 → 임베딩 → Neon에 넣는다."""
import argparse
import os

from ingest.load import ROOT, chunks_with_sources, load_documents, save


def load_env() -> None:
    # 로컬 전용: .env를 환경 변수로 읽는다(이미 있는 값은 덮지 않음). 값은 출력하지 않는다
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _document(doc_id: str) -> dict:
    docs = {d["id"]: d for d in load_documents()}
    if doc_id not in docs:
        raise SystemExit(f"documents.json에 없는 문서: {doc_id} (있는 것: {', '.join(docs)})")
    return docs[doc_id]


def ingest_document(doc_id: str, *, connect=None, embed=None) -> dict:
    """조각 → 임베딩을 먼저 다 만든 뒤 연결을 열어 save()하고 바로 닫는다(2차 Global 8 DB 연결 규칙).
    connect·embed가 없으면 운영 것(get_conn·embed_texts)을 쓴다. 설정은 부른 쪽이 load_env 한 뒤에 읽힌다."""
    doc = _document(doc_id)
    from app.catalog.registry import load_models
    from app.core.config import get_settings
    from app.core.db import get_conn  # load_env 뒤에 설정을 읽게 한다
    from app.retrieval.embeddings import embed_texts
    from evaluation.run_config import warn_if_different
    from ingest.describe import ingest_texts

    chunks_src, dropped = chunks_with_sources(doc)
    chunks = [(page, text) for page, text, _ in chunks_src]  # 저장 본문은 원문 그대로(설명은 임베딩 입력에만)
    models = {m["id"]: m for m in load_models()}
    settings = get_settings()
    warn_if_different(settings)  # 경고만(멈추지 않음): 조각 설명 설정이 운영 기록과 다르면 알린다(설계 5절 4, 검토 I1)
    embeddings = (embed or embed_texts)(ingest_texts(doc, chunks_src, settings, models))
    with (connect or get_conn)() as conn:
        save(conn, doc, chunks, embeddings)
    return {"doc_id": doc["id"], "chunks": len(chunks), "dropped": dropped}


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ingest")
    parser.add_argument("--doc-id", required=True)
    args = parser.parse_args()
    doc = _document(args.doc_id)
    load_env()
    out = ingest_document(args.doc_id)
    print(f"{doc['id']}: 조각 {out['chunks']}개, 적용 범위 밖이라 뺀 문단 {out['dropped']}개, 연결 모델 {', '.join(doc['model_ids'])}")


if __name__ == "__main__":
    main()
