import csv
from pathlib import Path

from app.catalog.registry import load_models, supported_ids
from ingest.load import build_chunks, load_documents

ROOT = Path(__file__).resolve().parents[2]
FIELDS = {"id", "doc_type", "title", "source_url", "scope_note", "model_ids", "file", "fetched_at"}


def test_documents_have_required_fields():
    docs = load_documents()
    assert len(docs) == 11 and len({d["id"] for d in docs}) == 11   # 설명서 3 + 가이드 8 (결정기록 014)
    for d in docs:
        assert FIELDS <= d.keys(), d["id"]
        assert d["doc_type"] in {"manual", "guide"} and d["source_url"].startswith("https://")
        assert d["model_ids"] and set(d["model_ids"]) <= supported_ids(load_models())
        if d["doc_type"] == "guide":
            assert d["content_selector"] and d["file"].startswith("data/guides/")


def test_every_model_has_one_manual():
    manuals = [m for d in load_documents() if d["doc_type"] == "manual" for m in d["model_ids"]]
    assert sorted(manuals) == sorted(supported_ids(load_models()))


def test_flexwash_paragraphs_excluded_only_on_oc_and_lc():
    excluded = {d["id"] for d in load_documents() if d.get("exclude_keywords") == ["플렉스워시"]}
    assert excluded == {"guide-samsung-drum-oc", "guide-samsung-drum-lc"}


def test_eval_guide_refs_are_documents():
    with (ROOT / "evaluation" / "questions.csv").open(encoding="utf-8-sig", newline="") as f:
        refs = {x[6:] for r in csv.DictReader(f) for x in r["expected_ref"].split("|") if x.startswith("guide:")}
    assert refs <= {d["id"] for d in load_documents()}


def test_guide_chunks_have_no_page_and_start_with_title():
    doc = {"id": "guide-sample", "doc_type": "guide", "title": "샘플 에러코드 안내",
           "file": "tests/ingest/fixtures/sample_guide.html", "content_selector": "article"}
    chunks, dropped = build_chunks(doc)
    assert chunks and all(page is None for page, _ in chunks) and dropped == 0
    assert chunks[0][1].startswith("샘플 에러코드 안내") and "숨은 패널 설명" in chunks[0][1]
