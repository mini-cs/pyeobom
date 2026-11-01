import csv
from pathlib import Path

import pytest

from app.retrieval.search import contains_code, extract_code_tokens


@pytest.mark.parametrize("q,tokens", [
    ("에러 코드 4E가 떴어요", ["4E"]),
    ("4 e 떠요", ["4E"]),
    ("물이 안 빠져요", []),
    ("세탁 중에 OE가 뜨고 물이 안 빠지는 것 같아요", ["OE"]),   # LG 드럼 가이드 형식
    ("건조까지 돌렸는데 5C가 뜨면서 물이 안 빠져요", ["5C"]),   # 삼성 형식
    ("에어컨에 CH10이 떴어요", ["CH10"]),
    ("AI 건조는 어떻게 켜요?", []),                              # 에러 맥락이 없는 영문 약어는 코드가 아님
    ("LG 세탁기에 UE 에러가 떴어요", ["UE"]),                    # 흔한 약어(LG)는 빼고
    ("1.5 V 건전지 넣었는데 220 V 맞나요?", []),                 # 단위는 코드가 아님
])
def test_extract_code_tokens(q, tokens):
    assert extract_code_tokens(q) == tokens


def test_eval_questions_codes_are_exact():
    # 평가 질문 30개에서 뽑히는 코드를 고정한다(엉뚱한 약어가 코드로 잡히면 진단 조각이 불필요하게 붙음)
    with (Path(__file__).resolve().parents[2] / "evaluation" / "questions.csv").open(encoding="utf-8") as f:
        got = {r["id"]: extract_code_tokens(r["question"]) for r in csv.DictReader(f)}
    expected = {"q05": ["OE"], "q06": ["PE"], "q07": ["TE"], "q14": ["5C"], "q15": ["4E"], "q16": ["HC"],
                "q18": ["IE"], "q23": ["CH05"], "q24": ["CH10"]}
    assert {k: v for k, v in got.items() if v} == expected


@pytest.mark.parametrize("token,text,found", [
    ("IE", "IEEE 802.11 규격, IEC 60456", False),   # 단어 경계: IEEE·IEC 안의 IE는 코드가 아님
    ("IE", "IE [급수 문제]", True),
    ("CH05", "CH05/53, E0 등의 코드가 표시되면", True),
    ("CH10", "CH05/53, CH32/33", False),
    ("4E", "4C, 4E 점검 코드", True),
    ("TE", "tE 에러는 온도 감지 센서 이상", True),     # 대소문자 무시
])
def test_contains_code_uses_word_boundary(token, text, found):
    assert contains_code(token, text) is found
