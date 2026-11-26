"""모델 추가 도구(계획 2차 Task 8 Step 2). 실제 Neon·OpenAI·Supabase는 부르지 않는다(가짜 connect·embed, 비용 0).
비교용 모델(SEW-HBW122L)에는 돌리지 않는다: 검사는 지금 운영 설명서 3개로만(2026-11-26 사용자 지시)."""
import json
import shutil
from pathlib import Path

import pytest

import app.catalog.registry as registry
import app.core.config as config
import ingest.__main__ as main_mod
from app.core.config import Settings
from ingest import add_model
from ingest.load import load_documents
from tests.ingest.db_rule import FakeConn

ROOT = Path(__file__).resolve().parents[2]
MANUAL = {"id": "manual-x", "doc_type": "manual", "title": "샘플 설명서", "file": "unused.pdf"}
FILLER = "세탁조 청소는 한 달에 한 번 해 주세요. " * 2  # 공백을 빼면 32자: 30자가 넘는 쪽 글
DRAFT = dict(doc_id="manual-new-x1", model_id="washer-new-x1", brand="LG", appliance="washer",
             title="LG 드럼세탁기 사용설명서", source_url="https://example.com/manuals", pdf="data/manuals/x1.pdf",
             codes=["X1*N*", "X2*N*"], fetched_at="2026-11-26", name="LG 드럼세탁기",
             scope_note="모델 전용 — 표지 모델명 X1*N*/X2*N*", model_name_hint="제품에 붙은 라벨에서 모델명을 확인하세요")


# ── 검사(check) ──
def test_check_flags_textless_pdf():
    pages = [(1, FILLER), (2, " \n "), (3, "12"), (4, "\n")]  # 4쪽 중 3쪽이 30자 미만
    result = add_model.check_document(MANUAL, extract=lambda path: pages)
    assert result["pages"] == 4 and result["text_pages"] == 1 and result["empty_pages"] == [2, 3, 4]
    assert result["ok"] is False


def test_check_flags_remaining_page_marker():
    pages = [(1, "1\n" + FILLER), (2, FILLER + "\n2\n" + FILLER)]  # 2쪽: 앞 20자 밖에 쪽 번호만 있는 줄
    result = add_model.check_document(MANUAL, extract=lambda path: pages)
    assert result["empty_pages"] == [] and result["remaining_markers"] == [(2, 1)]
    assert result["ok"] is False
    clean = add_model.check_document(MANUAL, extract=lambda path: [(1, "1\n" + FILLER), (2, "2\n" + FILLER)])
    assert clean["ok"] is True and clean["remaining_markers"] == []


def test_existing_three_manuals_pass_check():
    manuals = [d for d in load_documents() if d["doc_type"] == "manual"]
    assert len(manuals) == 3
    missing = [d["id"] for d in manuals if not (ROOT / d["file"]).exists()]
    if missing:
        pytest.skip(f"로컬 PDF 없음: {missing}")
    for doc in manuals:
        result = add_model.check_document(doc)
        assert result["ok"], (doc["id"], result["empty_pages"], result["remaining_markers"])


# ── 초안(draft) ──
def test_draft_refuses_existing_id():
    with pytest.raises(ValueError):
        add_model.draft_entries(**{**DRAFT, "doc_id": "manual-lg-fx25"})
    with pytest.raises(ValueError):
        add_model.draft_entries(**{**DRAFT, "model_id": "washer-lg-fx25"})


def test_draft_passes_catalog_and_document_checks():
    doc, model = add_model.draft_entries(**DRAFT)
    # tests/ingest/test_documents.py의 필드 검사
    assert {"id", "doc_type", "title", "source_url", "scope_note", "model_ids", "file", "fetched_at"} <= doc.keys()
    assert doc["doc_type"] == "manual" and doc["source_url"].startswith("https://") and doc["model_ids"] == [model["id"]]
    # tests/catalog/test_registry.py의 필드 검사
    assert {"id", "brand", "appliance", "model_name", "display_name", "name", "model_codes", "official_url",
            "model_name_hint"} <= model.keys()
    assert model["official_url"].startswith("https://")
    assert model["name"] and "(" not in model["name"] and model["display_name"].startswith(model["name"])
    assert model["model_codes"] and all(code in model["display_name"] for code in model["model_codes"])
    assert "short_name" not in model and model["diagnostic_refs"] == []
    assert model["display_name"] == "LG 드럼세탁기 (X1*N*·X2*N*)" and model["model_name"] == "X1*N* / X2*N*"


def test_draft_refuses_values_the_checks_would_reject():
    for bad in ({"appliance": "fridge"}, {"source_url": "http://example.com"}, {"name": "LG (드럼)"}, {"codes": []},
                # 검토 지적(2026-11-26): 날짜는 YYYY-MM-DD만, 문서·모델 id는 confirm과 같은 모양(소문자·숫자·하이픈)만
                {"fetched_at": "2026/11/26"}, {"fetched_at": "20261126"}, {"fetched_at": "2026-13-01"},
                {"doc_id": "Manual-X"}, {"doc_id": "../manual-x"}, {"model_id": "washer_x"}, {"model_id": "washer x"}):
        with pytest.raises(ValueError):
            add_model.draft_entries(**{**DRAFT, **bad})


def test_json_writers_keep_current_format(tmp_path):
    docs_text = (ROOT / "data" / "documents.json").read_text(encoding="utf-8")
    models_text = (ROOT / "data" / "models.json").read_text(encoding="utf-8")
    assert add_model.dump_documents(json.loads(docs_text)) == docs_text
    assert add_model.dump_models(json.loads(models_text)) == models_text
    shutil.copy(ROOT / "data" / "documents.json", tmp_path / "documents.json")
    shutil.copy(ROOT / "data" / "models.json", tmp_path / "models.json")
    doc, model = add_model.draft_entries(**DRAFT)
    add_model.write_entries(doc, model, documents_path=tmp_path / "documents.json", models_path=tmp_path / "models.json")
    new_docs = (tmp_path / "documents.json").read_text(encoding="utf-8")
    assert new_docs.startswith(docs_text.rstrip()[:-1].rstrip()) and json.loads(new_docs)[-1] == doc
    assert json.loads((tmp_path / "models.json").read_text(encoding="utf-8"))[-1] == model


# ── 가이드 연결(link-guide) ──
def test_link_guide_does_not_touch_chunks(tmp_path):
    docs = tmp_path / "documents.json"
    shutil.copy(ROOT / "data" / "documents.json", docs)
    conn = FakeConn(rowcount=1)
    connect = _connect(conn)
    assert add_model.link_guide("guide-lg-drum-errors", "aircon-lg-sq06fa1wds", connect=connect, documents_path=docs) is True
    assert len(conn.sql) == 1 and "chunks" not in conn.sql[0]
    assert conn.sql[0].startswith("INSERT INTO document_models") and "ON CONFLICT DO NOTHING" in conn.sql[0]
    guide = next(d for d in json.loads(docs.read_text(encoding="utf-8")) if d["id"] == "guide-lg-drum-errors")
    assert guide["model_ids"] == ["washer-lg-fx25", "aircon-lg-sq06fa1wds"]
    # 다시 연결하면 DB는 그대로(0행), 파일에 두 번 넣지 않음
    assert add_model.link_guide("guide-lg-drum-errors", "aircon-lg-sq06fa1wds", connect=_connect(FakeConn(rowcount=0)),
                                documents_path=docs) is False
    guide = next(d for d in json.loads(docs.read_text(encoding="utf-8")) if d["id"] == "guide-lg-drum-errors")
    assert guide["model_ids"] == ["washer-lg-fx25", "aircon-lg-sq06fa1wds"]


def test_link_guide_refuses_manual_or_unknown_model(tmp_path):
    docs = tmp_path / "documents.json"
    shutil.copy(ROOT / "data" / "documents.json", docs)
    for guide_id, model_id in (("manual-lg-fx25", "washer-lg-fx25"), ("guide-lg-drum-errors", "washer-none")):
        conn = FakeConn()
        with pytest.raises(ValueError):
            add_model.link_guide(guide_id, model_id, connect=_connect(conn), documents_path=docs)
        assert conn.sql == []
    assert docs.read_bytes() == (ROOT / "data" / "documents.json").read_bytes()


# ── 되돌리기(remove) ──
def _remove_answer(doc_type="manual", bundle=None, linked=1, variants=None, others=0):
    def answer(sql, params):
        if "to_regclass('bundle_chunks')" in sql:
            return ("bundle_chunks" if bundle is not None else None,)
        if "to_regclass('chunk_variants')" in sql:
            return ("chunk_variants" if variants is not None else None,)
        if sql.startswith("SELECT doc_type"):
            return (doc_type,) if doc_type else None
        if "FROM bundle_chunks" in sql:
            return (bundle,)
        if "FROM chunk_variants" in sql:
            return (variants,)
        if "FROM document_models WHERE doc_id = %s AND model_id = %s" in sql:
            return (linked,)
        if "FROM document_models WHERE doc_id = %s AND model_id <> %s" in sql:
            return (others,)
        return (7,)
    return answer


def test_remove_without_yes_deletes_nothing():
    conn = FakeConn(_remove_answer())
    out = add_model.remove_model_data("manual-x", "m1", connect=_connect(conn))
    assert out["deleted"] is False and out["chunks"] == 7 and out["documents"] == 1
    assert not any(s.startswith("DELETE") for s in conn.sql) and conn.transactions == 0


def test_remove_with_yes_deletes_in_one_transaction_and_keeps_bundle():
    conn = FakeConn(_remove_answer())
    out = add_model.remove_model_data("manual-x", "m1", connect=_connect(conn), yes=True)
    deletes = [s for s in conn.sql if s.startswith("DELETE")]
    assert out["deleted"] is True and conn.transactions == 1 and len(deletes) == 4
    assert all("bundle_chunks" not in s for s in deletes)


def test_remove_refuses_guide_unlinked_model_or_bundle_rows():
    for answer in (_remove_answer(doc_type="guide"), _remove_answer(linked=0), _remove_answer(bundle=5)):
        conn = FakeConn(answer)
        with pytest.raises(ValueError):
            add_model.remove_model_data("manual-x", "m1", connect=_connect(conn), yes=True)
        assert not any(s.startswith("DELETE") for s in conn.sql)


# 검토 지적 처리(2026-11-26 사용자 결정 1~3)
def test_remove_refuses_doc_missing_in_db():
    """문서 id 오타면 연결 확인 없이 그 모델의 연결을 다 지우던 길(검토 Important 3, 보안 ①)."""
    for yes in (False, True):
        conn = FakeConn(_remove_answer(doc_type=None))
        with pytest.raises(ValueError, match="DB에 없는 문서"):
            add_model.remove_model_data("manual-typo", "m1", connect=_connect(conn), yes=yes)
        assert not any(s.startswith("DELETE") for s in conn.sql)


def test_remove_keeps_other_documents_links():
    """가이드 연결은 가이드 문서와의 연결만 세고 지운다. 다른 설명서와의 연결은 남긴다."""
    conn = FakeConn(_remove_answer())
    add_model.remove_model_data("manual-x", "m1", connect=_connect(conn), yes=True)
    guide_count = next(s for s in conn.sql if s.startswith("SELECT count(*) FROM document_models") and "model_id = %s" in s
                       and "doc_id = %s" not in s)
    assert "doc_type = 'guide'" in guide_count
    for s in (s for s in conn.sql if s.startswith("DELETE FROM document_models")):
        assert " OR " not in s
        assert s == "DELETE FROM document_models WHERE doc_id = %s" or "doc_type = 'guide'" in s
    # 이 설명서가 다른 모델에도 연결돼 있으면 지우지 않는다(그 모델의 설명서 연결까지 사라지므로)
    conn = FakeConn(_remove_answer(others=1))
    with pytest.raises(ValueError, match="다른 모델"):
        add_model.remove_model_data("manual-x", "m1", connect=_connect(conn), yes=True)
    assert not any(s.startswith("DELETE") for s in conn.sql)


def test_remove_refuses_model_still_in_models_json():
    """Task 10 Step 1 순서: models.json에서 빼는 PR을 병합한 뒤에만 지운다(보안 ②)."""
    conn = FakeConn(_remove_answer())
    with pytest.raises(ValueError, match="models.json"):
        add_model.remove_model_data("manual-lg-fx25", "washer-lg-fx25", connect=_connect(conn), yes=True)
    assert conn.sql == []


def test_remove_preview_counts_chunk_variants():
    """chunk_variants는 chunks를 ON DELETE CASCADE로 참조해 함께 지워진다(measure/chunk_variants.sql). 표가 없으면 0."""
    out = add_model.remove_model_data("manual-x", "m1", connect=_connect(FakeConn(_remove_answer(variants=4))))
    assert out["chunk_variants"] == 4
    out = add_model.remove_model_data("manual-x", "m1", connect=_connect(FakeConn(_remove_answer())))
    assert out["chunk_variants"] == 0


# ── 에러 코드 후보(codes) ──
def test_error_code_candidates_lists_code_like_tokens():
    pages = [(1, "표시창에 4E 가 나오면 급수를 확인하세요. 에러 dE 표시"), (2, "CH10 오류, 4E 다시, 세탁 용량 9kg")]
    assert add_model.error_code_candidates(MANUAL, extract=lambda path: pages) == ["4E", "DE", "CH10"]


# ── 적재(ingest) ──
def test_ingest_main_behaves_as_before(monkeypatch, capsys):
    import app.core.db as db
    import app.retrieval.embeddings as embeddings
    from contextlib import contextmanager

    doc = {**MANUAL, "source_url": "https://example.com", "scope_note": "샘플", "model_ids": ["m1"], "fetched_at": "2026-11-26"}
    seen = {}

    @contextmanager
    def fake_conn():
        yield "conn"
    monkeypatch.setattr(main_mod, "load_documents", lambda: [doc])
    monkeypatch.setattr(main_mod, "load_env", lambda: None)
    monkeypatch.setattr(main_mod, "chunks_with_sources", lambda d: ([(3, "본문 1", "쪽 글"), (None, "본문 2", "글")], 4))
    monkeypatch.setattr(main_mod, "save", lambda conn, d, chunks, embs: seen.update(conn=conn, chunks=chunks, embs=embs))
    monkeypatch.setattr(db, "get_conn", fake_conn)
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.0]] * len(texts))
    monkeypatch.setattr(config, "get_settings", lambda: Settings(
        openai_api_key="", database_url="", openai_embed_model="text-embedding-3-small",
        openai_chat_model="gpt-6-luna", embed_dim=1536))
    monkeypatch.setattr(registry, "load_models", lambda: [{"id": "m1", "display_name": "모델1"}])
    monkeypatch.setattr("sys.argv", ["ingest", "--doc-id", "manual-x"])
    main_mod.main()
    assert seen == {"conn": "conn", "chunks": [(3, "본문 1"), (None, "본문 2")], "embs": [[0.0], [0.0]]}
    assert capsys.readouterr().out.endswith("manual-x: 조각 2개, 적용 범위 밖이라 뺀 문단 4개, 연결 모델 m1\n")
    monkeypatch.setattr("sys.argv", ["ingest", "--doc-id", "manual-none"])
    with pytest.raises(SystemExit, match="documents.json에 없는 문서: manual-none"):
        main_mod.main()


def test_ingest_command_refuses_over_budget(monkeypatch, tmp_path):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("date,item,estimate_usd,actual_usd,note\n2026-11-26,앞 측정,0.995,,\n", encoding="utf-8")
    called = []
    monkeypatch.setattr(add_model, "LEDGER", ledger)
    monkeypatch.setattr(add_model, "load_env", lambda: None)
    monkeypatch.setattr(add_model, "ingest_manual", lambda doc_id, **kw: called.append((doc_id, kw)) or {})
    with pytest.raises(SystemExit, match="장부"):
        add_model.main(["ingest", "--doc-id", "manual-lg-fx25", "--estimate-usd", "0.01"])
    assert called == []
    add_model.main(["ingest", "--doc-id", "manual-lg-fx25", "--estimate-usd", "0.005"])
    add_model.main(["ingest", "--doc-id", "manual-lg-fx25", "--estimate-usd", "0.001", "--yes"])
    assert called == [("manual-lg-fx25", {"yes": False}), ("manual-lg-fx25", {"yes": True})]


# 검토 지적 처리(2026-11-26 사용자 결정 4·5)
PROD = Settings(openai_api_key="", database_url="", openai_embed_model="text-embedding-3-small",
                openai_chat_model="gpt-6-luna", embed_dim=1536, rewrite_model="gpt-6-luna")  # 운영 그대로


def test_prod_settings_fixture_matches_production():
    from evaluation.run_config import differences
    assert differences(PROD) == []


@pytest.fixture
def ingest_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "get_settings", lambda: PROD)
    monkeypatch.setattr(add_model, "ingest_document", lambda doc_id, **kw: calls.append(doc_id) or {"doc_id": doc_id})
    return calls


def test_ingest_refuses_guide_and_existing_without_yes(ingest_calls):
    """가이드는 다시 적재하지 않는다(Global 9). 이미 DB에 있는 문서는 --yes 없이 지우고 다시 넣지 않는다(CLAUDE.md)."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="가이드"):
        add_model.ingest_manual("guide-lg-drum-errors", connect=_connect(conn))
    assert conn.sql == [] and ingest_calls == []
    exists = FakeConn(lambda sql, params: (1,))
    with pytest.raises(ValueError, match="--yes"):
        add_model.ingest_manual("manual-lg-fx25", connect=_connect(exists))
    assert ingest_calls == [] and exists.sql == ["SELECT 1 FROM documents WHERE id = %s"]
    add_model.ingest_manual("manual-lg-fx25", connect=_connect(exists), yes=True)
    add_model.ingest_manual("manual-lg-fx25", connect=_connect(FakeConn(lambda sql, params: None)))
    assert ingest_calls == ["manual-lg-fx25", "manual-lg-fx25"]


def test_ingest_stops_on_non_production_settings(monkeypatch, ingest_calls):
    from dataclasses import replace
    for bad in ({"openai_embed_model": "text-embedding-3-large"}, {"chunk_context_model": "gpt-6-luna"},
                {"refine_model": "gpt-6-luna"}, {"openai_embed_dimensions": 512}):
        monkeypatch.setattr(config, "get_settings", lambda bad=bad: replace(PROD, **bad))
        conn = FakeConn()
        with pytest.raises(ValueError, match="운영"):
            add_model.ingest_manual("manual-lg-fx25", connect=_connect(conn))
        assert conn.sql == [] and ingest_calls == []


def _connect(conn):
    from contextlib import contextmanager

    @contextmanager
    def connect():
        yield conn
    return connect
