ERRORS = {
    "EMPTY_QUESTION": (400, "질문을 입력해 주세요"),
    "QUESTION_TOO_LONG": (400, "질문은 {max_len}자 이내로 입력해 주세요"),
    "INVALID_MODEL": (400, "지원하는 모델을 선택해 주세요"),
    "INVALID_REQUEST": (400, "요청 형식이 올바르지 않아요. 새로고침한 뒤 다시 시도해 주세요"),
    "SERVICE_UNAVAILABLE": (503, "일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요"),
    "AI_TIMEOUT": (504, "답변이 늦어지고 있어요. 잠시 후 다시 시도해 주세요"),
    "DB_UNAVAILABLE": (503, "일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요"),
}


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def make_error(code: str, **values) -> AppError:
    status, message = ERRORS[code]
    return AppError(code, message.format(**values), status)
