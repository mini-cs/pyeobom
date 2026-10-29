"""python -m ingest --doc-id <id> : documents.json의 문서 하나를 조각 → 임베딩 → Neon에 넣는다."""
import argparse
import os

from ingest.load import ROOT, build_chunks, load_documents, save


def load_env() -> None:
    # 로컬 전용: .env를 환경 변수로 읽는다(이미 있는 값은 덮지 않음). 값은 출력하지 않는다
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ingest")
    parser.add_argument("--doc-id", required=True)
    args = parser.parse_args()
    docs = {d["id"]: d for d in load_documents()}
    if args.doc_id not in docs:
        raise SystemExit(f"documents.json에 없는 문서: {args.doc_id} (있는 것: {', '.join(docs)})")
    doc = docs[args.doc_id]

    load_env()
    from app.core.db import get_conn  # load_env 뒤에 설정을 읽게 한다
    from app.retrieval.embeddings import embed_texts

    chunks, dropped = build_chunks(doc)
    embeddings = embed_texts([text for _, text in chunks])
    with get_conn() as conn:
        save(conn, doc, chunks, embeddings)
    print(f"{doc['id']}: 조각 {len(chunks)}개, 적용 범위 밖이라 뺀 문단 {dropped}개, 연결 모델 {', '.join(doc['model_ids'])}")


if __name__ == "__main__":
    main()
