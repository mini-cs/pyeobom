"""바꾸기 시간 줄이기 실험(계획 2 Task 6): 같은 18턴을 설정별로 바꿔 보고 시간·토큰·비용·바꾼 문장을 저장한다.

사용법: python -m measure.compare_rewrite <새 세트 실행 결과 CSV(앞 대화 고정용)> [--settings base A B C D] [--runs 2] [--combo B+D]
- 실행 전에 docs/평가/v15-server.md 비용 장부에 예상 비용을 적고 check_budget(상한 1.5)을 통과해야 한다.
- 바꾸기 단계만 부른다(검색·답변 없음). 결과 CSV는 measure/out/에만 둔다(가린 질문·바꾼 질문 포함).
"""
import argparse
import csv
import datetime
import re
import statistics
import time
from dataclasses import replace
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
POINTERS = ("그거", "그건", "그게", "그걸", "그것", "거기", "그곳", "그때", "그런", "그렇게", "그럼", "그러면", "그래도",
            "이거", "이건", "이게", "이걸", "저거", "저건")
ENDINGS = ("도요?", "땐요?", "때는요?", "면요?", "은요?", "는요?")
_POINTER = re.compile(r"(?:^|\s)(?:" + "|".join(POINTERS) + r"|[그이저]\s)")
SHORT_CHARS = 10

SETTINGS = {  # 기준과 다른 점만 적는다
    "base": {},
    "A": {"model": "gpt-6.1-terra"},
    "B": {"effort": "none"},
    "C": {"shorten": True},
    "D": {"gate": True},
}
BASE = {"model": "gpt-6-luna", "effort": "low", "shorten": False, "gate": False}
PRICES = {"gpt-6-luna": (0.10, 0.50), "gpt-6.1-terra": (1.0, 5.0)}  # 1M 토큰당 입력·출력 USD(공식 가격표, 2026-11-09)


def needs_rewrite(question: str) -> bool:
    """D 규칙: 가리키는 말, 생략 끝말, 짧은 질문 중 하나라도 맞으면 바꾼다."""
    q = question.strip()
    return bool(_POINTER.search(q)) or q.endswith(ENDINGS) or len(re.sub(r"\s", "", q)) <= SHORT_CHARS


def shorten_history(history: list[dict], n_chars: int = 200) -> list[dict]:
    """C: 직전 질문 + 직전 답 앞 n_chars자만."""
    return [{"question": history[-1]["question"], "answer": history[-1]["answer"][:n_chars]}] if history else []


def config(name: str) -> dict:
    cfg = dict(BASE)
    for part in name.split("+"):
        cfg |= SETTINGS[part]
    return cfg


def load_turns(hist_csv: str) -> list[dict]:
    """고정 앞 대화: 실행 결과의 가린 질문·답을 대화 순서대로 history로 만든다(2번째 턴부터)."""
    with open(hist_csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    turns, history, current = [], [], None
    for r in rows:
        if r["dialog_id"] != current:
            current, history = r["dialog_id"], []
        if r["turn"] != "1":
            turns.append({"dialog_id": r["dialog_id"], "turn": r["turn"], "type": r["type"],
                          "question": r["question_masked"], "history": list(history[-3:])})
        history.append({"question": r["question_masked"], "answer": r["answer"]})
    return turns


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m measure.compare_rewrite")
    parser.add_argument("hist_csv")
    parser.add_argument("--settings", nargs="+", default=list(SETTINGS))
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--combo", default=None, help="조합 설정(예: B+D). 주면 이 설정만 실행")
    args = parser.parse_args()

    from ingest.__main__ import load_env
    load_env()
    from app.answer.rewrite import rewrite_question
    from app.core.config import get_settings

    names = [args.combo] if args.combo else args.settings
    turns, base_settings, rows = load_turns(args.hist_csv), get_settings(), []
    for run in range(1, args.runs + 1):
        for t in turns:
            for name in names:  # 설정을 번갈아 불러 시간대 차이가 한 설정에 몰리지 않게 한다
                cfg = config(name)
                row = {"setting": name, "run": run, "dialog_id": t["dialog_id"], "turn": t["turn"], "type": t["type"],
                       "question": t["question"], "skipped": False, "used": False, "reason": "", "rewritten": "", "ms": 0,
                       "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost_usd": 0.0}
                if cfg["gate"] and not needs_rewrite(t["question"]):
                    row |= {"skipped": True, "reason": "skipped"}
                else:
                    history = shorten_history(t["history"]) if cfg["shorten"] else t["history"]
                    settings = replace(base_settings, rewrite_model=cfg["model"], reasoning_effort=cfg["effort"])
                    start = time.perf_counter()
                    r = rewrite_question(t["question"], history, cfg["model"], settings)
                    ms = int((time.perf_counter() - start) * 1000)
                    pin, pout = PRICES[cfg["model"]]
                    u = r.usage
                    row |= {"used": r.used, "reason": r.reason, "rewritten": r.text if r.used else "", "ms": ms, **u,
                            "cost_usd": (u.get("input_tokens", 0) * pin + u.get("output_tokens", 0) * pout) / 1e6}
                row["effective"] = row["rewritten"] or t["question"]  # 검색에 실제로 쓰일 질문(건너뜀·실패면 원래 질문)
                rows.append(row)
                print(name, run, t["dialog_id"], t["turn"], row["reason"], row["ms"], flush=True)

    OUT.mkdir(exist_ok=True)
    label = (args.combo or "-".join(names)).replace("+", "_")
    out = OUT / f"rewrite-compare-{label}-{datetime.date.today().isoformat()}.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for name in names:
        rs = [r for r in rows if r["setting"] == name]
        called = [r["ms"] for r in rs if not r["skipped"]]
        print({"setting": name, "turns": len(rs), "called": len(called), "skipped": sum(r["skipped"] for r in rs),
               "median_ms": statistics.median(called) if called else 0, "max_ms": max(called, default=0),
               "mean_added_ms": round(sum(r["ms"] for r in rs) / len(rs)),
               "failures": sum(1 for r in rs if not r["skipped"] and not r["used"] and r["reason"] != "ok"),
               "cost_usd": round(sum(r["cost_usd"] for r in rs), 5)})
    print("csv:", out.name)


if __name__ == "__main__":
    main()
