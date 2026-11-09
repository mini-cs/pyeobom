import csv
import json
import re
from pathlib import Path

import pytest

from app.ask.service import Deps, answer_question
from app.catalog.registry import load_models
from app.core.brand_guard import mentions_other_brand
from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
BRANDS = {m["id"]: m["brand"] for m in load_models()}


@pytest.mark.parametrize("question, model_brand, expected", [
    ("LG 세탁기 IE 에러는 뭐예요?", "삼성", "lg"),
    ("삼성 세탁기처럼 UE가 떠요", "LG", "samsung"),
    ("삼성 세탁기에 IE 에러가 떠요", "삼성", None),  # q18: 같은 브랜드는 규칙이 관여하지 않음
    ("lg세탁기 코드가 떠요", "삼성", "lg"),
    ("엘지 제품도 이렇게 해요?", "삼성", "lg"),
    ("Samsung 앱으로 돼요?", "LG", "samsung"),
    ("LGA 소켓 말고 세탁조 청소는?", "삼성", None),  # 영문 단어 일부는 브랜드가 아님
])
def test_mentions_other_brand(question, model_brand, expected):
    assert mentions_other_brand(question, model_brand) == expected


@pytest.mark.parametrize("question", ["강남구 삼성동에 사는데 기사님 와 줄 수 있어요?", "삼성역 근처인데 필터는 어디서 사요?",
                                      "삼성로에 살아요", "삼성병원 앞인데 에어컨이 안 켜져요"])
def test_korean_place_names_are_not_brands(question):
    # 허용 목록: 지명(삼성동·삼성역·삼성로·삼성병원)을 브랜드로 잡으면 정상 질문이 막힌다
    assert mentions_other_brand(question, "LG") is None


@pytest.mark.parametrize("question, model_brand, expected", [
    ("삼성 세탁기도 이래요?", "LG", "samsung"), ("삼성꺼는 어때요?", "LG", "samsung"), ("삼성은 다르죠?", "LG", "samsung"),
    ("삼성전자 서비스 불러야 해요?", "LG", "samsung"), ("엘지 에어컨도 같아요?", "삼성", "lg"), ("이거 삼성?", "LG", "samsung"),
    ("엘지랑 비교하면요?", "삼성", "lg"), ("삼성", "LG", "samsung"),
])
def test_korean_brand_followed_by_allowed_word(question, model_brand, expected):
    assert mentions_other_brand(question, model_brand) == expected


def test_evaluation_questions_are_not_blocked():
    with open(ROOT / "evaluation" / "questions.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 30
    blocked = [r["id"] for r in rows if mentions_other_brand(r["question"], BRANDS[r["model_id"]])]
    assert blocked == []


def test_screen_example_questions_are_not_blocked():
    # 화면 예시 질문은 public/app.js의 EXAMPLES에 있다
    js = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    block = re.search(r"const EXAMPLES = (\{.*?\});", js, re.S).group(1)
    examples = json.loads(re.sub(r",\s*}", "}", block))
    assert set(examples) == set(BRANDS)
    blocked = [q for mid, qs in examples.items() for q in qs if mentions_other_brand(q, BRANDS[mid])]
    assert blocked == []


def _fail(*args):
    raise AssertionError("다른 브랜드 질문에서 임베딩·검색·AI가 불리면 안 된다")


def test_other_brand_question_skips_search_and_ai():
    deps = Deps(embed_query=_fail, search=_fail, complete=_fail, supported_ids={"washer-samsung-wd90h25"},
                official_url=lambda m: "https://example.com/samsung", diagnostic=_fail, brand=lambda m: "삼성")
    settings = Settings(openai_api_key="", database_url="", openai_embed_model="m", openai_chat_model="m", embed_dim=3)
    body = answer_question("washer-samsung-wd90h25", "LG 세탁기 IE 에러는 뭐예요?", deps, settings, debug=True)
    assert body["found"] is False
    assert body["answer"] == "지금 고른 모델은 삼성 제품이에요. 다른 제조사 제품은 모델을 바꿔서 물어봐 주세요."
    assert body["citations"] == []
    assert body["official_url"] == "https://example.com/samsung"
    assert body["cited_refs"] == [] and body["retrieved_refs"] == []
