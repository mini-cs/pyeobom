import re


def _stars(*groups: str) -> str:
    return "-".join("*" * len(g) for g in groups)


_PARTICLES = ("으로", "에서", "에게", "까지", "부터", "이랑", "한테", "로", "에", "은", "는", "이", "가", "을", "를", "도", "와", "과", "의", "만", "랑", "께")


def _email(m: re.Match) -> str:
    # \w가 한글도 잡아 뒤따르는 조사까지 삼키므로, 마지막 덩어리에서 끝부분만 돌려준다(결정기록 015: 가리는 범위만 줄임)
    label = m[0].rpartition(".")[2]
    if g := re.fullmatch(r"([A-Za-z0-9_-]+)([가-힣].*)", label):  # 영문 도메인 뒤에 붙은 한글
        return "[이메일]" + g[2]
    if re.fullmatch(r"[가-힣]+", label):  # 한글 도메인 끝의 조사(긴 것부터)
        for p in _PARTICLES:
            if label.endswith(p) and len(label) > len(p):
                return "[이메일]" + p
    return "[이메일]"


# 순서가 중요하다: 이메일 → 휴대폰 → 지역번호 전화 → 동호수 → 도로명
RULES = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), _email),
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


def mask_history(history: list[dict]) -> list[dict]:
    # 앞 대화도 질문·답 모두 가린 뒤에만 AI(질문 바꾸기)에 보낸다
    return [{"question": mask_pii(t["question"])[0], "answer": mask_pii(t["answer"])[0]} for t in history]
