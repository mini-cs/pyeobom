import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from measure.build_paraphrase import clean_text, split_cards

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evaluation"


def test_clean_text_softens_only_listed_words():
    assert clean_text("옷 존나 더러워서") == "옷 엄청 더러워서"
    assert clean_text("개털 ㅈㄴ 묻은 담요") == "개털 엄청 묻은 담요"
    assert clean_text("물 흐르는 소리 나는데 좆된거임?") == "물 흐르는 소리 나는데 큰일 난 거임?"
    assert clean_text("빨래 끝냈는데 똥내나는데 어케함?") == "빨래 끝냈는데 똥내나는데 어케함?"  # 나머지 말투는 그대로


def test_split_cards_is_per_model_half_and_repeatable():
    cards = {c: ("a" if c <= 8 else "b" if c <= 15 else "c") for c in range(1, 23)}
    dev, test = split_cards(cards, seed=1)
    assert dev.isdisjoint(test) and dev | test == set(cards)
    assert Counter(cards[c] for c in dev) == {"a": 4, "b": 4, "c": 4}
    assert (dev, test) == split_cards(cards, seed=1)


def _read(name):
    with open(EVAL / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


@pytest.mark.skipif(not (EVAL / "paraphrase_dev.csv").exists(), reason="P 세트 파일을 만들기 전")
def test_paraphrase_files_are_sealed_and_consistent():
    split = json.loads((EVAL / "paraphrase_split.json").read_text(encoding="utf-8"))
    # 봉인 확인. git 체크아웃이 줄 끝을 CRLF로 바꿀 수 있어 LF로 맞춘 내용의 해시를 비교한다
    assert hashlib.sha256((EVAL / "paraphrase_test.csv").read_bytes().replace(b"\r\n", b"\n")).hexdigest() == split["test_sha256"]
    dev, test = _read("paraphrase_dev.csv"), _read("paraphrase_test.csv")
    assert {r["card"] for r in dev}.isdisjoint({r["card"] for r in test})  # 같은 카드가 양쪽에 없음
    rows = dev + test
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        assert r["question"].strip()
        assert (r["type"] == "trap") == (r["expected_found"] == "false")
        assert r["expected_ref"] or r["type"] == "trap"  # 기대 근거 또는 함정 표시


SEALED_TEST_SHA256 = "ca5b83dd6fee2ef40c7f1db625effbfe4135507216fe3d889ca81a631889085e"  # 2026-11-10 처음 봉인한 확인용 해시


@pytest.mark.skipif(not (EVAL / "paraphrase_dev.csv").exists(), reason="P 세트 파일을 만들기 전")
def test_confirmed_additions_keep_test_file_sealed():
    split = json.loads((EVAL / "paraphrase_split.json").read_text(encoding="utf-8"))
    assert split["test_sha256"] == SEALED_TEST_SHA256  # 개발용만 고쳤으니 확인용은 그대로
    dev = {r["id"]: r["expected_ref"].split("|") for r in _read("paraphrase_dev.csv")}
    assert {"chunk:300", "chunk:312"} <= set(dev["p01-1"]) and {"chunk:300", "chunk:312"} <= set(dev["p01-2"])
    assert {"manual:38", "manual:39", "manual:11", "manual:19"} <= set(dev["p19-2"])
    assert "manual:11" not in dev["p19-1"]  # 응답자 2 문장에만
    assert "채팅 Claude가 원문 대조, 사용자가 확정" in (EVAL / "paraphrase_dev.csv").read_text(encoding="utf-8-sig").split("id,card")[0]
