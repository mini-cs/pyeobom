import pytest

from app.input_guard.pii import mask_pii


@pytest.mark.parametrize("raw,expected", [
    ("기사님 010-1234-5678로 연락 주세요", "기사님 010-****-****로 연락 주세요"),
    ("01012345678 입니다", "010-****-**** 입니다"),
    ("02-123-4567 사무실", "02-***-**** 사무실"),
    ("메일은 abc.def@gmail.com", "메일은 [이메일]"),
    ("101동 1203호 세탁기", "[동호수] 세탁기"),
    ("망원로 123 원룸이에요", "[주소] 원룸이에요"),
])
def test_masks_pii(raw, expected):
    masked, found = mask_pii(raw)
    assert masked == expected and found is True


def test_keeps_normal_question():
    assert mask_pii("에러 코드 4E가 떴어요") == ("에러 코드 4E가 떴어요", False)
