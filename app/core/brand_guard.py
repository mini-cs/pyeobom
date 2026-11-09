"""다른 제조사 질문 규칙(결정 A): 고른 모델과 다른 브랜드 이름이 질문에 있으면 AI 없이 "찾지 못함"으로 답한다."""
import re

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
