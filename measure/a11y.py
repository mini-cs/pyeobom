"""1차 화면 상태 4개(빈 화면·답·찾지 못함·오류)에 axe-core를 돌려 접근성 위반 수를 잰다(AI 비용 없음, 설계 8절).

`/api/ask`는 Playwright로 가로채 고정 응답(fixtures)을 돌려주므로 AI를 부르지 않는다. `/api/models`는 실제 API를 쓴다.
사용법: .venv/Scripts/python -m measure.a11y [주소]   (먼저 measure/에서 npm install)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AXE = HERE / "node_modules" / "axe-core" / "axe.min.js"
OUT = HERE / "out"
IMPACTS = ("critical", "serious", "moderate", "minor")
ERROR_BODY = {"error_code": "AI_TIMEOUT", "message": "답변이 늦어지고 있어요. 잠시 후 다시 시도해 주세요"}


def summarize_violations(results: dict) -> dict:
    violations = results["violations"]
    by_impact = {impact: 0 for impact in IMPACTS}
    for v in violations:
        by_impact[v["impact"]] += 1
    return {"total": len(violations), "by_impact": by_impact, "rules": [v["id"] for v in violations]}


def _fixture(name: str) -> str:
    return (HERE / "fixtures" / name).read_text(encoding="utf-8")


STATES = {  # 상태 이름 → (/api/ask 가로채기 상태 코드, 본문). None이면 질문을 보내지 않음
    "empty": None,
    "answer": (200, _fixture("ask_found.json")),
    "not_found": (200, _fixture("ask_not_found.json")),
    "error": (504, json.dumps(ERROR_BODY, ensure_ascii=False)),
}


def run(url: str) -> dict:
    from playwright.sync_api import sync_playwright  # 측정할 때만 필요(단위 테스트는 요약 함수만 씀)

    OUT.mkdir(exist_ok=True)
    summaries = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")  # 설치된 크롬 사용(브라우저 내려받기 없음)
        for state, reply in STATES.items():
            page = browser.new_page(viewport={"width": 360, "height": 740})
            if reply:
                status, body = reply
                page.route("**/api/ask", lambda route, request, s=status, b=body: route.fulfill(
                    status=s, content_type="application/json", body=b))
            page.goto(url)
            page.wait_for_function("document.getElementById('model-name').textContent.includes('(')")
            if reply:
                page.fill("#question", "측정용 질문입니다")
                page.click("#send")
                page.wait_for_selector("#result .card")  # 로딩 표시(.loading)가 아니라 결과 카드가 나올 때까지
            page.add_script_tag(path=str(AXE))
            results = page.evaluate("axe.run()")
            (OUT / f"axe-{state}.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
            summaries[state] = summarize_violations(results)
            page.close()
        version = results["testEngine"]["version"]
        browser.close()
    return {"axe": version, "url": url, "states": summaries}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else "https://pyeobom.vercel.app"), ensure_ascii=False, indent=1))
