"""중간 점검 시연: 같은 질문을 세 모델로 검색해, 각 모델에 연결된 문서의 조각만 나오는지 보여 준다.

사용법: .venv/Scripts/python -X utf8 experiments/search_demo.py ["질문"]
로컬 .env의 DATABASE_URL·OPENAI_API_KEY를 쓴다(값은 출력하지 않음). 조회만 하고 DB를 바꾸지 않는다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest.__main__ import load_env  # noqa: E402

load_env()

from app.catalog.registry import load_models  # noqa: E402
from app.core.db import get_conn  # noqa: E402
from app.retrieval.embeddings import embed_query  # noqa: E402
from app.retrieval.search import search_vector  # noqa: E402

question = sys.argv[1] if len(sys.argv) > 1 else "물이 안 빠지고 에러가 떠요"
query_vec = embed_query(question)  # 질문 임베딩은 한 번만 만든다
print(f"질문: {question}\n")
with get_conn() as conn:
    for model in load_models():
        linked = {r[0] for r in conn.execute("SELECT doc_id FROM document_models WHERE model_id = %s", (model["id"],))}
        chunks = search_vector(conn, model["id"], query_vec, k=3)
        mixed = [c.doc_id for c in chunks if c.doc_id not in linked]
        print(f"[{model['display_name']}] 연결 문서 {len(linked)}개 · 다른 모델 문서 섞임 {len(mixed)}개")
        for c in chunks:
            snippet = " ".join(c.content.split())[:40]  # 인용은 짧게(원문 통째 노출 금지)
            print(f"  {c.ref:32s} 거리 {c.score:.3f} | {snippet}…")
        print()
