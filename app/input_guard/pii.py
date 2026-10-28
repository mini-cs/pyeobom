import re


def _stars(*groups: str) -> str:
    return "-".join("*" * len(g) for g in groups)


# 순서가 중요하다: 이메일 → 휴대폰 → 지역번호 전화 → 동호수 → 도로명
RULES = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), lambda m: "[이메일]"),
    (re.compile(r"(?<!\d)(01[016789])-?(\d{3,4})-?(\d{4})(?!\d)"),
     lambda m: f"{m[1]}-{_stars(m[2], m[3])}"),
    (re.compile(r"(?<!\d)(0[2-6]\d?)-(\d{3,4})-(\d{4})(?!\d)"),
     lambda m: f"{m[1]}-{_stars(m[2], m[3])}"),
    (re.compile(r"\d+동\s?\d+호"), lambda m: "[동호수]"),
    # 번호 뒤에 단위가 붙으면("세탁기로 30분", "온도로 18도") 주소가 아니라 조사 '로'로 본다. 조사("123에")는 주소로 가린다
    (re.compile(r"[가-힣]+(?:로|길)\s?\d+(?:-\d+)?(?!\d|\s?(?:분|초|시간|도|℃|번(?!지)|회|개|장|벌|일|주|개월|년|단계|kg|g|ml|L|%))"),
     lambda m: "[주소]"),
]


def mask_pii(text: str) -> tuple[str, bool]:
    found = False
    for pattern, repl in RULES:
        text, n = pattern.subn(repl, text)
        found = found or n > 0
    return text, found
