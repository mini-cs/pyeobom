"""2차 확인 질문 세트 검사와 모델 합격 판정(설계 9.3-7·8, 계획 Global 6). 측정 전에 고정."""
import re

VERDICTS = ("정답", "오답", "환각", "찾지 못함")
KINDS = ("사용법", "에러 코드")
PASS_CORRECT = 8
PAGES_RE = re.compile(r"\d+(;\d+)*")
SOURCE_RE = re.compile(r"manual|guide:\S+")


def validate_confirm_set(rows: list[dict], page_count: int) -> list[str]:
    problems = []
    if len(rows) != 10:
        problems.append(f"질문이 10개가 아님: {len(rows)}개")
    for r in rows:
        qid = r.get("qid", "?")
        if r.get("kind") not in KINDS:
            problems.append(f"{qid}: kind는 사용법·에러 코드 중 하나")
        if not SOURCE_RE.fullmatch(r.get("source") or ""):
            problems.append(f"{qid}: source는 manual 또는 guide:<doc_id>")
        elif r.get("kind") == "사용법" and r.get("source") != "manual":
            problems.append(f"{qid}: 사용법 질문은 설명서(manual)에서만")
        if not PAGES_RE.fullmatch(r.get("expected_pages") or ""):
            problems.append(f"{qid}: expected_pages가 비었거나 형식이 아님(예: 12;13)")
        elif r.get("source") == "manual" and not all(1 <= int(p) <= page_count for p in r["expected_pages"].split(";")):
            problems.append(f"{qid}: expected_pages가 설명서 쪽 범위(1~{page_count}) 밖")
    errors = sum(r.get("kind") == "에러 코드" for r in rows)
    if errors not in (0, 2):
        problems.append(f"에러 코드 질문은 0개 또는 2개: {errors}개")
    # 앞·중간·뒤 고르게: 설명서(manual) 사용법 질문의 정답 쪽 중 가장 앞 쪽으로 1/3을 나눈다(적는 순서와 무관)
    thirds = [0, 0, 0]
    for r in rows:
        pages = r.get("expected_pages") or ""
        if r.get("kind") == "사용법" and r.get("source") == "manual" and PAGES_RE.fullmatch(pages):
            first = min(int(p) for p in pages.split(";"))
            if 1 <= first <= page_count:
                thirds[(first - 1) * 3 // page_count] += 1
    for name, n in zip(("앞", "중간", "뒤"), thirds):
        if n < 2:
            problems.append(f"설명서 {name} 1/3의 사용법 질문이 2개 미만: {n}개")
    return problems


def passes(judgments: list[dict]) -> tuple[bool, dict]:
    for r in judgments:
        if r["verdict"] not in VERDICTS:
            raise ValueError(f"{r['qid']}: 모르는 판정 {r['verdict']!r}")
        if r["borderline"] == "yes" and r["worse_verdict"] not in VERDICTS:
            raise ValueError(f"{r['qid']}: 경계 판정에는 worse_verdict가 필요")
    worst = [r["worse_verdict"] if r["borderline"] == "yes" else r["verdict"] for r in judgments]
    best = [r["verdict"] for r in judgments]
    detail = {"correct": best.count("정답"), "hallucination": best.count("환각"),
              "correct_worst": worst.count("정답"), "hallucination_worst": worst.count("환각")}
    ok = detail["correct_worst"] >= PASS_CORRECT and detail["hallucination_worst"] == 0 \
        and detail["correct"] >= PASS_CORRECT and detail["hallucination"] == 0
    return ok, detail
