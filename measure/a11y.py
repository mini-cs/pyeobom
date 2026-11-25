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
    # 2026-11-11 근거 접기 확인용(조건 4의 15개 뒤에 덧붙임): 근거 펼침, 공식 링크 표시
    "chat-evidence-open": ["chat", "ask:found", "evidence"],
    "chat-doc-links": ["chat", "ask:found", "evidence", "links"],
    # 2026-11-25 2차 Task 6: 건조기 빈 목록·로그인 시트·요청 화면. 가짜 Supabase(SUPABASE)로만 돌아 로컬에서만 잰다
    "model-dryer": ["model:건조기"],
    "login-sheet": ["model:건조기", "nomodel"],
    "login-code": ["model:건조기", "nomodel", "email"],
    "request-form": ["model:건조기", "nomodel", "email", "code"],
    "request-done": ["model:건조기", "nomodel", "email", "code", "request"],
    # 2026-11-25 Task 6 덧붙임: 로그인한 상태의 서랍(맨 아래 계정 줄)
    "drawer-account": ["model:건조기", "nomodel", "email", "code", "account-drawer"],
    # 2026-11-25 Task 6 덧붙임 2: 계정 바꾸기 확인 창
    "switch-confirm": ["model:건조기", "nomodel", "email", "code", "switch"],
}
LOCAL_ONLY = {"model-dryer", "login-sheet", "login-code", "request-form", "request-done", "drawer-account", "switch-confirm"}
SUPABASE = "https://supabase.test"   # 가짜 주소. 실제 Supabase·메일은 부르지 않는다
FAKE_SESSION = {  # 모양만 맞춘 가짜 세션(토큰은 서명 없는 가짜)
    "access_token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJleHAiOjQxMDI0NDQ4MDB9.fake",
    "token_type": "bearer", "expires_in": 3600, "expires_at": 4102444800, "refresh_token": "fake-refresh-token",
    "user": {"id": "00000000-0000-4000-8000-000000000001", "aud": "authenticated", "role": "authenticated",
             "email": "tester@example.com", "app_metadata": {}, "user_metadata": {}, "created_at": "2026-11-25T00:00:00Z"},
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
                page.locator("#model-cards li").first.wait_for()   # 모델 카드 또는 "아직 등록된 … 없어요"
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
        elif action == "evidence":
            page.locator(".turn .fold").last.click()
            page.locator(".turn .evidence").first.wait_for()
        elif action == "links":
            page.locator(".turn .offer").last.click()
            page.locator(".turn .doc-links a").first.wait_for()
        elif action == "nomodel":
            page.get_by_role("button", name="내 모델이 없어요").click()
            page.locator("#login-email").wait_for()
        elif action == "email":
            page.fill("#login-email", "tester@example.com")
            page.get_by_role("button", name="코드 보내기").click()
            page.locator("#login-code").wait_for()
        elif action == "code":
            page.fill("#login-code", "123456")
            page.get_by_role("button", name="확인").click()
            page.locator("#request-brand").wait_for()
        elif action == "request":
            page.fill("#request-brand", "가짜브랜드")
            page.fill("#request-model", "DV90-FAKE1")
            page.get_by_role("button", name="요청하기").click()
            page.locator("#request-done").wait_for()
        elif action == "switch":
            page.get_by_role("button", name="계정 바꾸기").click()
            page.locator("#switch-confirm").wait_for()
        elif action == "account-drawer":
            page.get_by_role("button", name="지난 대화").click()
            page.locator("#drawer-email").wait_for()
        elif action == "delete-all":
            page.get_by_role("button", name="전체 삭제").click()
            page.locator("#delete-confirm").wait_for()
    if "nosave" in steps:
        page.locator("#save-note").wait_for()


def _fake_supabase(route):
    req = route.request
    cors = {"access-control-allow-origin": "*", "access-control-allow-methods": "GET,POST,OPTIONS",
            "access-control-allow-headers": req.headers.get("access-control-request-headers", "*")}
    if req.method == "OPTIONS":
        return route.fulfill(status=204, headers=cors)
    path = req.url.split("supabase.test", 1)[1]
    body = FAKE_SESSION if path.startswith("/auth/v1/verify") else ([] if path.startswith("/rest/") else {})
    status = 201 if path.startswith("/rest/") and req.method == "POST" else 200
    route.fulfill(status=status, headers=cors, json=body)


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
            if url and state in LOCAL_ONLY:
                continue
            context = browser.new_context(viewport={"width": 360, "height": 740}, extra_http_headers=headers)
            if state in LOCAL_ONLY:
                context.route("**/api/public-config", lambda route: route.fulfill(
                    json={"supabase_url": SUPABASE, "supabase_anon_key": "sb_publishable_fake-public-key"}))
                context.route(f"{SUPABASE}/**", _fake_supabase)
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
