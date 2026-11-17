"""v1.7 Task 11 갈래 나(회귀): 30문항과 이어지는 질문의 가린 판정지 한 장. `python -m measure.v17_blind4 --label v17-s4 --date 2026-11-17`

- 두 벌 × 두 회차 답을 섞고 무작위 번호를 붙인다. 30문항은 글자까지 같은 답을 묶는다.
- 이어지는 질문은 판정할 답마다 그 회차의 앞 턴 질문·답을 보여 주고, 그 턴까지의 대화가 글자까지 같을 때만 묶는다(⑲).
- 판정지·대응표는 measure/out/(git 밖). 대응표의 run = 결과 CSV 이름(판정 후 공개)
"""
import argparse
import csv
import json
import random
from pathlib import Path

from measure.stage2 import BLIND_HEADER

ROOT = Path(__file__).resolve().parent.parent
EXTRA = "- 함정이 아닌 문항의 '찾지 못함'은 오답(기준 문장 '설명서에 없다고 했는데 있으면 오답' 적용, 2026-11-17 사용자 결정)\n"


def _one_line(s: str) -> str:
    return s.replace("\r", " ").replace("\n", " ")


def build_sheet(q30: dict[str, list[dict]], fu: dict[str, list[dict]], rng, label: str) -> tuple[str, list[dict]]:
    """q30·fu: {결과 CSV 이름: 행들}. (판정지 글, 대응표)"""
    items = []  # (절, 항목 id, 머리 줄들, {묶음 글: [(run, 답)]})
    first = next(iter(q30.values()))
    for r0 in first:
        groups: dict[str, list] = {}
        for run, rows in q30.items():
            a = next(r["answer"] for r in rows if r["id"] == r0["id"])
            groups.setdefault(a, []).append(run)
        trap = " (함정)" if r0["type"].startswith("trap") else ""
        head = [f"## {r0['id']}{trap}", f"- 질문: {r0['question']}", f"- 기대 근거: {r0['expected_ref'] or '-'}"]
        items.append(("q30", r0["id"], head, {a: (runs, "", a) for a, runs in groups.items()}))
    fu_first = next(iter(fu.values()))
    for r0 in fu_first:
        d, n = r0["dialog_id"], int(r0["turn"])
        groups = {}
        for run, rows in fu.items():
            turns = sorted((r for r in rows if r["dialog_id"] == d), key=lambda r: int(r["turn"]))
            hist = " | ".join(f"{int(t['turn'])}턴 질문 {_one_line(t['question'])} → {int(t['turn'])}턴 답 {_one_line(t['answer'])}"
                              for t in turns if int(t["turn"]) < n)
            a = next(t["answer"] for t in turns if int(t["turn"]) == n)
            groups.setdefault((hist, a), []).append(run)
        trap = " (함정)" if r0["type"] == "trap" else ""
        head = [f"## {d}-{n} (대화 {d}, {n}턴){trap}", f"- 질문: {r0['question']}", f"- 기대 근거: {r0['expected_ref'] or '-'}"]
        items.append(("fu", f"{d}-{n}", head, {k: (runs, k[0], k[1]) for k, runs in groups.items()}))

    numbers = iter(rng.sample(range(100, 1000), sum(len(g) for *_, g in items)))
    lines = [BLIND_HEADER.replace("{label}", label).rstrip("\n").replace(
        "- 함정에 찾지 못함이면 **정답**(B 기준)\n", "- 함정에 찾지 못함이면 **정답**(B 기준)\n" + EXTRA), ""]
    key = []
    section = None
    for sec, item, head, groups in items:
        if sec != section:
            section = sec
            lines += ["# 30문항 절", ""] if sec == "q30" else ["# 이어지는 질문 절", "", "앞 대화 줄은 바로 아래 같은 번호 답을 만든 대화다. 판정 대상은 이 턴의 답뿐이다.", ""]
        lines += head
        entries = list(groups.values())
        rng.shuffle(entries)
        for runs, hist, answer in entries:
            no = next(numbers)
            if hist:
                lines.append(f"- 앞 대화(답 {no}): {hist}")
            lines.append(f"- **답 {no}**: {_one_line(answer)}  → 판정: ")
            key += [{"section": sec, "item": item, "run": run, "no": no} for run in runs]
        lines.append("")
    return "\n".join(lines), key


def _read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--date", required=True)
    args = ap.parse_args()
    res = ROOT / "evaluation" / "results"
    q30 = {p.stem: _read(p) for p in sorted(res.glob(f"{args.label}-*-{args.date}.csv"))}
    fu = {p.stem: _read(p) for p in sorted(res.glob(f"{args.label.replace('-s4', '-s4fu')}-*-{args.date}.csv"))}
    if len(q30) != 4 or len(fu) != 4:
        raise SystemExit(f"결과 CSV가 4개씩이 아니라 멈춤: 30문항 {len(q30)}, 이어지는 질문 {len(fu)}")
    out = ROOT / "measure" / "out"
    sheet, key_path = out / f"{args.label}-blind-sheet.md", out / f"{args.label}-blind-key.json"
    if sheet.exists() or key_path.exists():
        raise SystemExit("판정지 또는 대응표가 이미 있어 멈춤(덮어쓰지 않음)")
    text, key = build_sheet(q30, fu, random.SystemRandom(), args.label)
    sheet.write_text(text, encoding="utf-8")
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")  # 판정 후 공개
    print(sheet, "답", text.count("**답 "), "대응", len(key))


if __name__ == "__main__":
    main()
