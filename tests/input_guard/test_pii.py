import csv
from pathlib import Path

import pytest

from app.input_guard.pii import mask_pii

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("raw,expected", [
    ("기사님 010-1234-5678로 연락 주세요", "기사님 010-****-****로 연락 주세요"),
    ("01012345678 입니다", "010-****-**** 입니다"),
    ("02-123-4567 사무실", "02-***-**** 사무실"),
    ("메일은 abc.def@gmail.com", "메일은 [이메일]"),
    ("101동 1203호 세탁기", "[동호수] 세탁기"),
    ("가나다로 123 원룸이에요", "[주소] 원룸이에요"),
])
def test_masks_pii(raw, expected):
    masked, found = mask_pii(raw)
    assert masked == expected and found is True


def test_keeps_normal_question():
    assert mask_pii("에러 코드 4E가 떴어요") == ("에러 코드 4E가 떴어요", False)


@pytest.mark.parametrize("q", ["세탁기로 30분", "온도로 18도", "코스로 2번", "헹굼 2회로 3회 더"])
def test_particle_ro_with_unit_is_not_address(q):
    assert mask_pii(q) == (q, False)


@pytest.mark.parametrize("raw,expected", [
    ("가나다로 123에", "[주소]에"),
    ("가나다로 123번지", "[주소]번지"),
    ("라마바로 12-3이에요", "[주소]이에요"),
])
def test_road_name_address_is_masked(raw, expected):
    assert mask_pii(raw) == (expected, True)


def test_eval_questions_are_unchanged():
    with (ROOT / "evaluation" / "questions.csv").open(encoding="utf-8-sig", newline="") as f:
        questions = [r["question"] for r in csv.DictReader(f)]
    assert len(questions) == 30
    changed = [q for q in questions if mask_pii(q) != (q, False)]
    assert changed == []


@pytest.mark.parametrize("raw,expected", [
    ("test@example.com으로 보내 주세요", "[이메일]으로 보내 주세요"),
    ("메일은 a.b-c@mail.co.kr로 주세요", "메일은 [이메일]로 주세요"),
    ("test@예시.한국으로", "[이메일]으로"),
    ("test@예시.한국", "[이메일]"),
    ("test@example.com", "[이메일]"),
])
def test_email_mask_keeps_korean_particle(raw, expected):
    masked, found = mask_pii(raw)
    assert masked == expected and found is True


def test_uppercase_email_is_masked():
    masked, found = mask_pii("TEST@EXAMPLE.COM")
    assert "@" not in masked and found is True
