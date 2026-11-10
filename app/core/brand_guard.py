"""다른 제조사 질문 규칙(결정 A): 고른 모델과 다른 브랜드 이름이 질문에 있으면 AI 없이 "찾지 못함"으로 답한다."""
import json
import re
from pathlib import Path

from app.retrieval.search import extract_code_tokens

# 브랜드 키 → 질문에서 찾을 이름. 영문은 대소문자 무시·앞뒤가 영문자가 아닐 때만 브랜드로 본다
ALIASES = {"samsung": ("삼성", "samsung"), "lg": ("엘지", "lg")}
# 한글 이름은 뒤에 아래 말이 올 때만 브랜드로 본다(허용 목록). 지명(삼성동·삼성역·삼성로 등)을 브랜드로 잡으면 정상 질문이 막히고,
# 브랜드를 놓치면 1차처럼 AI가 처리할 뿐이라 놓치는 쪽이 안전하다(결정기록 027)
KO_FOLLOWERS = (r"\s", r"[.,!?~…·)\]\"'」』]", "$", "이랑", "에서", "전자", "세탁기", "에어컨", "건조기", "제품",
                "은", "는", "이", "가", "의", "을", "를", "도", "랑", "꺼", "거")
_KO_NEXT = "(?=" + "|".join(KO_FOLLOWERS) + ")"


def _name_pattern(name: str) -> str:
    return rf"(?<![a-z]){name}(?![a-z])" if name.isascii() else name + _KO_NEXT


_PATTERNS = {key: re.compile("|".join(_name_pattern(n) for n in names), re.I) for key, names in ALIASES.items()}


def brand_key(brand: str) -> str | None:
    return next((key for key, names in ALIASES.items() if brand.lower() in names), None)


def mentions_other_brand(question: str, model_brand: str) -> str | None:
    own = brand_key(model_brand)
    return next((key for key, p in _PATTERNS.items() if key != own and p.search(question)), None)


def other_brand_message(model_brand: str) -> str:
    return f"지금 고른 모델은 {model_brand} 제품이에요. 다른 제조사 제품은 모델을 바꿔서 물어봐 주세요."


# 브랜드별 에러 코드 목록(우리 설명서·에러 가이드에서 뽑음, 결정기록 027)
# 두 글자 코드(IE·PE)는 다른 뜻으로도 쓰여("PE 소재라고 표시돼") 에러 상황 말이 함께 있을 때만 막는다
_ERROR_WORDS = re.compile(r"에러|오류|코드|뜨(?!거)|떴|떠")
_CODES = json.loads((Path(__file__).resolve().parents[2] / "data" / "error_codes.json").read_text(encoding="utf-8"))["codes"]


def other_brand_code(question: str, model_brand: str) -> str | None:
    """질문 속 코드가 다른 브랜드 목록에만 있고 고른 모델 브랜드 목록에는 없으면 그 코드(두 목록 모두에 있거나 어디에도 없으면 막지 않음)."""
    own = brand_key(model_brand)
    if own is None:
        return None
    others = {c for key, codes in _CODES.items() if key != own for c in codes}
    return next((c for c in extract_code_tokens(question) if c in others and c not in _CODES.get(own, {})
                 and not (len(c) == 2 and c.isalpha() and not _ERROR_WORDS.search(question))), None)


def other_brand_code_message(model_brand: str) -> str:
    return f"이 코드는 지금 고른 {model_brand} 모델 설명서에 없는 코드예요. 다른 제조사 제품이라면 모델을 바꿔 물어봐 주세요."


def guard_message(question: str, model_brand: str) -> str | None:
    """다른 제조사 이름 또는 다른 브랜드에만 있는 코드가 든 질문이면 AI 없이 보낼 안내 문장(결정 A)."""
    if mentions_other_brand(question, model_brand):
        return other_brand_message(model_brand)
    if other_brand_code(question, model_brand):
        return other_brand_code_message(model_brand)
    return None
