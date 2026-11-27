"""실제 흐름 테스트(2차 Task 11 ②): 운영 주소에서 실제 메일 코드로 A·B가 로그인해, A의 요청이 A의 "내 요청"에만 보이는지 확인한다.

설계 docs/superpowers/specs/2026-11-27-live-flow-test-design.md, 계획 docs/superpowers/plans/2026-11-27-live-flow-test-plan.md Task 2.
- 코드는 Resend 받기 API(GET /emails/receiving)로 읽는다. 받기 주소는 실행마다 새로 만든다(live_mail.make_address)
- 끝나면 이 실행의 두 받기 주소로 만든 계정만 관리 키로 지운다(요청은 on delete cascade). 못 지우면 실패
- 받기 주소·도메인·키·코드·user_id를 출력하지 않는다: 실패 문구는 scrub로 가린 뒤 pytrace=False로 알리고,
  메일이 보이는 요소는 확인 대상으로 쓰지 않는다. trace·실패 사진은 쓰지 않는다. 질문은 하지 않는다(OpenAI 0원)
"""
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

from ingest.__main__ import load_env
from tests.e2e.live_mail import extract_code, make_address, pick_mail, scrub

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
VIDEO_DIR = ROOT / "docs" / "Claude outputs" / "phase2" / "e2e"   # .gitignore 안(영상이 git에 안 들어감)
KST = timezone(timedelta(hours=9))   # Windows에 시간대 자료가 없을 수 있어 zoneinfo 안 씀
RESEND = "https://api.resend.com"
SIZE = {"width": 390, "height": 844}
T = 20_000   # 운영 주소·Supabase 응답을 기다리는 시간(ms)

# 앱 문구(원문 그대로)
DONE = "요청을 받았어요. 추가되면 메일로 알려 드릴게요."
DUPLICATE = "이미 요청하셨어요"
WRONG_CODE = "코드가 맞지 않아요. 다시 확인해 주세요"
EMPTY = "아직 요청이 없어요"
BRAND = "가짜브랜드"

# 녹화 중 받기 주소가 보이는 칸·글자를 투명하게(칸 모양은 남김). 앱 코드는 바꾸지 않는다
MASK_SCRIPT = """
(() => {
  const css = `#login-email, #login-code, #login-sent-email, #request-email, #drawer-email, #switch-current-email {
    color: transparent !important; -webkit-text-fill-color: transparent !important;
    text-shadow: none !important; caret-color: transparent !important; }`;
  const add = () => {
    const s = document.createElement("style");
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", add);
  else add();
})();
"""

NEEDED = ("RESEND_RECEIVING_API_KEY", "RESEND_RECEIVING_DOMAIN", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")


class Flow:
    """한 실행의 상태: 단계 이름·가릴 비밀 목록·코드 읽기."""

    def __init__(self):
        load_env()   # 로컬 .env(값은 출력하지 않음)
        missing = [n for n in NEEDED if not os.environ.get(n)]
        if missing:
            pytest.skip(f"{', '.join(missing)}가 없으면 실제 흐름 테스트를 건너뛴다")
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self.base = (os.environ.get("E2E_BASE_URL") or "https://pyeobom.help").rstrip("/")
        domain = os.environ["RESEND_RECEIVING_DOMAIN"]
        self.resend_key = os.environ["RESEND_RECEIVING_API_KEY"]
        self.supabase = os.environ["SUPABASE_URL"].rstrip("/")
        self.service_key = os.environ["SUPABASE_SERVICE_KEY"]
        self.bypass = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")
        self.addr = {"A": make_address("a", domain), "B": make_address("b", domain)}
        self.since = datetime.now(timezone.utc) - timedelta(minutes=2)
        self.started = datetime.now(KST)
        self.secrets: list[str | None] = [self.addr["A"], self.addr["B"], domain, self.resend_key,
                                          self.service_key, self.bypass]
        self.step = "시작"

    def wait_code(self, who: str) -> str:
        headers = {"Authorization": f"Bearer {self.resend_key}"}
        deadline = time.monotonic() + 90
        with httpx.Client(base_url=RESEND, headers=headers, timeout=20) as c:
            while True:
                r = c.get("/emails/receiving", params={"limit": 100})
                if r.status_code != 200:
                    raise RuntimeError(f"받기 목록 응답 {r.status_code}({who})")
                mail_id = pick_mail(r.json().get("data") or [], self.addr[who], self.since)
                if mail_id:
                    r = c.get(f"/emails/receiving/{mail_id}")
                    if r.status_code != 200:
                        raise RuntimeError(f"받은 메일 응답 {r.status_code}({who})")
                    body = r.json()
                    code = extract_code(body.get("text")) or extract_code(body.get("html"))
                    if not code:
                        raise RuntimeError(f"메일에서 코드를 찾지 못함({who})")
                    self.secrets.append(code)
                    return code
                if time.monotonic() > deadline:
                    raise RuntimeError(f"코드 메일이 90초 안에 오지 않음({who})")
                time.sleep(2)

    def delete_test_users(self) -> tuple[int, int]:
        """이 실행의 두 받기 주소로 만든 계정만 지운다. (지운 수, 찾은 수)."""
        want = {a.lower() for a in self.addr.values()}
        with httpx.Client(base_url=self.supabase, headers={"apikey": self.service_key}, timeout=30) as admin:
            r = admin.get("/auth/v1/admin/users", params={"page": 1, "per_page": 1000})
            if r.status_code != 200:
                raise RuntimeError(f"관리 사용자 목록 응답 {r.status_code}")
            ids = [u["id"] for u in r.json().get("users", []) if (u.get("email") or "").lower() in want]
            self.secrets.extend(ids)   # user_id도 실패 문구에서 가린다
            deleted = sum(admin.delete(f"/auth/v1/admin/users/{uid}").status_code in (200, 204) for uid in ids)
        return deleted, len(ids)


def add_bypass(context, flow: Flow) -> None:
    # 우회 머리글은 대상 주소로 가는 요청에만(Supabase·Resend로 보내지 않음). extra_http_headers는 모든 곳으로 가서 안 씀
    if not flow.bypass:
        return

    def handle(route):
        headers = {**route.request.headers, "x-vercel-protection-bypass": flow.bypass,
                   "x-vercel-set-bypass-cookie": "true"}
        route.continue_(headers=headers)

    context.route(f"{flow.base}/**", handle)


def login_sheet(page):
    return page.get_by_role("dialog", name="로그인")


def send_code(page, address: str):
    sheet = login_sheet(page)
    expect(sheet).to_be_visible(timeout=T)
    sheet.get_by_label("이메일").fill(address)
    sheet.get_by_role("button", name="코드 보내기").click()
    return sheet


def enter_code(sheet, code: str) -> None:
    sheet.get_by_label("인증 코드").fill("")
    sheet.get_by_label("인증 코드").fill(code)
    sheet.get_by_role("button", name="확인").click()


def fill_request(page, model_text: str) -> None:
    form = page.locator('[data-screen="request"]')
    form.get_by_label("브랜드").fill(BRAND)
    form.get_by_label("모델명").fill(model_text)
    form.get_by_role("button", name="요청하기").click()


def run_flow(page, flow: Flow) -> None:
    model_text = f"E2E-{datetime.now(timezone.utc):%m%d%H%M%S}"

    flow.step = "A 로그인"
    page.goto(flow.base)
    page.get_by_role("link", name="시작하기").click()
    page.get_by_role("button", name="건조기", exact=True).click()
    page.get_by_role("button", name="내 모델이 없어요").click()
    sheet = send_code(page, flow.addr["A"])
    enter_code(sheet, flow.wait_code("A"))
    expect(sheet).to_be_hidden(timeout=T)
    expect(page.get_by_role("heading", level=1)).to_have_text("내 모델 요청하기", timeout=T)

    flow.step = "A 요청"
    fill_request(page, model_text)
    # 결과 안내는 글자가 HTML에 처음부터 있고 숨어 있을 뿐이라 보이는지 먼저 본다(계획 덧붙임 1)
    expect(page.locator("#request-done")).to_be_visible(timeout=T)
    expect(page.locator("#request-done")).to_contain_text(DONE)

    flow.step = "방어 ① 같은 모델 다시 요청"
    fill_request(page, model_text)
    expect(page.locator("#request-error")).to_be_visible(timeout=T)
    expect(page.locator("#request-error")).to_contain_text(DUPLICATE)

    flow.step = "A 내 요청"
    page.goto(flow.base)
    summary = page.locator("#landing-requests")
    expect(summary).to_be_visible(timeout=T)
    expect(summary).to_contain_text("내 요청 1건")
    summary.click()
    items = page.locator("#requests-list .request-item")
    expect(items).to_have_count(1, timeout=T)
    expect(items.first).to_contain_text(f"{BRAND} {model_text}")
    expect(items.first).to_contain_text("대기")

    flow.step = "로그아웃"
    page.get_by_role("button", name="지난 대화").click()
    row = page.locator("#drawer .drawer-account")
    row.get_by_role("button", name="로그아웃").click()
    expect(row.get_by_role("button", name="로그인")).to_be_visible(timeout=T)

    flow.step = "B 로그인(방어 ② 틀린 코드)"
    row.get_by_role("button", name="로그인").click()
    sheet = send_code(page, flow.addr["B"])
    code = flow.wait_code("B")
    enter_code(sheet, code[:-1] + str((int(code[-1]) + 1) % 10))
    expect(page.locator("#login-code-error")).to_be_visible(timeout=T)
    expect(page.locator("#login-code-error")).to_contain_text(WRONG_CODE)
    enter_code(sheet, code)
    expect(sheet).to_be_hidden(timeout=T)

    flow.step = "B 내 요청(RLS)"
    with page.expect_response(lambda r: "/rest/v1/model_requests" in r.url, timeout=T):
        page.goto(flow.base)
    expect(page.locator("#landing-requests")).to_be_hidden(timeout=T)
    page.goto(f"{flow.base}/#requests")
    expect(page.locator("#requests-empty")).to_be_visible(timeout=T)   # 보이기 전의 0개 확인은 아무것도 증명하지 못함
    expect(page.locator("#requests-empty")).to_contain_text(EMPTY)
    expect(page.locator("#requests-list .request-item")).to_have_count(0)


def save_video(page, flow: Flow) -> None:
    src = Path(page.video.path())
    src.replace(VIDEO_DIR / f"live-flow-{flow.started:%Y%m%d-%H%M}.webm")


def test_live_request_flow_and_rls():
    flow = Flow()
    failure = None
    cleanup = None
    deleted = found = 0
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(viewport=SIZE, record_video_dir=str(VIDEO_DIR), record_video_size=SIZE)
                context.add_init_script(MASK_SCRIPT)
                add_bypass(context, flow)
                page = context.new_page()
                try:
                    run_flow(page, flow)
                except Exception as e:  # noqa: BLE001 — 단계 이름과 가린 문구만 남긴다
                    failure = (flow.step, type(e).__name__, scrub(str(e)[:500], flow.secrets))
                finally:
                    context.close()   # 닫아야 영상이 저장된다
                    save_video(page, flow)
            finally:
                browser.close()
    finally:
        try:
            deleted, found = flow.delete_test_users()
        except Exception as e:  # noqa: BLE001
            cleanup = f"{type(e).__name__} {scrub(str(e)[:300], flow.secrets)}"

    tally = f"정리 지움 {deleted}/{found}" + (f"(정리 오류: {cleanup})" if cleanup else "")
    if failure:
        pytest.fail(f"{failure[0]} 단계 실패: {failure[1]} {failure[2]} / {tally}", pytrace=False)
    if cleanup or found != 2 or deleted < found:
        pytest.fail(f"정리: {tally}", pytrace=False)
