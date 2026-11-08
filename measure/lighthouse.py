"""Lighthouse JSON 보고서 여러 개를 중앙값으로 요약한다(실행마다 점수가 출렁여 3회 중앙값만 기록, 설계 8절)."""
from statistics import median

AUDITS = {
    "lcp_ms": "largest-contentful-paint",
    "cls": "cumulative-layout-shift",
    "tbt_ms": "total-blocking-time",
    "fcp_ms": "first-contentful-paint",
}


def summarize_runs(reports: list[dict]) -> dict:
    summary = {"performance": median(r["categories"]["performance"]["score"] for r in reports)}
    for key, audit in AUDITS.items():
        summary[key] = median(r["audits"][audit]["numericValue"] for r in reports)
    summary["runs"] = len(reports)
    return summary


if __name__ == "__main__":
    import json
    import sys

    reports = [json.load(open(path, encoding="utf-8")) for path in sys.argv[1:]]
    print(json.dumps(summarize_runs(reports), ensure_ascii=False))
    print("lighthouse", reports[0]["lighthouseVersion"], reports[0]["fetchTime"], reports[0]["finalDisplayedUrl"])
