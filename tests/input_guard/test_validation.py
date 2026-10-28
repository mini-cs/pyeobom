import pytest

from app.core.errors import AppError
from app.input_guard.validation import validate_model_id, validate_question


@pytest.mark.parametrize("q", [None, "", "   ", "\n\t　"])
def test_empty_question_rejected(q):
    with pytest.raises(AppError) as e:
        validate_question(q, 500)
    assert e.value.code == "EMPTY_QUESTION" and e.value.status == 400


def test_question_over_limit_rejected():
    with pytest.raises(AppError) as e:
        validate_question("가" * 10_000, 500)
    assert e.value.code == "QUESTION_TOO_LONG"


def test_question_at_limit_accepted():
    assert validate_question("가" * 500, 500) == "가" * 500


def test_question_is_trimmed():
    assert validate_question("  통세척 방법  ", 500) == "통세척 방법"


@pytest.mark.parametrize("m", [None, "", "unknown-model"])
def test_invalid_model_rejected(m):
    with pytest.raises(AppError) as e:
        validate_model_id(m, {"washer-a"})
    assert e.value.code == "INVALID_MODEL"


def test_supported_model_accepted():
    assert validate_model_id("washer-a", {"washer-a"}) == "washer-a"


def test_too_long_message_uses_max_len():
    with pytest.raises(AppError) as e:
        validate_question("가" * 301, 300)
    assert e.value.message == "질문은 300자 이내로 입력해 주세요"
