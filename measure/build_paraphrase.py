"""P 세트(표현이 다른 질문) 정리(검색 개선 계획 Task 1).

사용법: python -m measure.build_paraphrase   (measure/out/p-set-responses.csv → evaluation/paraphrase_dev.csv·paraphrase_test.csv·paraphrase_split.json)
- 구글 폼 응답(이름·연락처 칸 없음). 동의한 응답만, 빈칸 제외, 정해진 욕설만 순화하고 나머지 말투는 그대로
- 정답 근거는 채팅 Claude가 설명서 원본으로 대조하고 사용자가 확정(2026-11-10). 쪽의 조각을 모두 기대 근거로, 가이드 조각은 chunk:<id>
- 카드 단위·모델별로 반씩 개발용/확인용으로 나누고(시드 고정) 확인용 파일의 해시를 기록한다. 확인용은 3단계 전까지 검색·채점하지 않는다
"""
import csv
import hashlib
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "measure" / "out" / "p-set-responses.csv"
EVAL = ROOT / "evaluation"
SEED = 20261110
SOFTEN = {"존나": "엄청", "ㅈㄴ": "엄청", "좆된거임": "큰일 난 거임"}  # 사용자 지정, 나머지 말투는 그대로

LG_W, SS_W, LG_A = "washer-lg-fx25", "washer-samsung-wd90h25", "aircon-lg-sq06fa1wds"
M = lambda *pages: [f"manual:{p}" for p in pages]
# 카드 → (모델, 기대 근거, 메모). None은 함정(설명서에 답 없음)
CARDS = {
    1: (LG_W, M(43, 44, 45, 56) + ["chunk:300", "chunk:312"], "가이드 결빙 조각 300·312"), 2: (LG_W, M(41) + ["chunk:299", "chunk:300"], "가이드 IE(급수) 조각 299·300"),
    3: (LG_W, M(16, 17), ""), 4: (LG_W, M(35), "정답은 '건조기 연결 시' 조건을 밝혀야 함"), 5: (LG_W, M(14, 23, 29), ""),
    6: (LG_W, M(25, 26, 30), ""), 7: (LG_W, M(34), ""), 8: (LG_W, M(42, 58), ""),
    9: (SS_W, M(*range(35, 46)), "35~45쪽 코스 표(구김 방지 옵션)"), 10: (SS_W, M(18, 35, 40, 41), ""), 11: (SS_W, M(33), ""),
    12: (SS_W, M(37), ""), 13: (SS_W, M(39), ""), 14: (SS_W, M(36), ""), 15: (SS_W, M(32, 51, 70), ""),
    16: (LG_A, M(15, 16, 23, 50), ""), 17: (LG_A, M(25, 28), ""), 18: (LG_A, M(36, 37, 38, 39), ""), 19: (LG_A, M(38, 39), ""),
    20: (LG_A, M(21, 26, 35, 52), ""), 21: (LG_A, None, ""), 22: (LG_A, M(15, 16, 48, 50), ""),
}
EXTRA_TRAPS = {(16, 2), (17, 2)}  # 2번 응답자의 "정속형인가요?"·"무풍인가요?"(사용자 지정)
# (카드, 응답자) → 그 문장에만 더하는 기대 근거. 카드 19 응답자 2 "휴대폰과 연동이 되나요?"는 ThinQ 연결 쪽도(11쪽 앱 설치·제품 등록, 19쪽 LG ThinQ 연결하기)
EXTRA_REFS = {(19, 2): (M(11, 19), "ThinQ 연결 쪽(11·19)도 정답")}
TRAP_NOTE = "함정(B 기준: 묻는 정보를 지어내지 않고 없다고 밝히면 정답)"
COLUMNS = ["id", "card", "respondent", "model_id", "question", "expected_ref", "type", "expected_found", "note"]
HEADER = ["# P 세트(표현이 다른 질문): 구글 폼 2명 41문장(둘 다 동의, 이름·연락처 없음). 사용자 본인 문장은 넣지 않음(M3 사전을 먼저 봄)",
          "# 순화: '존나'·'ㅈㄴ'→'엄청', '좆된거임'→'큰일 난 거임'(4곳), 나머지 말투는 그대로",
          "# 정답 근거: 채팅 Claude가 설명서 원본으로 대조, 사용자 확정(2026-11-10). 쪽의 조각 모두, 가이드 조각은 chunk:<id>",
          "# " + TRAP_NOTE]
# 확정 기록은 개발용 머리에만 둔다(확인용 파일을 고치면 봉인 해시가 바뀐다). 확정 기록은 paraphrase_split.json에도
CONFIRMED = ("# 확정: 2026-11-10, 채팅 Claude가 원문 대조, 사용자가 확정. 확정 때 추가: 카드 1에 가이드 결빙 조각 chunk:300·312, "
             "카드 19 응답자 2에 ThinQ 연결 쪽 manual:11·19(답이 있는 쪽은 모두)")


def clean_text(text: str) -> str:
    for bad, good in SOFTEN.items():
        text = text.replace(bad, good)
    return text.strip()


def split_cards(cards: dict[int, str], seed: int) -> tuple[set[int], set[int]]:
    """카드 → 모델. 모델마다 카드를 섞어 앞의 반(홀수면 올림)을 개발용, 나머지를 확인용으로"""
    rng, dev = random.Random(seed), set()
    for model in sorted(set(cards.values())):
        group = sorted(c for c, m in cards.items() if m == model)
        rng.shuffle(group)
        dev |= set(group[:math.ceil(len(group) / 2)])
    return dev, set(cards) - dev


def build_rows(src: Path = SRC) -> tuple[list[dict], int]:
    with open(src, encoding="utf-8-sig", newline="") as f:
        table = list(csv.reader(f))
    header, answers = table[0], table[1:]
    rows, softened = [], 0
    for resp_no, ans in enumerate(answers, 1):
        if ans[1].strip() != "동의해요":
            continue
        for col in range(3, len(header)):
            card = int(header[col].split(".", 1)[0])
            if not ans[col].strip():
                continue
            text = clean_text(ans[col])
            softened += text != ans[col].strip()
            model, refs, note = CARDS[card]
            trap = refs is None or (card, resp_no) in EXTRA_TRAPS
            if (card, resp_no) in EXTRA_REFS:
                more, more_note = EXTRA_REFS[(card, resp_no)]
                refs, note = refs + more, "; ".join(x for x in (note, more_note) if x)
            rows.append({"id": f"p{card:02d}-{resp_no}", "card": card, "respondent": resp_no, "model_id": model, "question": text,
                         "expected_ref": "" if trap else "|".join(refs), "type": "trap" if trap else "paraphrase",
                         "expected_found": "false" if trap else "true", "note": TRAP_NOTE if trap else note})
    return rows, softened


def _write(path: Path, rows: list[dict], extra: tuple[str, ...] = ()) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        f.write("\n".join(HEADER + list(extra)) + "\n")
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    rows, softened = build_rows()
    dev, test = split_cards({c: m for c, (m, _, _) in CARDS.items()}, SEED)
    _write(EVAL / "paraphrase_dev.csv", [r for r in rows if r["card"] in dev], (CONFIRMED,))
    _write(EVAL / "paraphrase_test.csv", [r for r in rows if r["card"] in test])
    split = {"seed": SEED, "dev_cards": sorted(dev), "test_cards": sorted(test),
             "test_sha256": hashlib.sha256((EVAL / "paraphrase_test.csv").read_bytes()).hexdigest(),
             "rows": {"dev": sum(r["card"] in dev for r in rows), "test": sum(r["card"] in test for r in rows)},
             "softened_sentences": softened, "confirmed": CONFIRMED[2:], "sealed": "확인용은 3단계 전까지 검색·채점하지 않는다(계획 1-1)"}
    (EVAL / "paraphrase_split.json").write_text(json.dumps(split, ensure_ascii=False, indent=1), encoding="utf-8")
    print(split)


if __name__ == "__main__":
    main()
