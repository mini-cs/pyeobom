"""결정기록 032 다시 세기 (Fable 분할 설계 7절, 결정기록 033, 계획 Task 9).

v1.7 A-3 실행과 운영 반영 9단계 30문항 2회에서 정답·정답(경계)으로 판정된 답을 모은다(`targets`).
판정 원자료는 판정 뒤 결과 CSV의 `human_verdict` 열에 옮겨 커밋한 값이다(evaluation/results/, 2026-11-17·19).
새 판정(덧붙임 판정 규칙, 평가 규칙)을 넣으면 ⑰로 A-3 표를 다시 센다(`recount_a3`).
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ingest.load import ROOT

RESULTS = ROOT / "evaluation" / "results"
OUT = ROOT / "measure" / "out" / "fable" / "recount-032"
DATE = "2026-11-17"
# (실행, 결과 CSV 이름(날짜 앞), 벌(None이면 CSV method 열), 회차, 가린 판정지)
RUNS = [
    *[("v17-s3", f"v17-s3-{r}", None, r, "v17-s3") for r in ("r1", "r2")],
    *[(run, f"{run}-{m}-{r}", method, r, "v17-s4")
      for run in ("v17-s4", "v17-s4fu") for m, method in (("m0", "m0"), ("strip", "strip_800")) for r in ("r1", "r2")],
    *[("v17-rollout", f"v17-rollout-{r}", "rollout", r, "") for r in ("r1", "r2")],  # 운영 반영 9단계, 가린 판정지 없이 판정
]
COLUMNS = ["run", "method", "qid", "round", "model_id", "question", "answer", "old_verdict", "sheet", "answer_no"]
_VERDICT = re.compile(r"^\s*(정답|오답|환각)\s*(\(경계\))?")
_ANSWER_NO = re.compile(r"\(답 (\d+)\)\s*$")


def parse_verdict(text: str) -> tuple[str, bool, str]:
    """`human_verdict` 칸 → (판정, 경계 여부, 가린 판정지 답 번호 또는 "")."""
    m = _VERDICT.match(text)
    if not m:
        raise ValueError(f"판정을 읽을 수 없음: {text[:20]!r}")
    no = _ANSWER_NO.search(text)
    return m[1], bool(m[2]), no[1] if no else ""


def _dev_models() -> dict[str, str]:
    lines = [l for l in open(ROOT / "evaluation" / "paraphrase_dev.csv", encoding="utf-8-sig") if not l.startswith("#")]
    return {r["id"]: r["model_id"] for r in csv.DictReader(lines)}


def load_rows(runs=RUNS, root: Path = RESULTS) -> list[dict]:
    rows, models = [], None
    for run, stem, method, rnd, sheet in runs:
        with open(root / f"{stem}.csv" if (root / f"{stem}.csv").exists() else root / f"{stem}-{DATE}.csv",
                  encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                verdict, boundary, no = parse_verdict(r["human_verdict"])
                qid = r["id"] if r.get("id") else f"{r['dialog_id']}-{r['turn']}"
                model = r.get("model_id")
                if not model:  # 3단계 결과에는 model_id 열이 없어 개발용 세트에서 찾는다
                    models = models or _dev_models()
                    model = models[qid]
                rows.append({"run": run, "method": method or r["method"], "qid": qid, "round": rnd, "model_id": model,
                             "question": r["question"], "answer": r["answer"],
                             "old_verdict": verdict + ("(경계)" if boundary else ""), "sheet": sheet, "answer_no": no})
    return rows


def collect_targets(runs=RUNS, root: Path = RESULTS) -> list[dict]:
    return [r for r in load_rows(runs, root) if r["old_verdict"].startswith("정답")]


def recount_a3(old: list[dict], new: dict[tuple, str]) -> dict:
    """새 판정(키: (run, method, qid, round))을 넣고 ⑰로 다시 셈: 모든 회차 정답이면 정답, 한 회차라도 환각이면 환각."""
    by_q = defaultdict(list)
    for r in old:
        v = new.get((r["run"], r["method"], r["qid"], r["round"]), r["old_verdict"])
        by_q[(r["run"], r["method"], r["qid"])].append(v)
    out: dict = {}
    for (run, method, _), vs in by_q.items():
        s = out.setdefault((run, method), {"correct": 0, "hallucination": 0, "denominator": 0})
        s["denominator"] += 1
        s["correct"] += all(v.startswith("정답") for v in vs)
        s["hallucination"] += any(v.startswith("환각") for v in vs)
    return out


def main() -> None:
    if sys.argv[1:] != ["targets"]:
        raise SystemExit("사용법: python -m measure.recount_032 targets")
    targets = collect_targets()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "targets.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["row", *COLUMNS])
        w.writeheader()
        w.writerows({"row": i, **t} for i, t in enumerate(targets, 1))
    # 답 글은 출력하지 않고 수만
    for k, n in sorted(Counter((t["run"], t["method"], t["round"], t["old_verdict"]) for t in targets).items()):
        print(*k, n)
    print("합계", len(targets))


if __name__ == "__main__":
    main()
