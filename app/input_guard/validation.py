from app.core.errors import make_error


def validate_question(question: str | None, max_len: int) -> str:
    text = (question or "").strip()  # str.strip()은 전각 공백 등 유니코드 공백도 지운다
    if not text:
        raise make_error("EMPTY_QUESTION")
    if len(text) > max_len:
        raise make_error("QUESTION_TOO_LONG", max_len=max_len)
    return text


def validate_model_id(model_id: str | None, supported: set[str]) -> str:
    if model_id not in supported:
        raise make_error("INVALID_MODEL")
    return model_id
