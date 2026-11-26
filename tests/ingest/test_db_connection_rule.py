"""DB 연결 규칙(계획 2차 Task 8 Step 1, Global 8): AI·파일·대기 동안 연결을 쥐지 않는다. 실제 Neon·OpenAI는 부르지 않는다."""
import shutil
from pathlib import Path

import pytest

import app.catalog.registry as registry
import app.core.config as config
import ingest.__main__ as main_mod
from app.core.config import Settings
from ingest import add_model
from tests.ingest.db_rule import FakeConn, assert_no_ai_while_open, event_connect

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = Settings(openai_api_key="", database_url="", openai_embed_model="text-embedding-3-small",
                    openai_chat_model="gpt-6-luna", embed_dim=1536)
DOC = {"id": "manual-x", "doc_type": "manual", "title": "샘플 설명서", "source_url": "https://example.com/x",
       "scope_note": "샘플", "model_ids": ["m1"], "file": "unused.pdf", "fetched_at": "2026-11-26"}


def test_rule_checker_catches_ai_while_open_and_unclosed():
    assert_no_ai_while_open(["file", "ai", "open", "close", "file"])
    for bad in (["open", "ai", "close"], ["open", "file", "close"], ["open", "sleep", "close"], ["open"]):
        with pytest.raises(AssertionError):
            assert_no_ai_while_open(bad)


@pytest.fixture
def ingest_env(monkeypatch):
    events = []

    def chunks(doc):
        events.append("file")
        return [(3, "본문 1", "쪽 글 3"), (4, "본문 2", "쪽 글 4")], 0
    monkeypatch.setattr(main_mod, "load_documents", lambda: [DOC])
    monkeypatch.setattr(main_mod, "chunks_with_sources", chunks)
    monkeypatch.setattr(main_mod, "save", lambda conn, doc, chunks, embs: events.append("save"))
    monkeypatch.setattr(config, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(registry, "load_models", lambda: [{"id": "m1", "display_name": "모델1"}])
    return events


def _embed(events):
    def embed(texts):
        events.append("ai")
        return [[0.0]] * len(texts)
    return embed


def test_ingest_document_embeds_everything_before_opening(ingest_env):
    events = ingest_env
    out = main_mod.ingest_document("manual-x", connect=event_connect(events), embed=_embed(events))
    assert out == {"doc_id": "manual-x", "chunks": 2, "dropped": 0}
    assert events == ["file", "ai", "open", "save", "close"]
    assert_no_ai_while_open(events)


def test_ingest_document_closes_when_save_fails(ingest_env, monkeypatch):
    events = ingest_env

    def broken_save(conn, doc, chunks, embs):
        raise RuntimeError("저장 실패")
    monkeypatch.setattr(main_mod, "save", broken_save)
    with pytest.raises(RuntimeError):
        main_mod.ingest_document("manual-x", connect=event_connect(events), embed=_embed(events))
    assert events[-2:] == ["open", "close"]
    assert_no_ai_while_open(events)


def test_link_guide_writes_json_only_after_closing(tmp_path, monkeypatch):
    docs = tmp_path / "documents.json"
    shutil.copy(ROOT / "data" / "documents.json", docs)
    events = []
    real_write = add_model.write_documents

    def write(items, path):
        events.append("file")
        real_write(items, path)
    monkeypatch.setattr(add_model, "write_documents", write)
    add_model.link_guide("guide-lg-drum-errors", "aircon-lg-sq06fa1wds", connect=event_connect(events),
                         documents_path=docs)
    assert events == ["open", "close", "file"]
    assert_no_ai_while_open(events)


def test_ingest_manual_checks_db_then_closes_before_embedding(monkeypatch):
    """이미 있는지 보는 연결도 짧게 열고 닫은 뒤에 임베딩(검토 지적 4, Global 8)."""
    from dataclasses import replace
    events = []

    def fake_ingest(doc_id, connect=None, embed=None):
        events.append("ai")
        with connect():
            events.append("save")
        return {"doc_id": doc_id}
    monkeypatch.setattr(config, "get_settings", lambda: replace(SETTINGS, rewrite_model="gpt-6-luna"))
    monkeypatch.setattr(add_model, "ingest_document", fake_ingest)
    add_model.ingest_manual("manual-lg-fx25", connect=event_connect(events, FakeConn(lambda sql, params: None)))
    assert events == ["open", "close", "ai", "open", "save", "close"]
    assert_no_ai_while_open(events)


def test_remove_closes_when_query_fails():
    events = []

    def answer(sql, params):
        raise RuntimeError("DB 오류")
    with pytest.raises(RuntimeError):
        add_model.remove_model_data("manual-x", "m1", connect=event_connect(events, FakeConn(answer)), yes=True)
    assert events == ["open", "close"]
    assert_no_ai_while_open(events)
