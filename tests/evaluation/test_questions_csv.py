import csv
import re
from pathlib import Path

import pytest

from app.catalog.registry import load_models, supported_ids

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "evaluation" / "questions.csv"
GUIDES = ROOT / "data" / "guides"
COLUMNS = ["id", "model_id", "question", "expected_keywords", "expected_ref", "type", "expected_found"]
ALLOWED_TYPES = {"usage", "error_code", "colloquial", "trap_none", "trap_other_model"}
REF_PATTERN = re.compile(r"manual:\d+|guide:[\w-]+")


@pytest.fixture
def rows():
    if not QUESTIONS.exists():
        return []
    with QUESTIONS.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == COLUMNS
        return list(reader)


@pytest.fixture
def model_ids():
    return supported_ids(load_models())


def count(rows, type_):
    return sum(r["type"] == type_ for r in rows)


def test_has_30_rows_with_unique_ids(rows):
    assert len(rows) == 30 and len({r["id"] for r in rows}) == 30


def test_types_are_allowed(rows):
    assert rows and {r["type"] for r in rows} <= ALLOWED_TYPES


def test_trap_counts(rows):
    assert count(rows, "trap_none") >= 3 and count(rows, "trap_other_model") >= 2


def test_traps_expect_not_found(rows):
    assert rows
    for r in rows:
        if r["type"].startswith("trap"):
            assert r["expected_found"] == "false" and r["expected_ref"] == "", r["id"]


def test_answerable_rows_have_ref_and_keywords(rows):
    assert rows
    for r in rows:
        assert r["expected_found"] in {"true", "false"}, r["id"]
        if r["expected_found"] == "true":
            refs = r["expected_ref"].split("|")
            assert all(REF_PATTERN.fullmatch(x) for x in refs) and r["expected_keywords"].strip(), r["id"]


def test_model_ids_exist(rows, model_ids):
    assert rows and {r["model_id"] for r in rows} <= model_ids


def test_guide_refs_match_saved_guides(rows):
    # shortcut: documents.json이 생기기 전까지 저장한 가이드 파일 이름으로 대조, Task 6에서 documents.json 대조로 바꾼다
    if not GUIDES.exists():
        pytest.skip("data/guides/는 커밋하지 않는 폴더라 이 컴퓨터에만 있다")
    saved = {p.stem for p in GUIDES.glob("*.html")}
    refs = {x.removeprefix("guide:") for r in rows for x in r["expected_ref"].split("|") if x.startswith("guide:")}
    assert rows and refs <= saved, refs - saved
