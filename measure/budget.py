"""측정 비용 장부 검사: AI 측정을 실행하기 전에 누적 예상 비용이 상한(설계 8절, 2달러)을 넘지 않는지 본다."""

CAP_USD = 2.0


def check_budget(ledger_rows: list[dict], new_cost_usd: float, cap_usd: float = CAP_USD) -> bool:
    total = sum(row["estimate_usd"] for row in ledger_rows) + new_cost_usd
    return round(total, 6) <= cap_usd  # 0.1+0.2 같은 소수 오차로 상한과 같은 값이 막히지 않게
