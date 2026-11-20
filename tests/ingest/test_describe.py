"""조각 설명 붙이기(v1.95) Task 1: 설명 쓰기와 적재 연결(기본 꺼짐)."""
import json
from types import SimpleNamespace

import pytest

import ingest.load as load
from app.core.config import Settings

MANUAL_DOC = {"id": "manual-x", "doc_type": "manual", "title": "샘플 설명서", "file": "unused.pdf", "model_ids": ["m1"]}
GUIDE_DOC = {"id": "guide-x", "doc_type": "guide", "title": "샘플 에러코드 안내",
             "file": "tests/ingest/fixtures/sample_guide.html", "content_selector": "article"}
SETTINGS = Settings(openai_api_key="", database_url="", openai_embed_model="text-embedding-3-small",
                    openai_chat_model="gpt-6-luna", embed_dim=1536)


def _item(name="A", doc_type="manual", page=3):
    from ingest.describe import ContextItem
    return ContextItem("doc-" + name, doc_type, page, f"조각 {name} {{x}}", f"글 {name} {{x}} 조각 {name} {{x}}", "문서 — 모델")


def _fake_client(text='{"description": "설명"}'):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text=text, usage=SimpleNamespace(input_tokens=10, output_tokens=5))
    return SimpleNamespace(responses=SimpleNamespace(create=create)), calls


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_chunks_with_sources_matches_build_chunks_and_contains_chunk(monkeypatch):
    from ingest.load import build_chunks, chunks_with_sources
    pages = [(3, "3\n" + "세탁조 청소 " * 200), (4, "배수 필터를 확인하세요.")]
    monkeypatch.setattr(load, "extract_pages", lambda path: pages)
    for doc in (MANUAL_DOC, GUIDE_DOC):
        items, dropped = chunks_with_sources(doc)
        chunks, dropped_build = build_chunks(doc)
        assert [(p, t) for p, t, _ in items] == chunks and dropped == dropped_build
        assert items and all(t in src for _, t, src in items)
    manual_items, _ = chunks_with_sources(MANUAL_DOC)
    assert len(manual_items) == 3 and {p for p, _, _ in manual_items} == {3, 4} and all(not src.startswith("3\n") for _, _, src in manual_items)


def test_embedding_input_puts_description_then_newline_then_content():
    from ingest.describe import embedding_input
    assert embedding_input("설명", "본문") == "설명\n본문"


def test_clean_description_rules():
    from ingest.describe import clean_description
    assert clean_description('{"description": " 가 \\n 나 "}') == "가 나"
    assert clean_description('{"description": "  "}') is None
    assert clean_description('{"description": "' + "가" * 150 + '"}') == "가" * 150
    assert clean_description('{"description": "' + "가" * 151 + '"}') is None
    assert clean_description("JSON 아님") is None


def test_prompt_template_has_each_field_once_and_no_eval_words():
    from ingest.describe import PROMPT_PATH
    text = PROMPT_PATH.read_text(encoding="utf-8")
    for field in ("{doc_label}", "{scope}", "{source}", "{chunk}"):
        assert text.count(field) == 1
    for word in ("평가", "정답", "질문"):
        assert word not in text


def test_build_prompt_scope_by_doc_type():
    from ingest.describe import build_prompt
    manual, guide = build_prompt(_item("A", "manual", 3)), build_prompt(_item("B", "guide", None))
    assert "설명서 한 쪽의 글 전체" in manual and "해결 가이드 글 전체" not in manual
    assert "해결 가이드 글 전체" in guide and "설명서 한 쪽의 글 전체" not in guide
    assert "조각 A {x}" in manual and "글 A {x}" in manual and "문서 — 모델" in manual
    for field in ("{doc_label}", "{scope}", "{source}", "{chunk}"):
        assert field not in manual


def test_describe_chunk_sends_model_effort_schema():
    from ingest.describe import CANDIDATE_CONTEXT, build_prompt, describe_chunk
    client, calls = _fake_client()
    desc, usage = describe_chunk(_item(), CANDIDATE_CONTEXT, client)
    assert desc == "설명" and usage == {"input_tokens": 10, "output_tokens": 5, "error": None}
    (kw,) = calls
    assert kw["model"] == "gpt-6-luna" and kw["reasoning"] == {"effort": "low"} and kw["max_output_tokens"] == 1000
    assert kw["text"]["format"]["name"] == "chunk_context" and kw["text"]["format"]["strict"] is True
    assert kw["input"] == [{"role": "user", "content": build_prompt(_item())}]


def test_describe_all_retries_once_then_reports_missing(tmp_path):
    from ingest.describe import CANDIDATE_CONTEXT, MissingDescriptions, describe_all
    a, b = _item("A"), _item("B")
    calls = []

    def call(item, spec, client):
        calls.append(item.doc_id)
        return ("설명 A" if item is a else None), {"input_tokens": 10, "output_tokens": 5, "error": None}
    path = tmp_path / "d.jsonl"
    with pytest.raises(MissingDescriptions) as e:
        describe_all([a, b], CANDIDATE_CONTEXT, path=path, call=call)
    assert e.value.count == 1 and issubclass(MissingDescriptions, SystemExit)
    assert calls.count("doc-A") == 1 and calls.count("doc-B") == 2
    rec = _records(path)[0]
    assert rec["doc_id"] == "doc-A" and rec["attempts"] == 1 and rec["description"] == "설명 A"


def test_describe_all_reuses_stored_without_calling(tmp_path):
    from ingest.describe import CANDIDATE_CONTEXT, describe_all
    path, items = tmp_path / "d.jsonl", [_item("A"), _item("B")]
    first = describe_all(items, CANDIDATE_CONTEXT, path=path,
                         call=lambda item, spec, client: (f"설명 {item.doc_id}", {"input_tokens": 1, "output_tokens": 1, "error": None}))
    again = describe_all(items, CANDIDATE_CONTEXT, path=path, call=lambda *a: pytest.fail("다시 부르면 안 됨"))
    assert first == again == ["설명 doc-A", "설명 doc-B"] and len(_records(path)) == 2


def test_describe_all_key_includes_model_effort_prompt(tmp_path, monkeypatch):
    import ingest.describe as d
    path, items = tmp_path / "d.jsonl", [_item("A")]
    d.describe_all(items, d.CANDIDATE_CONTEXT, path=path,
                   call=lambda item, spec, client: ("옛 설명", {"input_tokens": 1, "output_tokens": 1, "error": None}))
    calls = []

    def call(item, spec, client):
        calls.append(spec)
        return "새 설명", {"input_tokens": 1, "output_tokens": 1, "error": None}
    assert d.describe_all(items, d.ContextSpec("other-model", "low"), path=path, call=call) == ["새 설명"]
    assert d.describe_all(items, d.ContextSpec("gpt-6-luna", "medium"), path=path, call=call) == ["새 설명"]
    monkeypatch.setattr(d, "prompt_sha256", lambda: "다른 요청문")
    assert d.describe_all(items, d.CANDIDATE_CONTEXT, path=path, call=call) == ["새 설명"]
    assert len(calls) == 3


def test_describe_all_allow_new_false_refuses_without_calling(tmp_path):
    from ingest.describe import CANDIDATE_CONTEXT, MissingDescriptions, describe_all
    with pytest.raises(MissingDescriptions) as e:
        describe_all([_item("A"), _item("B")], CANDIDATE_CONTEXT, path=tmp_path / "d.jsonl",
                     call=lambda *a: pytest.fail("부르면 안 됨"), allow_new=False)
    assert e.value.count == 2 and not (tmp_path / "d.jsonl").exists()


def test_ingest_texts_unchanged_when_context_off():
    from ingest.describe import ingest_texts
    src = [(3, "본문 1", "글"), (4, "본문 2", "글 2")]
    texts = ingest_texts(MANUAL_DOC, src, SETTINGS, {"m1": {"display_name": "모델1"}},
                         describe=lambda *a, **k: pytest.fail("꺼져 있으면 부르지 않음"))
    assert texts == ["본문 1", "본문 2"]


def test_ingest_texts_prepend_when_on():
    from dataclasses import replace

    from ingest.describe import ContextItem, ContextSpec, ingest_texts
    seen = {}

    def describe(items, spec):
        seen.update(items=items, spec=spec)
        return ["설명"]
    texts = ingest_texts(MANUAL_DOC, [(3, "본문", "글")], replace(SETTINGS, chunk_context_model="gpt-6-luna"),
                         {"m1": {"display_name": "모델1"}}, describe=describe)
    assert texts == ["설명\n본문"]
    assert seen["spec"] == ContextSpec("gpt-6-luna", "low")
    assert seen["items"] == [ContextItem("manual-x", "manual", 3, "본문", "글", "샘플 설명서 — 모델1")]


def test_build_prompt_keeps_braces_and_backslashes_in_source():
    from ingest.describe import ContextItem, build_prompt
    source = r"쪽 글 {chunk} \1 \g<0> {doc_label} 끝"  # raw: 진짜 역슬래시(\1이 제어 문자로 읽히지 않게)
    chunk = r"조각 본문 \1"
    assert "\\" in source and "\x01" not in source + chunk
    item = ContextItem("doc-a", "manual", 3, chunk, source, "문서 — 모델")
    prompt = build_prompt(item)
    assert source in prompt  # 쪽 글의 "{chunk}"·역슬래시가 글자 그대로
    assert prompt.count(chunk) == 1 and "<조각>\n" + chunk + "\n</조각>" in prompt
    assert prompt.count("문서 — 모델") == 1


def test_ingest_main_embeds_inputs_but_saves_original_text(monkeypatch):
    from contextlib import contextmanager
    from dataclasses import replace
    from functools import partial

    import app.catalog.registry as registry
    import app.core.config as config
    import app.core.db as db
    import app.retrieval.embeddings as embeddings
    import ingest.__main__ as main_mod
    import ingest.describe as describe_mod

    src = [(3, "본문 1", "쪽 글 3"), (4, "본문 2", "쪽 글 4")]
    seen = {}

    @contextmanager
    def fake_conn():
        yield "conn"
    monkeypatch.setattr(main_mod, "load_documents", lambda: [MANUAL_DOC])
    monkeypatch.setattr(main_mod, "load_env", lambda: None)  # 로컬 .env를 읽지 않는다
    monkeypatch.setattr(main_mod, "chunks_with_sources", lambda doc: (src, 0))
    monkeypatch.setattr(main_mod, "save", lambda conn, doc, chunks, embs: seen.update(saved=chunks, embs=embs))
    monkeypatch.setattr(db, "get_conn", fake_conn)
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: seen.update(embedded=texts) or [[0.0]] * len(texts))
    monkeypatch.setattr(registry, "load_models", lambda: [{"id": "m1", "display_name": "모델1"}])
    monkeypatch.setattr(describe_mod, "ingest_texts",
                        partial(describe_mod.ingest_texts, describe=lambda items, spec: [f"설명 {i.page}" for i in items]))
    monkeypatch.setattr("sys.argv", ["ingest", "--doc-id", "manual-x"])

    monkeypatch.setattr(config, "get_settings", lambda: replace(SETTINGS, chunk_context_model="gpt-6-luna"))
    main_mod.main()
    assert seen["embedded"] == ["설명 3\n본문 1", "설명 4\n본문 2"]
    assert seen["saved"] == [(3, "본문 1"), (4, "본문 2")] and len(seen["embs"]) == 2

    seen.clear()
    monkeypatch.setattr(config, "get_settings", lambda: SETTINGS)
    main_mod.main()
    assert seen["embedded"] == ["본문 1", "본문 2"] and seen["saved"] == [(3, "본문 1"), (4, "본문 2")]


# 검토 지적 처리(사용자 결정 2026-11-20): I1 적재 설정 경고, M1 실패한 조각 기록
def test_ingest_main_warns_but_does_not_stop(monkeypatch, capsys):
    from contextlib import contextmanager
    from dataclasses import replace

    import app.catalog.registry as registry
    import app.core.config as config
    import app.core.db as db
    import app.retrieval.embeddings as embeddings
    import ingest.__main__ as main_mod

    seen = {}

    @contextmanager
    def fake_conn():
        yield "conn"
    monkeypatch.setattr(main_mod, "load_documents", lambda: [MANUAL_DOC])
    monkeypatch.setattr(main_mod, "load_env", lambda: None)
    monkeypatch.setattr(main_mod, "chunks_with_sources", lambda doc: ([(3, "본문", "쪽 글")], 0))
    monkeypatch.setattr(main_mod, "save", lambda conn, doc, chunks, embs: seen.update(saved=chunks))
    monkeypatch.setattr(db, "get_conn", fake_conn)
    monkeypatch.setattr(embeddings, "embed_texts", lambda texts: [[0.0]] * len(texts))
    monkeypatch.setattr(registry, "load_models", lambda: [{"id": "m1", "display_name": "모델1"}])
    monkeypatch.setattr("sys.argv", ["ingest", "--doc-id", "manual-x"])
    monkeypatch.setattr(config, "get_settings", lambda: replace(SETTINGS, top_k=7))  # 운영(5)과 다름
    main_mod.main()
    out = capsys.readouterr().out
    assert "운영 기본값과 다른 설정" in out and "top_k=7" in out
    assert seen["saved"] == [(3, "본문")]  # 경고만 하고 멈추지 않는다


def test_describe_all_records_failed_chunk_as_null(tmp_path):
    from ingest.describe import CANDIDATE_CONTEXT, MissingDescriptions, describe_all
    a, b = _item("A"), _item("B")
    call = lambda item, spec, client: ("설명 A" if item is a else None, {"input_tokens": 10, "output_tokens": 5, "error": None})
    path = tmp_path / "d.jsonl"
    with pytest.raises(MissingDescriptions):
        describe_all([a, b], CANDIDATE_CONTEXT, path=path, call=call)
    ok, failed = _records(path)
    assert ok["doc_id"] == "doc-A" and ok["description"] == "설명 A"
    assert failed["doc_id"] == "doc-B" and failed["description"] is None and failed["attempts"] == 2
    assert (failed["input_tokens"], failed["output_tokens"]) == (20, 10)  # 두 번 시도한 토큰 합
    assert {k: failed[k] for k in ("page", "model", "effort")} == {"page": 3, "model": "gpt-6-luna", "effort": "low"}
    assert failed["content_sha256"] and failed["prompt_sha256"]


def test_describe_all_reruns_only_null_and_prefers_success(tmp_path):
    from ingest.describe import CANDIDATE_CONTEXT, MissingDescriptions, describe_all
    a, b = _item("A"), _item("B")
    path = tmp_path / "d.jsonl"
    with pytest.raises(MissingDescriptions):
        describe_all([a, b], CANDIDATE_CONTEXT, path=path,
                     call=lambda item, spec, client: ("설명 A" if item is a else None, {"input_tokens": 1, "output_tokens": 1, "error": None}))
    calls = []

    def call(item, spec, client):
        calls.append(item.doc_id)
        return "설명 B", {"input_tokens": 1, "output_tokens": 1, "error": None}
    assert describe_all([a, b], CANDIDATE_CONTEXT, path=path, call=call) == ["설명 A", "설명 B"]
    assert calls == ["doc-B"]  # null 줄은 "설명 있음"이 아니라 그 조각만 다시 부른다
    null_b = next(r for r in _records(path) if r["description"] is None)
    with path.open("a", encoding="utf-8") as f:  # 성공 줄 뒤에 null 줄이 또 있어도 성공 줄을 쓴다
        f.write(json.dumps(null_b, ensure_ascii=False) + "\n")
    assert describe_all([a, b], CANDIDATE_CONTEXT, path=path, call=lambda *x: pytest.fail("부르면 안 됨")) == ["설명 A", "설명 B"]
