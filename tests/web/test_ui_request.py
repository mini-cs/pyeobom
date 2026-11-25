"""2차 "내 모델 요청" 화면 테스트(계획 Task 6, 덧붙임 A-2·D). 로컬 정적 서버에서 열고 /api/*와 Supabase는 가로챈다.

Supabase 주소는 가짜(https://supabase.test)이고 실제 Supabase·구글·메일은 부르지 않는다(비용 0). 값은 모두 가짜.
"""
import base64
import json
import re
import time

import pytest
from playwright.sync_api import expect

from app.catalog.routes import list_models

pytestmark = pytest.mark.ui

MODELS = list_models()
TITLES = {m["id"]: m.get("short_name") or m["name"] for m in MODELS}
SUPABASE = "https://supabase.test"
PUBLIC_KEY = "sb_publishable_fake-public-key"
EMAIL = "tester@example.com"
CODE = "123456"
USER_ID = "00000000-0000-4000-8000-000000000001"

# 화면 문구(설계 5·10절, 계획 Task 6 "정해진 문구", 덧붙임 D-3)
CATEGORY_H1 = "어떤 가전이 궁금하세요?"
REQUEST_H1 = "내 모델 요청하기"
NO_MODEL = "내 모델이 없어요"
DRYER_EMPTY = "아직 등록된 건조기 모델이 없어요."
LOGIN_REASON = "모델이 추가되면 메일로 알려 드릴게요. 받을 이메일을 확인할게요"
PRIVACY = ("이메일과 요청 내용(가전 종류·브랜드·모델명)을 저장해요. 모델이 추가되면 알려 드리는 데만 써요. "
           "지우고 싶으면 알림 메일에 답장해 주세요. 2차 테스트 기간의 계정과 요청은 데모데이가 끝나면 지워요.")
ALREADY_EXISTS = "이미 있어요"
ASK_NOW = "바로 질문하기"
ALREADY_REQUESTED = "이미 요청하셨어요"
RECEIVED = "요청을 받았어요. 추가되면 메일로 알려 드릴게요."
UNAVAILABLE = "잠시 쓸 수 없어요"
WRONG_CODE = "코드가 맞지 않아요. 다시 확인해 주세요"
RESEND_WAIT = "잠시 뒤에 다시 보낼 수 있어요"
SEND_FAILED = "메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요"


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


# 모양만 JWT인 가짜 토큰(서명 없음). 서버가 확인하지 않는 가짜 Supabase에만 쓴다. amr은 지금 로그인 방식(맨 앞이 최근)
def make_token(email=EMAIL, method="otp"):
    payload = {"sub": USER_ID, "email": email, "role": "authenticated", "aud": "authenticated", "exp": 4102444800,
               "amr": [{"method": method, "timestamp": 1764040000}]}
    return f"{_b64({'alg': 'HS256', 'typ': 'JWT'})}.{_b64(payload)}.fake-signature"


FAKE_TOKEN = make_token()
USER = {"id": USER_ID, "aud": "authenticated", "role": "authenticated", "email": EMAIL,
        "app_metadata": {"provider": "email"}, "user_metadata": {}, "created_at": "2026-11-25T00:00:00Z"}


def session_body(email=EMAIL, method="otp"):
    return {"access_token": make_token(email, method), "token_type": "bearer", "expires_in": 3600,
            "expires_at": int(time.time()) + 3600, "refresh_token": "fake-refresh-token", "user": {**USER, "email": email}}


class FakeSupabase:
    """가짜 Supabase(Auth·Data API). 받은 요청을 적어 두고, 테스트가 정한 응답을 준다."""

    def __init__(self):
        self.calls = []
        self.down = False   # True면 연결 끊김(요청을 abort)
        self.otp = [(200, {})]   # 코드 보내기 응답(앞에서부터 하나씩, 마지막 것은 계속)
        self.insert = (201, [{"id": 1, "user_id": USER_ID, "category": "dryer", "status": "대기"}])
        self.token = None   # 구글 PKCE 교환 응답. None이면 구글 계정 세션
        self.hold_token = False   # True면 교환 응답을 붙잡아 둔다(테스트가 release로 보냄)
        self.held = []

    def release(self):
        for route, cors in self.held:
            route.fulfill(status=200, headers=cors, json=session_body(method="oauth"))
        self.held = []

    def posts(self, path):
        return [c for c in self.calls if c["method"] == "POST" and c["path"].startswith(path)]

    def handle(self, route):
        req = route.request
        path = req.url.split("supabase.test", 1)[1]
        cors = {"access-control-allow-origin": "*", "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
                "access-control-allow-headers": req.headers.get("access-control-request-headers", "*"),
                "access-control-expose-headers": "*"}
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=cors)
        body = json.loads(req.post_data) if req.post_data else None
        self.calls.append({"method": req.method, "path": path, "body": body, "headers": req.headers})
        if self.down:
            return route.abort()
        if path.startswith("/auth/v1/token") and self.hold_token:
            self.held.append((route, cors))
            return None
        status, data = self._answer(req.method, path, body)
        if isinstance(data, str):
            return route.fulfill(status=status, headers=cors, content_type="text/html", body=data)
        return route.fulfill(status=status, headers=cors, json=data)

    def _answer(self, method, path, body):
        if path.startswith("/auth/v1/otp"):
            return self.otp.pop(0) if len(self.otp) > 1 else self.otp[0]
        if path.startswith("/auth/v1/verify"):
            if body and body.get("token") == CODE:
                return 200, session_body(body.get("email") or EMAIL)
            return 403, {"code": 403, "error_code": "otp_expired", "msg": "Token has expired or is invalid"}
        if path.startswith("/auth/v1/token"):
            return self.token or (200, session_body(method="oauth"))   # 구글(PKCE) 교환
        if path.startswith("/auth/v1/user"):
            return 200, USER
        if path.startswith("/auth/v1/logout"):
            return 204, {}
        if path.startswith("/auth/v1/authorize"):
            return 200, "<!doctype html><title>가짜 구글</title><p>가짜 구글 로그인(테스트)</p>"
        if path.startswith("/rest/v1/model_requests"):
            return self.insert if method == "POST" else (200, [])
        return 404, {"message": "가짜 Supabase에 없는 주소(테스트)"}


def _ask_ok(body):
    return {"found": True, "answer": f"가짜 답입니다(테스트): {body['question']}", "citations": [],
            "official_url": "https://example.com/support", "latency_ms": 1, "pii_masked": False,
            "question_masked": body["question"], "rewritten_question": None, "reason": None}


@pytest.fixture
def open_app(browser, base_url):
    contexts = []

    def opener(config_status=200, init=None):
        fake = FakeSupabase()
        context = browser.new_context(viewport={"width": 360, "height": 780}, base_url=base_url)
        context.set_default_timeout(5000)
        context.route(re.compile(r"^(?!http://127\.0\.0\.1)"), lambda route: route.abort())  # 외부로 나가는 요청 없음
        context.route("https://supabase.test/**", fake.handle)   # 나중에 건 가로채기가 먼저 걸린다
        context.route("**/api/models", lambda route: route.fulfill(json=MODELS))
        config = {"supabase_url": SUPABASE, "supabase_anon_key": PUBLIC_KEY}
        context.route("**/api/public-config", lambda route: route.fulfill(
            status=config_status, json=config if config_status == 200 else
            {"error_code": "LOGIN_UNAVAILABLE", "message": "가짜 오류입니다(테스트)"}))
        context.route("**/api/ask", lambda route: route.fulfill(json=_ask_ok(json.loads(route.request.post_data))))
        if init:
            context.add_init_script(init)
        contexts.append(context)
        page = context.new_page()
        page.goto("/")
        return page, fake

    yield opener
    for c in contexts:
        c.close()


def go_model_screen(page, appliance_name):
    page.get_by_role("link", name="시작하기").click()
    expect(page.get_by_role("heading", level=1)).to_have_text(CATEGORY_H1)
    page.get_by_role("button", name=appliance_name, exact=True).click()


def login_sheet(page):
    return page.get_by_role("dialog", name="로그인")


def log_in_with_code(page, fake, email=EMAIL):
    sheet = login_sheet(page)
    sheet.get_by_label("이메일").fill(email)
    sheet.get_by_role("button", name="코드 보내기").click()
    sheet.get_by_label("인증 코드").fill(CODE)
    sheet.get_by_role("button", name="확인").click()
    expect(sheet).to_be_hidden()


def open_request_form(page, fake, appliance_name="건조기"):
    go_model_screen(page, appliance_name)
    page.get_by_role("button", name=NO_MODEL).click()
    log_in_with_code(page, fake)
    expect(page.get_by_role("heading", level=1)).to_have_text(REQUEST_H1)


def fill_request(page, brand, model_text):
    form = page.locator('[data-screen="request"]')
    form.get_by_label("브랜드").fill(brand)
    form.get_by_label("모델명").fill(model_text)
    form.get_by_role("button", name="요청하기").click()


# ── 건조기·내 모델이 없어요 ──

def test_dryer_tile_shows_empty_list_and_request_button(open_app):
    page, _ = open_app()
    go_model_screen(page, "건조기")
    expect(page.get_by_role("heading", level=1)).to_have_text("건조기 모델을 골라 주세요")
    expect(page.locator(".model-card")).to_have_count(0)
    expect(page.get_by_text(DRYER_EMPTY)).to_be_visible()
    expect(page.get_by_role("button", name=NO_MODEL)).to_be_visible()


def test_washer_model_screen_also_has_request_button(open_app):
    page, _ = open_app()
    go_model_screen(page, "세탁기")
    expect(page.locator(".model-card")).to_have_count(2)
    expect(page.get_by_role("button", name=NO_MODEL)).to_be_visible()


def test_request_requires_login_then_returns_to_form(open_app):
    page, fake = open_app()
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    sheet = login_sheet(page)
    expect(sheet).to_be_visible()
    # 시트가 올라오는 움직임이 끝난 뒤 잰다(움직이는 중에 둘을 따로 재면 위치가 어긋남)
    page.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
    expect(sheet.get_by_text(LOGIN_REASON)).to_be_visible()
    expect(sheet.get_by_text(PRIVACY)).to_be_visible()
    # 이유 문구는 맨 위, 개인정보 안내는 아래쪽(덧붙임 D-3)
    reason_top = sheet.get_by_text(LOGIN_REASON).bounding_box()["y"]
    privacy_top = sheet.get_by_text(PRIVACY).bounding_box()["y"]
    assert reason_top < privacy_top
    expect(sheet.get_by_text("또는", exact=True)).to_be_visible()
    google = sheet.get_by_role("button", name="Google로 계속하기")
    expect(google).to_be_visible()
    # G 아이콘(회색 배경을 뺀 공식 G)은 버튼 둥근 테두리 안쪽에 있다: 위·아래·왼쪽 모두 테두리에서 떨어짐
    icon = google.locator("img")
    assert icon.get_attribute("src") == "/icons/google-g.svg"
    expect(icon).to_have_js_property("complete", True)
    b, i = google.bounding_box(), icon.bounding_box()
    assert i["x"] - b["x"] >= 8 and i["y"] > b["y"] and i["y"] + i["height"] < b["y"] + b["height"], (b, i)
    log_in_with_code(page, fake)
    expect(page.get_by_role("heading", level=1)).to_have_text(REQUEST_H1)
    assert page.evaluate("location.hash") == "#request/dryer"
    expect(page.locator('[data-screen="request"]')).to_contain_text("건조기")   # 가전 종류는 고른 것 그대로
    # 인증 코드는 type email 하나로 확인한다(덧붙임 A-2)
    verify = fake.posts("/auth/v1/verify")
    assert len(verify) == 1 and verify[0]["body"]["type"] == "email" and verify[0]["body"]["email"] == EMAIL


def test_request_sends_only_three_columns_with_public_key(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    fill_request(page, " 가짜브랜드 ", " DV90-FAKE1 ")
    expect(page.get_by_text(RECEIVED)).to_be_visible()
    inserts = fake.posts("/rest/v1/model_requests")
    assert len(inserts) == 1
    body = inserts[0]["body"]
    row = body[0] if isinstance(body, list) else body
    assert row == {"category": "dryer", "brand": "가짜브랜드", "model_text": "DV90-FAKE1"}   # db.md: 넣기는 세 열만
    headers = inserts[0]["headers"]
    assert headers["apikey"] == PUBLIC_KEY and headers["authorization"] == f"Bearer {FAKE_TOKEN}"


def test_existing_model_offers_ask_now(open_app):
    page, fake = open_app()
    open_request_form(page, fake, "세탁기")
    fill_request(page, "삼성", "WD90H25AH-1234")
    expect(page.get_by_text(ALREADY_EXISTS)).to_be_visible()
    assert fake.posts("/rest/v1/model_requests") == []   # 이미 있는 모델은 요청을 넣지 않는다
    page.get_by_role("button", name=ASK_NOW).click()
    expect(page.locator("#chat-title")).to_have_text(TITLES["washer-samsung-wd90h25"])


def test_request_success_message(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    fill_request(page, "가짜브랜드", "DV90-FAKE2")
    expect(page.get_by_text(RECEIVED)).to_be_visible()
    # 요청이 끝나면 [요청하기]는 잠기지 않고 다시 눌리는 상태, 색도 평소 검은 버튼(마우스를 치운 뒤)
    submit = page.locator('[data-screen="request"]').get_by_role("button", name="요청하기")
    expect(submit).to_be_enabled()
    page.mouse.move(0, 0)
    expect(submit).to_have_css("background-color", "rgb(17, 17, 17)")


def test_duplicate_request_message(open_app):
    page, fake = open_app()
    fake.insert = (409, {"code": "23505", "message": "duplicate key value violates unique constraint (테스트)"})
    open_request_form(page, fake)
    fill_request(page, "가짜브랜드", "DV90-FAKE3")
    expect(page.get_by_text(ALREADY_REQUESTED)).to_be_visible()


def test_daily_limit_message(open_app):
    page, fake = open_app()
    fake.insert = (400, {"code": "P0001", "message": "최근 24시간 요청은 5개까지예요"})
    open_request_form(page, fake)
    fill_request(page, "가짜브랜드", "DV90-FAKE4")
    expect(page.get_by_text("오늘은 요청을 더 받을 수 없어요. 내일 다시 요청해 주세요")).to_be_visible()


# ── Review Focus 1·4 ──

def ask_in_chat_works(page):
    page.evaluate("() => { location.hash = '#model/washer'; }")
    page.locator(".model-card").first.click()
    page.locator("#question").fill("가짜 질문")
    page.locator("#question").press("Enter")
    expect(page.get_by_text("가짜 답입니다(테스트): 가짜 질문")).to_be_visible()


def test_request_unavailable_keeps_chat_working(open_app):
    # ① 공개 설정 주소가 503: 요청만 "잠시 쓸 수 없어요", 모델 고르기·질문은 그대로
    page, _ = open_app(config_status=503)
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    expect(page.get_by_text(UNAVAILABLE)).to_be_visible()
    expect(login_sheet(page)).to_be_hidden()
    ask_in_chat_works(page)
    # ② Supabase 연결이 끊김: 요청 넣기만 "잠시 쓸 수 없어요", 질문은 그대로
    page, fake = open_app()
    open_request_form(page, fake)
    fake.down = True
    fill_request(page, "가짜브랜드", "DV90-FAKE5")
    expect(page.get_by_text(UNAVAILABLE)).to_be_visible()
    ask_in_chat_works(page)


def test_request_after_session_expired_shows_login(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    fake.insert = (401, {"code": "PGRST303", "message": "JWT expired"})
    fill_request(page, "가짜브랜드", "DV90-FAKE6")
    expect(login_sheet(page)).to_be_visible()


# ── 로그인 시트(설계 10-3·10-6, 덧붙임 D-4·D-7) ──

def test_wrong_code_and_resend_wait_messages(open_app):
    page, fake = open_app()
    fake.otp = [(200, {}), (429, {"code": 429, "error_code": "over_email_send_rate_limit", "msg": "rate limit (테스트)"})]
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    sheet = login_sheet(page)
    sheet.get_by_label("이메일").fill(EMAIL)
    sheet.get_by_role("button", name="코드 보내기").click()
    sheet.get_by_label("인증 코드").fill("654321")
    sheet.get_by_role("button", name="확인").click()
    expect(sheet.get_by_text(WRONG_CODE)).to_be_visible()
    sheet.get_by_role("button", name="코드 다시 보내기").click()
    expect(sheet.get_by_text(RESEND_WAIT)).to_be_visible()


def test_send_code_failure_message(open_app):
    page, fake = open_app()
    fake.otp = [(500, {"code": 500, "error_code": "unexpected_failure", "msg": "Error sending magic link email (테스트)"})]
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    sheet = login_sheet(page)
    sheet.get_by_label("이메일").fill(EMAIL)
    sheet.get_by_role("button", name="코드 보내기").click()
    expect(sheet.get_by_text(SEND_FAILED)).to_be_visible()


def test_login_sheet_edit_email_and_resend(open_app):
    page, fake = open_app()
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    sheet = login_sheet(page)
    sheet.get_by_label("이메일").fill(EMAIL)
    sheet.get_by_role("button", name="코드 보내기").click()
    expect(sheet.get_by_text(EMAIL)).to_be_visible()   # 2단계: 보낸 이메일을 보여 준다
    sheet.get_by_role("button", name="코드 다시 보내기").click()
    expect(sheet.get_by_text(RESEND_WAIT)).to_be_hidden()   # 가짜 서버가 받아 주면 대기 문구 없음
    assert len(fake.posts("/auth/v1/otp")) == 2
    sheet.get_by_role("button", name="수정").click()
    expect(sheet.get_by_label("이메일")).to_have_value(EMAIL)   # 1단계로 돌아가 이메일을 고칠 수 있다
    expect(sheet.get_by_label("인증 코드")).to_be_hidden()


def test_drawer_login_opens_sheet_and_logout_after_login(open_app):
    page, fake = open_app()
    go_model_screen(page, "세탁기")
    page.get_by_role("button", name="지난 대화").click()
    drawer = page.locator("#drawer")
    expect(drawer.get_by_role("button", name="로그아웃")).to_have_count(0)
    drawer.get_by_role("button", name="로그인").click()
    expect(drawer).to_be_hidden()
    sheet = login_sheet(page)
    expect(sheet).to_be_visible()
    log_in_with_code(page, fake)
    page.get_by_role("button", name="지난 대화").click()
    expect(drawer.get_by_role("button", name="로그아웃")).to_be_visible()
    expect(drawer.get_by_role("button", name="로그인")).to_have_count(0)
    drawer.get_by_role("button", name="로그아웃").click()
    if not drawer.is_visible():
        page.get_by_role("button", name="지난 대화").click()
    expect(drawer.get_by_role("button", name="로그인")).to_be_visible()


def test_google_login_returns_to_request_form(open_app):
    # PKCE(flowType pkce): 돌아올 주소에 #이 없고, 떠나기 전 경로(#request/dryer)를 sessionStorage에 두었다가 돌아와 복원한다
    page, fake = open_app()
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    login_sheet(page).get_by_role("button", name="Google로 계속하기").click()
    page.wait_for_url(re.compile(r"^https://supabase\.test/auth/v1/authorize"))
    authorize = [c for c in fake.calls if c["path"].startswith("/auth/v1/authorize")][-1]
    query = authorize["path"]
    assert "provider=google" in query and "code_challenge=" in query
    redirect = re.search(r"redirect_to=([^&]+)", query).group(1)
    assert "%23" not in redirect and "#" not in redirect
    page.goto("/?code=fake-auth-code")
    expect(page.get_by_role("heading", level=1)).to_have_text(REQUEST_H1)
    assert page.evaluate("location.hash") == "#request/dryer"
    assert fake.posts("/auth/v1/token")   # 받은 code를 세션으로 바꿨다
    stored = page.evaluate("JSON.stringify(Object.assign({}, sessionStorage))")
    assert EMAIL not in stored   # sessionStorage에는 경로만(이메일 없음)


# ── 로그인 상태 보이기(Task 6 덧붙임, docs/superpowers/specs/2026-11-25-login-state-design.md) ──
OTHER_EMAIL = "other@example.com"


def account_box(page):
    return page.locator('[data-screen="request"] .account-box')


def test_request_screen_shows_notification_email(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    box = account_box(page)
    expect(box).to_be_visible()
    expect(box).to_contain_text("알림 받을 메일")
    expect(box.get_by_text(EMAIL)).to_be_visible()
    switch = box.get_by_role("button", name="계정 바꾸기")
    expect(switch).to_have_attribute("title", "계정 바꾸기")
    size = switch.bounding_box()
    assert size["width"] >= 44 and size["height"] >= 44, size   # 누르는 영역 --tap-min 이상


def test_switch_account_opens_sheet_without_logout_and_close_keeps_account(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    start_switch(page)   # 2026-11-25 덧붙임 2: 확인 창을 거친다
    sheet = login_sheet(page)
    expect(sheet).to_be_visible()
    expect(sheet.get_by_label("이메일")).to_be_visible()   # 1단계
    expect(sheet.get_by_text(SWITCH_GUIDE)).to_be_visible()   # 바꾸기 모양의 맨 위 안내
    sheet.get_by_role("button", name="닫기").click()
    expect(sheet).to_be_hidden()
    expect(account_box(page).get_by_text(EMAIL)).to_be_visible()   # 닫으면 원래 계정 그대로
    assert not [c for c in fake.calls if c["path"].startswith("/auth/v1/logout")]


def test_switch_account_to_other_email_updates_box(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    start_switch(page)   # 2026-11-25 덧붙임 2: 확인 창을 거친다
    log_in_with_code(page, fake, OTHER_EMAIL)
    expect(page.get_by_role("heading", level=1)).to_have_text(REQUEST_H1)
    expect(account_box(page).get_by_text(OTHER_EMAIL)).to_be_visible()
    expect(account_box(page).get_by_text(EMAIL, exact=True)).to_have_count(0)
    assert not [c for c in fake.calls if c["path"].startswith("/auth/v1/logout")]


def test_drawer_account_row_at_bottom_shows_email_and_logout(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    page.get_by_role("button", name="지난 대화").click()
    row = page.locator("#drawer .drawer-account")
    expect(row.get_by_text(EMAIL)).to_be_visible()
    expect(row.locator(".account-avatar")).to_have_text("T")   # 메일 첫 글자 대문자(장식)
    expect(row.locator(".account-avatar")).to_have_attribute("aria-hidden", "true")
    expect(row.get_by_role("button", name="로그아웃")).to_be_visible()
    # 서랍 맨 아래: 계정 줄 바로 다음이 하단 고지, 위에 구분선
    assert row.evaluate("(r) => r.nextElementSibling.classList.contains('drawer-footer')")
    assert row.evaluate("(r) => getComputedStyle(r).borderTopStyle") == "solid"
    row.get_by_role("button", name="로그아웃").click()
    if not page.locator("#drawer").is_visible():
        page.get_by_role("button", name="지난 대화").click()
    expect(row.get_by_role("button", name="로그인")).to_be_visible()   # 같은 자리에 로그인
    expect(row.get_by_text(EMAIL)).to_have_count(0)


# ── 로그인 방식 표시(L1)·계정 바꾸기 확인 창(S1), 설계 덧붙임 2026-11-25 ──
SWITCH_TITLE = "다른 계정으로 바꿀까요?"
SWITCH_TEXT = "바꾸면 앞으로 알림은 새 계정 메일로 가요. 지금까지 한 요청은 지금 계정에 남아요."
SWITCH_SHEET_TITLE = "다른 계정으로 로그인"
SWITCH_GUIDE = "새 계정으로 로그인하면 알림을 그 메일로 보내 드려요"


def switch_confirm(page):
    return page.get_by_role("dialog", name=SWITCH_TITLE)   # 2026-11-25 덧붙임 3: 화면 안 카드(group) → 막 위 팝업(dialog)


def start_switch(page):
    account_box(page).get_by_role("button", name="계정 바꾸기").click()
    switch_confirm(page).get_by_role("button", name="바꾸기", exact=True).click()


def drawer_row(page):
    page.get_by_role("button", name="지난 대화").click()
    return page.locator("#drawer .drawer-account")


def test_email_code_login_shows_method_in_box_and_drawer(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    expect(account_box(page)).to_contain_text("알림 받을 메일 · 메일 코드 계정")
    row = drawer_row(page)
    expect(row.get_by_text("메일 코드 계정")).to_be_visible()
    color = row.get_by_text("메일 코드 계정").evaluate("(e) => getComputedStyle(e).color")
    assert color == "rgb(107, 107, 107)", color   # --color-text-muted


def test_google_login_shows_google_method(open_app):
    page, fake = open_app()
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    login_sheet(page).get_by_role("button", name="Google로 계속하기").click()
    page.wait_for_url(re.compile(r"^https://supabase\.test/auth/v1/authorize"))
    page.goto("/?code=fake-auth-code")
    expect(page.get_by_role("heading", level=1)).to_have_text(REQUEST_H1)
    expect(account_box(page)).to_contain_text("알림 받을 메일 · Google 계정")
    expect(drawer_row(page).get_by_text("Google 계정")).to_be_visible()


def test_switch_confirm_shows_current_account_and_cancel_keeps_it(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    switch = account_box(page).get_by_role("button", name="계정 바꾸기")
    switch.click()
    confirm = switch_confirm(page)
    expect(confirm).to_be_visible()
    expect(confirm).to_contain_text("지금 계정 · 메일 코드 계정")
    expect(confirm.get_by_text(EMAIL)).to_be_visible()
    expect(confirm.get_by_text(SWITCH_TEXT)).to_be_visible()
    assert confirm.evaluate("(c) => c.contains(document.activeElement)")   # 열리면 창 안으로 포커스
    confirm.get_by_role("button", name="취소").click()
    expect(confirm).to_be_hidden()
    expect(login_sheet(page)).to_be_hidden()
    expect(switch).to_be_focused()
    expect(account_box(page).get_by_text(EMAIL)).to_be_visible()
    switch.click()   # Esc도 같다
    expect(confirm).to_be_visible()
    page.keyboard.press("Escape")
    expect(confirm).to_be_hidden()
    expect(switch).to_be_focused()
    assert not [c for c in fake.calls if c["path"].startswith("/auth/v1/logout")]


def test_switch_opens_blank_switch_sheet_without_logout(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    start_switch(page)
    sheet = page.get_by_role("dialog", name=SWITCH_SHEET_TITLE)
    expect(sheet).to_be_visible()
    expect(sheet.get_by_text(SWITCH_GUIDE)).to_be_visible()
    expect(sheet.get_by_text(LOGIN_REASON)).to_be_hidden()
    expect(sheet.get_by_label("이메일")).to_have_value("")   # 이전 로그인 메일이 채워지지 않음
    expect(sheet.get_by_role("button", name="Google로 계속하기")).to_be_visible()
    expect(sheet.get_by_text(PRIVACY)).to_be_visible()
    sheet.get_by_role("button", name="닫기").click()
    expect(account_box(page)).to_contain_text("알림 받을 메일 · 메일 코드 계정")   # 닫으면 지금 계정 그대로
    expect(account_box(page).get_by_text(EMAIL)).to_be_visible()
    assert not [c for c in fake.calls if c["path"].startswith("/auth/v1/logout")]


def test_switch_to_google_updates_method(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    start_switch(page)
    page.get_by_role("dialog", name=SWITCH_SHEET_TITLE).get_by_role("button", name="Google로 계속하기").click()
    page.wait_for_url(re.compile(r"^https://supabase\.test/auth/v1/authorize"))
    page.goto("/?code=fake-auth-code")
    expect(account_box(page)).to_contain_text("알림 받을 메일 · Google 계정")


def test_first_login_sheet_keeps_title_reason_and_starts_blank(open_app):
    page, fake = open_app()
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    sheet = page.get_by_role("dialog", name="로그인", exact=True)
    expect(sheet).to_be_visible()
    expect(sheet.get_by_text(LOGIN_REASON)).to_be_visible()
    expect(sheet.get_by_text(SWITCH_GUIDE)).to_be_hidden()
    sheet.get_by_label("이메일").fill(EMAIL)
    sheet.get_by_role("button", name="닫기").click()
    page.get_by_role("button", name=NO_MODEL).click()
    expect(sheet.get_by_label("이메일")).to_have_value("")   # 새로 열면 비어 있음


# ── 덧붙임 3(2026-11-25): 계정 바꾸기 확인은 막 위 팝업 ──
def test_switch_confirm_is_modal_popup_with_equal_buttons(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    account_box(page).get_by_role("button", name="계정 바꾸기").click()
    confirm = switch_confirm(page)
    expect(confirm).to_be_visible()
    # 팝업이 나타나는 움직임이 끝난 뒤 잰다(움직이는 중에 둘을 따로 재면 위치가 어긋남)
    page.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
    assert confirm.evaluate("(d) => d.tagName === 'DIALOG' && d.open && d.matches(':modal')")
    # 뒤 화면은 누를 수 없다: 팝업 밖 ☰ 버튼 자리를 누르면 막(팝업 dialog)이 받는다
    box = page.locator("#drawer-open").bounding_box()
    hit = page.evaluate("([x, y]) => document.elementFromPoint(x, y).id",
                        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
    assert hit == "switch-confirm", hit
    cancel = confirm.get_by_role("button", name="취소")
    ok = confirm.get_by_role("button", name="바꾸기", exact=True)
    c, o = cancel.bounding_box(), ok.bounding_box()
    assert abs(c["width"] - o["width"]) < 1 and c["y"] == o["y"], (c, o)   # 같은 너비 두 개 나란히
    assert c["height"] >= 44 and o["height"] >= 44, (c, o)


def test_switch_confirm_backdrop_click_closes_and_keeps_account(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    switch = account_box(page).get_by_role("button", name="계정 바꾸기")
    switch.click()
    confirm = switch_confirm(page)
    expect(confirm).to_be_visible()
    page.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
    page.mouse.click(5, 5)   # 팝업 밖(막)
    expect(confirm).to_be_hidden()
    expect(login_sheet(page)).to_be_hidden()
    expect(switch).to_be_focused()
    expect(account_box(page).get_by_text(EMAIL)).to_be_visible()
    assert not [c for c in fake.calls if c["path"].startswith("/auth/v1/logout")]


# ── Task 6 고침(2026-11-25): ①로그아웃 뒤 요청 화면 ②구글 로그인 뒤 첫 화면 깜빡임 ③바깥 누르기 ──
LOGIN_FAILED = "로그인하지 못했어요. 다시 시도해 주세요"
CHECKING = "로그인 확인 중…"
# 문서마다 화면을 그리기 직전(requestAnimationFrame)에 첫 화면이 보였는지 적는다
RECORD_LANDING = """
window.__landingSeen = false;
(function tick() {
  const s = document.querySelector('[data-screen="landing"]');
  if (s && s.checkVisibility()) window.__landingSeen = true;
  requestAnimationFrame(tick);
})();
"""


def wait_still(page):
    page.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")


def leave_for_google(page, sheet_name="로그인"):
    page.get_by_role("dialog", name=sheet_name).get_by_role("button", name="Google로 계속하기").click()
    page.wait_for_url(re.compile(r"^https://supabase\.test/auth/v1/authorize"))


def test_logout_on_request_screen_returns_to_model_screen(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    page.locator("#request-brand").fill("가짜브랜드")
    row = drawer_row(page)
    row.get_by_role("button", name="로그아웃").click()
    expect(row.get_by_role("button", name="로그인")).to_be_visible()
    expect(page).to_have_url(re.compile(r"#model/dryer$"))
    page.keyboard.press("Escape")
    expect(page.get_by_role("heading", level=1)).to_have_text("건조기 모델을 골라 주세요")
    expect(page.get_by_role("button", name=NO_MODEL)).to_be_visible()
    assert EMAIL not in page.content()   # 화면(DOM) 어디에도 이전 메일이 없다
    assert page.locator("#request-brand").input_value() == ""   # 입력값도 지운다


def test_google_return_goes_straight_to_request_screen(open_app):
    page, fake = open_app(init=RECORD_LANDING)
    fake.hold_token = True
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    leave_for_google(page)
    page.goto("/?code=fake-auth-code")
    expect(page.get_by_role("heading", level=1)).to_have_text(REQUEST_H1)
    expect(account_box(page)).to_contain_text(CHECKING)   # 세션이 준비될 때까지
    wait_until(page, lambda: fake.held)
    fake.release()
    expect(account_box(page)).to_contain_text("알림 받을 메일 · Google 계정")
    expect(account_box(page).get_by_text(EMAIL)).to_be_visible()
    assert page.evaluate("window.__landingSeen") is False   # 첫 화면은 한 번도 보이지 않았다
    assert "code=" not in page.url and page.url.endswith("#request/dryer")


def test_google_exchange_failure_opens_sheet_with_message(open_app):
    page, fake = open_app()
    fake.token = (400, {"error": "invalid_grant", "error_description": "가짜 실패(테스트)"})
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    leave_for_google(page)
    page.goto("/?code=fake-auth-code")
    sheet = login_sheet(page)
    expect(sheet).to_be_visible()
    expect(sheet.get_by_text(LOGIN_FAILED)).to_be_visible()


def test_google_from_drawer_returns_to_same_screen(open_app):
    page, fake = open_app(init=RECORD_LANDING)
    go_model_screen(page, "세탁기")
    page.get_by_role("button", name="지난 대화").click()
    page.locator("#drawer").get_by_role("button", name="로그인").click()
    leave_for_google(page)
    page.goto("/?code=fake-auth-code")
    expect(page.get_by_role("heading", level=1)).to_have_text("세탁기 모델을 골라 주세요")
    assert page.evaluate("window.__landingSeen") is False


def wait_until(page, check):
    for _ in range(100):
        if check():
            return
        page.wait_for_timeout(20)
    raise AssertionError("기다린 조건이 오지 않음")


NO_CLOSEDBY = "document.querySelectorAll('dialog').forEach((d) => d.removeAttribute('closedby'))"   # closedby를 모르는 브라우저처럼


def test_drawer_backdrop_click_closes_without_closedby(open_app):
    page, _ = open_app()
    go_model_screen(page, "세탁기")
    page.evaluate(NO_CLOSEDBY)
    page.get_by_role("button", name="지난 대화").click()
    drawer = page.locator("#drawer")
    expect(drawer).to_be_visible()
    wait_still(page)
    page.mouse.click(350, 400)   # 서랍(폭 316px) 오른쪽 막
    expect(drawer).to_be_hidden()
    expect(page.locator("#drawer-open")).to_be_focused()


def test_login_sheet_backdrop_click_closes_without_closedby(open_app):
    page, _ = open_app()
    go_model_screen(page, "건조기")
    page.evaluate(NO_CLOSEDBY)
    opener = page.get_by_role("button", name=NO_MODEL)
    opener.click()
    sheet = login_sheet(page)
    expect(sheet).to_be_visible()
    wait_still(page)
    page.mouse.click(180, 20)   # 시트 위 막
    expect(sheet).to_be_hidden()
    expect(opener).to_be_focused()


def test_switch_popup_backdrop_click_closes_without_closedby(open_app):
    page, fake = open_app()
    open_request_form(page, fake)
    page.evaluate(NO_CLOSEDBY)
    switch = account_box(page).get_by_role("button", name="계정 바꾸기")
    switch.click()
    confirm = switch_confirm(page)
    expect(confirm).to_be_visible()
    wait_still(page)
    page.mouse.click(5, 5)
    expect(confirm).to_be_hidden()
    expect(switch).to_be_focused()


# ── 첫 화면 숨김(auth-return)이 늘 풀리는지(2026-11-25 Step 6 확인) ──
LANDING_H1 = "가전 설명서, 대신 펴 봐 드려요"


def assert_not_blank(page, title):
    expect(page.get_by_role("heading", level=1)).to_have_text(title)
    assert page.evaluate("document.documentElement.classList.contains('auth-return')") is False


def test_code_without_saved_path_shows_landing(open_app):
    # a. 주소에 코드는 있는데 기억한 경로가 없을 때: 첫 화면이 보인다
    page, fake = open_app()
    page.goto("/?code=fake-auth-code")
    assert_not_blank(page, LANDING_H1)


def test_google_exchange_failure_keeps_request_screen_behind_sheet(open_app):
    # b. 교환 실패: 시트 뒤 화면도 비지 않는다(기억한 요청 화면)
    page, fake = open_app()
    fake.token = (400, {"error": "invalid_grant", "error_description": "가짜 실패(테스트)"})
    go_model_screen(page, "건조기")
    page.get_by_role("button", name=NO_MODEL).click()
    leave_for_google(page)
    page.goto("/?code=fake-auth-code")
    expect(login_sheet(page).get_by_text(LOGIN_FAILED)).to_be_visible()
    assert_not_blank(page, REQUEST_H1)


@pytest.mark.parametrize("broken", ["public-config", "supabase-js"])
def test_google_return_without_supabase_still_shows_screen(open_app, broken):
    # c. 공개 설정이나 supabase.js를 받지 못할 때도 화면이 비지 않는다
    page, fake = open_app(config_status=503 if broken == "public-config" else 200)
    if broken == "supabase-js":
        page.context.route("**/vendor/supabase.js", lambda route: route.abort())
    page.evaluate("sessionStorage.setItem('pyeobom.returnTo', '#request/dryer')")
    page.goto("/?code=fake-auth-code")
    assert_not_blank(page, REQUEST_H1)
