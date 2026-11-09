"""다른 제조사 질문 규칙(결정 A): 고른 모델과 다른 브랜드 이름이 질문에 있으면 AI 없이 "찾지 못함"으로 답한다."""
import re

# 브랜드 키 → 질문에서 찾을 이름. 영문은 대소문자 무시·앞뒤가 영문자가 아닐 때만, 한글은 그대로 찾는다
ALIASES = {"samsung": ("삼성", "samsung"), "lg": ("엘지", "lg")}
_PATTERNS = {key: re.compile("|".join(n if not n.isascii() else rf"(?<![a-z]){n}(?![a-z])" for n in names), re.I)
             for key, names in ALIASES.items()}


def brand_key(brand: str) -> str | None:
    return next((key for key, names in ALIASES.items() if brand.lower() in names), None)


def mentions_other_brand(question: str, model_brand: str) -> str | None:
    own = brand_key(model_brand)
    return next((key for key, p in _PATTERNS.items() if key != own and p.search(question)), None)


def other_brand_message(model_brand: str) -> str:
    return f"지금 고른 모델은 {model_brand} 제품이에요. 다른 제조사 제품은 모델을 바꿔서 물어봐 주세요."
