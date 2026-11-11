"""v1.5 화면 상태 전부(계획 3 채택 조건 4)에 axe-core를 돌려 위반·확인 필요 수를 잰다(AI 비용 없음).

`/api/ask`는 언제나 Playwright로 가로채 고정 응답(measure/fixtures/)을 돌려주므로 AI를 부르지 않는다.
주소를 주지 않으면 public/을 로컬 정적 서버로 띄우고 `/api/models`도 data/models.json 공개 필드로 가로챈다.
주소(미리보기)를 주면 `/api/models`는 그 주소의 실제 API를 쓴다(AI·DB 호출 없음).
사용법: .venv/Scripts/python -m measure.a11y [주소]   (먼저 measure/에서 npm install)
결과: measure/out/axe-<local|호스트>-<상태>.json(전체), axe-summary-<local|호스트>.json(요약)
"""
import contextlib
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from measure.load_common import bypass_headers

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / "public"
AXE = HERE / "node_modules" / "axe-core" / "axe.min.js"
OUT = HERE / "out"
IMPACTS = ("critical", "serious", "moderate", "minor")
ERROR_BODY = {"error_code": "AI_TIMEOUT", "message": "답변이 늦어지고 있어요. 잠시 후 다시 시도해 주세요"}
QUESTION = "측정용 질문입니다"

# 계획 3 채택 조건 4의 상태 목록 그대로. 값은 랜딩에서 시작해 차례로 할 일
STATES = {
    "landing-empty": [],
    "landing-recent": ["chat", "ask:found", "home"],
    "category": ["category"],
    "model-washer": ["model:세탁기"],
    "model-aircon": ["model:에어컨"],
    "chat-empty": ["chat"],
    "chat-loading": ["chat", "ask:hold"],
    "chat-answer": ["chat", "ask:found"],
    "chat-followup": ["chat", "ask:found", "ask:found"],   # 이어지는 답과 접힌 이전 답
    "chat-not-found": ["chat", "ask:not_found"],
    "chat-other-brand": ["chat", "ask:other_brand"],
    "chat-error": ["chat", "ask:error"],
    "chat-save-failed": ["nosave", "chat", "ask:found"],
    "drawer": ["chat", "ask:found", "drawer"],
    "delete-all-confirm": ["chat", "ask:found", "drawer", "delete-all"],
}
NO_SAVE = "Storage.prototype.setItem = function () { throw new DOMException('측정용 공간 부족', 'QuotaExceededError'); };"
FIXTURES = {"found": "ask_found.json", "not_found": "ask_not_found.json", "other_brand": "ask_other_brand.json"}


def summarize_violations(results: dict) -> dict:
    violations = results["violations"]
    by_impact = {impact: 0 for impact in IMPACTS}
    for v in violations:
        by_impact[v["impact"]] += 1
    return {"total": len(violations), "by_impact": by_impact, "rules": [v["id"] for v in violations]}


def summarize(results: dict) -> dict:
    incomplete = results["incomplete"]
    return {**summarize_violations(results), "incomplete": len(incomplete), "incomplete_rules": [i["id"] for i in incomplete]}


def fake_reply(kind: str, question: str) -> tuple[int, dict]:
    """가짜 /api/ask 응답. 가린 질문은 보낸 질문 그대로(측정 질문에는 개인정보가 없다)."""
    if kind == "error":
        return 504, ERROR_BODY
    body = json.loads((HERE / "fixtures" / FIXTURES[kind]).read_text(encoding="utf-8"))
    return 200, {**body, "question_masked": question}


class _Handler(SimpleHTTPRequestHandler):
    # 윈도 레지스트리의 MIME 값에 휘둘리지 않게 고정(JS 모듈은 JavaScript 형식이어야 불러와짐)
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".svg": "image/svg+xml", ".woff2": "font/woff2"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def log_message(self, *args):
        pass


@contextlib.contextmanager
def serve_public():
    """public/을 127.0.0.1의 빈 포트로 띄운다. /api/*는 없다(가로채서 씀)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _ask_handler(replies, held):
    def on_ask(route):  # 실제 /api/ask에는 가지 않는다. replies의 다음 종류로 답하고, hold면 붙잡아 둔다
        kind = replies.pop(0)
        if kind == "hold":
            held.append(route)
            return
        question = json.loads(route.request.post_data or "{}").get("question", "")
        status, body = fake_reply(kind, question)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body, ensure_ascii=False))
    return on_ask


def _settle(page):
    # 글꼴을 받고, 끝나는 움직임(서랍 슬라이드 등)이 끝난 뒤 잰다. 무한 반복(진행 막대)은 기다리지 않는다
    page.evaluate("async () => { await document.fonts.ready; }")
    page.wait_for_function("""() => document.getAnimations().every((a) =>
        a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)""")


def _prepare(page, base, steps, replies):
    asked = 0
    for step in steps:
        action, _, arg = step.partition(":")
        if action == "home":
            page.goto(base)
            page.locator("#landing-recent .conv-card").first.wait_for()
        elif action in ("category", "model", "chat"):
            page.get_by_role("link", name="시작하기").click()
            page.locator("#tiles").wait_for()
            if action != "category":
                page.get_by_role("button", name=arg or "세탁기").click()
                page.locator(".model-card").first.wait_for()
            if action == "chat":
                page.locator(".model-card").first.click()
                page.locator(".suggestion").first.wait_for()
        elif action == "ask":
            replies.append(arg)
            asked += 1
            page.fill("#question", QUESTION)
            page.click("#send")
            if arg == "hold":
                page.locator('.turn[data-state="loading"]').wait_for()
            else:
                page.wait_for_function("""(n) => document.querySelectorAll('.turn').length === n
                    && !document.querySelector('.turn[data-state="loading"]')""", arg=asked)
        elif action == "drawer":
            page.get_by_role("button", name="지난 대화").click()
            page.locator("#drawer .conv-card").first.wait_for()
        elif action == "delete-all":
            page.get_by_role("button", name="전체 삭제").click()
            page.locator("#delete-confirm").wait_for()
    if "nosave" in steps:
        page.locator("#save-note").wait_for()


def context_headers(url: str | None, secret: str | None) -> dict:
    # 미리보기는 배포 보호가 있어 우회 값을 헤더로만 보낸다(Locust·Promptfoo와 같음). 로컬에는 보내지 않는다
    return bypass_headers(secret) if url else {}


def run(url: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright  # 측정할 때만 필요(단위 테스트는 요약 함수만 씀)

    OUT.mkdir(exist_ok=True)
    tag = "local" if url is None else urlparse(url).hostname
    summaries = {}
    with contextlib.ExitStack() as stack:
        base = url.rstrip("/") if url else stack.enter_context(serve_public())
        models = None
        if url is None:
            from app.catalog.routes import list_models  # 실제 /api/models와 같은 공개 필드
            models = list_models()
        p = stack.enter_context(sync_playwright())
        browser = p.chromium.launch(channel="chrome")  # 설치된 크롬 사용(브라우저 내려받기 없음)
        if url:
            from ingest.__main__ import load_env  # 우회 값은 .env에서 읽고 출력하지 않는다
            load_env()
        headers = context_headers(url, os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET"))
        for state, steps in STATES.items():
            context = browser.new_context(viewport={"width": 360, "height": 740}, extra_http_headers=headers)
            replies, held = [], []
            context.route("**/api/ask", _ask_handler(replies, held))
            if models is not None:
                context.route("**/api/models", lambda route: route.fulfill(json=models))
            if "nosave" in steps:
                context.add_init_script(NO_SAVE)
            page = context.new_page()
            page.goto(base)
            _prepare(page, base, steps, replies)
            _settle(page)
            page.add_script_tag(path=str(AXE))
            results = page.evaluate("axe.run()")
            (OUT / f"axe-{tag}-{state}.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
            summaries[state] = summarize(results)
            for route in held:
                route.fulfill(status=504, json=ERROR_BODY)
            context.close()
        browser.close()
    summary = {"axe": results["testEngine"]["version"], "url": url or "local(public/)", "states": summaries}
    (OUT / f"axe-summary-{tag}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else None), ensure_ascii=False, indent=1))
