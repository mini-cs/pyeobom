"""v1.7 새 응답 카드별 세기(설계 10절). 문장 내용은 출력하지 않고 개수만 낸다.

사용법: python -m measure.v17_count   (measure/out/p-set-responses.csv, evaluation/paraphrase_split.json의 카드 번호만 읽음)
"""
import csv
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "measure" / "out" / "p-set-responses.csv"
SPLIT = ROOT / "evaluation" / "paraphrase_split.json"
# 지난 내보내기 파일(p-set-responses.csv)의 저장 시각. P 세트를 2026-11-10에 이 파일로 만들었다
CUTOFF = datetime(2026, 11, 10, 13, 4, 4)
CONSENT = "동의해요"
_TS = re.compile(r"(\d{4})\. (\d+)\. (\d+) (오전|오후) (\d+):(\d+):(\d+)")


def parse_kst(text: str) -> datetime:
    y, mo, d, ap, h, mi, s = _TS.fullmatch(text.strip()).groups()
    hour = int(h) % 12 + (12 if ap == "오후" else 0)
    return datetime(int(y), int(mo), int(d), hour, int(mi), int(s))


def count_new_responses(csv_path: Path, cutoff: datetime, dev_cards: set[int], test_cards: set[int]) -> dict[str, int]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    cards = []
    for name in rows[0][3:]:
        head = name.split(".")[0].strip()
        cards.append(int(head) if head.isdigit() else None)
    out = {"dev": 0, "test": 0, "other": 0, "blank": 0}
    for row in rows[1:]:
        if len(row) < 2 or row[1].strip() != CONSENT or parse_kst(row[0]) <= cutoff:
            continue
        for card, cell in zip(cards, row[3:]):
            if not cell.strip():
                out["blank"] += 1
            elif card in dev_cards:
                out["dev"] += 1
            elif card in test_cards:
                out["test"] += 1
            else:
                out["other"] += 1
    return out


def report(csv_path: Path, cutoff: datetime, dev_cards: set[int], test_cards: set[int]) -> dict[str, int]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))[1:]
    new = [r for r in rows if parse_kst(r[0]) > cutoff]
    consented = [r for r in new if len(r) > 1 and r[1].strip() == CONSENT]
    counts = count_new_responses(csv_path, cutoff, dev_cards, test_cards)
    print(f"전체 응답 {len(rows)}, 새 응답 {len(new)}, 새 응답 중 동의 {len(consented)}")
    print(counts)
    return counts


if __name__ == "__main__":
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    report(SRC, CUTOFF, set(split["dev_cards"]), set(split["test_cards"]))
