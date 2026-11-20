"""조각 설명 붙이기(v1.95) Task 2: 운영 조각과 원본 짝짓기, 실험 벌 저장, 비용 어림, 자동 검사, 표본."""
from types import SimpleNamespace

import pytest

from ingest.describe import ContextItem
from measure.v17_bundle import BundleChunk

DOCS = [{"id": "manual-a", "doc_type": "manual"}, {"id": "guide-b", "doc_type": "guide"}]
PROD = [BundleChunk(5, "manual-a", 1, "쪽1 조각"), BundleChunk(6, "manual-a", 2, "쪽2 조각"),
        BundleChunk(7, "guide-b", None, "가이드 조각")]


def _item(doc_id, page, content, doc_type="manual"):
    return ContextItem(doc_id, doc_type, page, content, f"글 {content}", "문서 — 모델")


FILE_ITEMS = {"manual-a": [_item("manual-a", 1, "쪽1 조각"), _item("manual-a", 2, "쪽2 조각")],
              "guide-b": [_item("guide-b", None, "가이드 조각", "guide")]}


def _conn(chunks):
    rows = [(c.id, c.doc_id, c.page, c.content) for c in chunks]
    return SimpleNamespace(execute=lambda sql, *a: SimpleNamespace(fetchall=lambda: rows))


def _cc(monkeypatch):
    from measure import chunk_context
    monkeypatch.setattr(chunk_context, "context_items", lambda doc, models: FILE_ITEMS[doc["id"]])
    return chunk_context


def test_production_items_pairs_by_doc_in_id_order(monkeypatch):
    cc = _cc(monkeypatch)
    # 운영 번호 순이 문서 순과 섞여 있어도 문서별로 짝짓고, 결과는 운영 번호 순
    prod = [BundleChunk(5, "manual-a", 1, "쪽1 조각"), BundleChunk(6, "guide-b", None, "가이드 조각"),
            BundleChunk(7, "manual-a", 2, "쪽2 조각")]
    pairs = cc.production_items(_conn(prod), DOCS, {})
    assert [c.id for c, _ in pairs] == [5, 6, 7]
    assert [(i.doc_id, i.page, i.content, i.chunk_id) for _, i in pairs] == [
        ("manual-a", 1, "쪽1 조각", 5), ("guide-b", None, "가이드 조각", 6), ("manual-a", 2, "쪽2 조각", 7)]
    assert pairs[0][1].source == "글 쪽1 조각"


def test_production_items_refuses_text_mismatch(monkeypatch):
    cc = _cc(monkeypatch)
    bad = [PROD[0], BundleChunk(6, "manual-a", 2, "비밀 본문 글자"), PROD[2]]
    with pytest.raises(SystemExit) as e:
        cc.production_items(_conn(bad), DOCS, {})
    assert "manual-a" in str(e.value) and "비밀 본문 글자" not in str(e.value) and "쪽2 조각" not in str(e.value)
    with pytest.raises(SystemExit):  # DB에만 있는 문서
        cc.production_items(_conn(PROD + [BundleChunk(8, "guide-z", None, "다른")]), DOCS, {})
    with pytest.raises(SystemExit):  # 파일에만 있는 문서
        cc.production_items(_conn(PROD[:2]), DOCS, {})


def test_store_contextual_refuses_missing_description(monkeypatch):
    cc = _cc(monkeypatch)
    pairs = [(c, FILE_ITEMS[c.doc_id][0]) for c in PROD]
    monkeypatch.setattr(cc, "store_reembedded", lambda *a, **k: pytest.fail("저장 전에 멈춰야 함"))
    with pytest.raises(SystemExit):
        cc.store_contextual(None, pairs, ["설명", "", "설명"])
    with pytest.raises(SystemExit):
        cc.store_contextual(None, pairs, ["설명", "설명"])
    seen = {}
    monkeypatch.setattr(cc, "store_reembedded", lambda name, chunks, spec, *, conn, inputs: seen.update(
        name=name, chunks=chunks, spec=spec, inputs=inputs) or len(chunks))
    assert cc.store_contextual("conn", pairs, ["가", "나", "다"]) == 3
    assert seen["name"] == "ctx_small" and seen["spec"] == cc.SMALL and seen["chunks"] == PROD
    assert seen["inputs"] == ["가\n쪽1 조각", "나\n쪽2 조각", "다\n가이드 조각"]


def test_estimate_describe_upper_bound(monkeypatch):
    cc = _cc(monkeypatch)
    from ingest.describe import MAX_OUTPUT_TOKENS, build_prompt
    from measure.stage2 import PRICE_IN, PRICE_OUT
    items = FILE_ITEMS["manual-a"]
    chars = sum(len(build_prompt(i)) for i in items)
    got = cc.estimate_describe(items)
    assert got["items"] == 2 and got["input_chars"] == chars
    assert got["cost_usd"] == pytest.approx(chars * PRICE_IN / 1e6 + 2 * MAX_OUTPUT_TOKENS * PRICE_OUT / 1e6)


def test_unsupported_tokens_flags_new_number_and_code(monkeypatch):
    cc = _cc(monkeypatch)
    item = ContextItem("guide-b", "guide", None, "5C 에러가 뜨면 배수 필터를 청소", "5c 에러 해결 가이드 글", "드럼 세탁기 — 모델")
    assert cc.unsupported_tokens("5C 에러에 60분 기다린 뒤 E5와 60 확인", item) == ["60", "E5"]
    assert cc.unsupported_tokens("드럼 세탁기 5C 에러 해결", item) == []


def test_sample_items_is_seeded_and_20(monkeypatch):
    cc = _cc(monkeypatch)
    pairs = [(BundleChunk(i, "d", 1, "x"), None) for i in range(100, 432)]
    a, b = cc.sample_items(pairs), cc.sample_items(pairs)
    assert a == b and len(a) == 20 == len(set(a)) and set(a) <= set(range(100, 432))
    assert cc.sample_items(pairs, seed=1) != a and cc.SAMPLE_SEED == 20261121
