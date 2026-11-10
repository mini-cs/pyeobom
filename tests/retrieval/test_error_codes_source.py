import json
import re
from pathlib import Path

import pytest

from app.catalog.registry import load_models
from app.core.brand_guard import brand_key
from app.retrieval.search import contains_code

CODES = json.loads((Path(__file__).resolve().parents[2] / "data" / "error_codes.json").read_text(encoding="utf-8"))["codes"]
BRAND_OF = {m["id"]: brand_key(m["brand"]) for m in load_models()}
CASES = [(brand, code, ref) for brand, codes in CODES.items() for code, refs in codes.items() for ref in refs]


@pytest.mark.integration
@pytest.mark.parametrize("brand, code, ref", CASES)
def test_code_appears_in_its_source(conn, brand, code, ref):
    doc_id, _, page = ref.partition(":")
    rows = conn.execute("SELECT content FROM chunks WHERE doc_id = %s AND (%s::int IS NULL OR page = %s::int)",
                        (doc_id, page or None, page or None)).fetchall()
    models = {r[0] for r in conn.execute("SELECT model_id FROM document_models WHERE doc_id = %s", (doc_id,))}
    assert rows and {BRAND_OF[m] for m in models} == {brand}  # 출처 문서가 그 브랜드 모델의 문서
    texts = [r[0] for r in rows]
    if any(contains_code(code, t) for t in texts):
        return
    # LG 에어컨 가이드는 "CH05, 53, E0…"처럼 CH를 빼고 숫자만 적은 코드가 있다
    digits = re.fullmatch(r"CH(\d+)", code)
    assert digits and any("CH" in t and re.search(rf"(?<!\d){digits[1]}(?!\d)", t) for t in texts), (code, ref)
