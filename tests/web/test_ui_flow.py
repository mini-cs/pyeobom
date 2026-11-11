"""화면 흐름(랜딩 → 카테고리 → 모델) Playwright 테스트. 로컬 정적 서버에서 열고 /api/*는 가로챈다(AI 비용 없음)."""
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from app.answer.check import GUIDE_WARNING
from app.catalog.routes import list_models

pytestmark = pytest.mark.ui

PUBLIC = Path(__file__).resolve().parents[2] / "public"
MODELS = list_models()  # 실제 /api/models와 같은 공개 필드만
NAMES = {m["id"]: m["name"] for m in MODELS}  # 화면 이름(코드 없음). 코드는 모델 선택 카드에만
TITLES = {m["id"]: m.get("short_name") or m["name"] for m in MODELS}  # 채팅 위쪽 막대 이름(short_name ?? name)
CODES = [c for m in MODELS for c in m["model_codes"]]
LANDING_H1 = "가전 설명서, 대신 펴 봐 드려요"
CATEGORY_H1 = "어떤 가전이 궁금하세요?"
AI_NOTE = "제품 그림은 AI로 그린 일러스트예요. 실제 제품과 다를 수 있어요."
STORE_KEY = "pyeobom.conversations"


class _Handler(SimpleHTTPRequestHandler):
    # 윈도 레지스트리의 MIME 값에 휘둘리지 않게 고정(JS 모듈은 JavaScript 형식이어야 불러와짐)
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".svg": "image/svg+xml", ".woff2": "font/woff2"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def playwright():
    with sync_playwright() as p:   # 한 스레드에 하나만 열 수 있어 브라우저들이 함께 쓴다
        yield p


@pytest.fixture(scope="module")
def browser(playwright):
    b = playwright.chromium.launch()
    yield b
    b.close()


def _conversation(i, model_id):
    day = f"2026-11-0{i}T09:00:00.000Z"
    return {"id": f"c{i}", "model_id": model_id, "title": f"가짜 질문 {i}", "created_at": day, "updated_at": day,
            "turns": [{"question_masked": f"가짜 질문 {i}", "rewritten_question": None, "answer": "가짜 답",
                       "found": False, "citations": [], "kind": "not_found"}]}


def _ask_504(body, route):
    return 504, {"error_code": "AI_TIMEOUT", "message": "가짜 오류입니다(테스트)"}


def _open(browser, base_url, path="/", conversations=None, ask=None, init=None):
    context = browser.new_context(viewport={"width": 360, "height": 780}, base_url=base_url)
    context.set_default_timeout(5000)  # 실패할 때 30초씩 기다리지 않게
    context.route(re.compile(r"^(?!http://127\.0\.0\.1)"), lambda route: route.abort())  # 외부로 나가는 요청 없음
    context.route("**/api/models", lambda route: route.fulfill(json=MODELS))
    asks = []  # 화면이 보낸 /api/ask 요청 본문

    def handle_ask(route):  # 실제 /api/ask에 붙지 않는다. ask가 None을 돌려주면 응답을 붙잡아 둔다(테스트가 나중에 보냄)
        body = json.loads(route.request.post_data or "{}")
        asks.append(body)
        result = (ask or _ask_504)(body, route)
        if result is not None:
            route.fulfill(status=result[0], json=result[1])

    context.route("**/api/ask", handle_ask)
    if conversations is not None:
        state = json.dumps({"version": 1, "conversations": conversations}, ensure_ascii=False)
        context.add_init_script(f"localStorage.setItem({json.dumps(STORE_KEY)}, {json.dumps(state)})")
    if init:
        context.add_init_script(init)
    page = context.new_page()
    page.goto(path)
    return page, asks


@pytest.fixture
def open_page(browser, base_url):
    pages = []

    def opener(path="/", conversations=None, ask=None, init=None, with_asks=False):
        page, asks = _open(browser, base_url, path, conversations, ask, init)
        pages.append(page)
        return (page, asks) if with_asks else page

    yield opener
    for p in pages:
        p.context.close()


def visible_h1(page):
    return page.evaluate("""() => [...document.querySelectorAll('h1')]
        .filter((h) => h.checkVisibility())
        .map((h) => ({text: h.textContent.trim(), hidden: !!h.closest('[aria-hidden="true"]')}))""")


def assert_screen(page, title):
    expect(page.get_by_role("heading", level=1)).to_have_text(title)
    assert visible_h1(page) == [{"text": title, "hidden": False}]


def assert_focus_on_h1(page, title):
    page.wait_for_function("document.activeElement && document.activeElement.tagName === 'H1'")
    assert page.evaluate("document.activeElement.textContent.trim()") == title


def go_category(page):
    page.get_by_role("link", name="시작하기").click()
    assert_screen(page, CATEGORY_H1)


def test_first_open_shows_landing_even_with_chat_hash(open_page):
    page = open_page("/#chat/washer-lg-fx25")
    assert_screen(page, LANDING_H1)


def test_start_category_model_cards_with_illustrations(open_page):
    page = open_page()
    go_category(page)
    page.get_by_role("button", name="세탁기").click()
    cards = page.locator(".model-card")
    expect(cards).to_have_count(2)
    washer_ids = [m["id"] for m in MODELS if m["appliance"] == "washer"]
    for card, model_id in zip(cards.all(), washer_ids):
        expect(card).to_contain_text(NAMES[model_id])
        img = card.locator("img")
        assert img.get_attribute("src") == f"/images/models/{model_id}.svg"
        expect(img).to_have_js_property("complete", True)
        assert img.evaluate("(i) => i.naturalWidth") > 0
    page.go_back()
    assert_screen(page, CATEGORY_H1)
    page.get_by_role("button", name="에어컨").click()
    expect(cards).to_have_count(1)
    assert cards.locator("img").get_attribute("src") == "/images/models/aircon-lg-sq06fa1wds.svg"


def test_model_card_opens_chat_for_that_model(open_page):
    page = open_page()
    go_category(page)
    page.get_by_role("button", name="에어컨").click()
    page.locator(".model-card").click()
    assert_screen(page, TITLES["aircon-lg-sq06fa1wds"])
    assert page.evaluate("location.hash") == "#chat/aircon-lg-sq06fa1wds"


def test_back_goes_model_category_landing(open_page):
    page = open_page("/#model/washer")
    assert_screen(page, LANDING_H1)
    go_category(page)
    page.get_by_role("button", name="세탁기").click()
    expect(page.locator(".model-card")).to_have_count(2)
    page.go_back()
    assert_screen(page, CATEGORY_H1)
    page.go_back()
    assert_screen(page, LANDING_H1)


def test_each_screen_has_one_h1_and_focus_moves_to_it(open_page):
    page = open_page()
    assert_screen(page, LANDING_H1)
    go_category(page)
    assert_focus_on_h1(page, CATEGORY_H1)
    page.get_by_role("button", name="세탁기").click()
    expect(page.locator(".model-card")).to_have_count(2)
    model_h1 = page.get_by_role("heading", level=1).text_content().strip()
    assert visible_h1(page) == [{"text": model_h1, "hidden": False}]
    assert_focus_on_h1(page, model_h1)
    page.locator(".model-card").first.click()
    assert_screen(page, TITLES["washer-samsung-wd90h25"])
    assert_focus_on_h1(page, TITLES["washer-samsung-wd90h25"])
    page.go_back()
    page.go_back()
    assert_screen(page, CATEGORY_H1)
    assert_focus_on_h1(page, CATEGORY_H1)


def test_category_tiles_arrow_keys_disabled_tile_and_dots(open_page):
    page = open_page()
    go_category(page)
    washer = page.get_by_role("button", name="세탁기")
    aircon = page.get_by_role("button", name="에어컨")
    soon = page.get_by_role("button", name="더 추가 예정")
    expect(page.locator("#tile-dots .dot").first).to_be_visible()
    # 비활성 점은 누르는 버튼이라 흰 바탕과 3:1 이상인 #8C8C8C(가이드 --color-dot)
    inactive = page.locator('#tile-dots .dot[aria-current="false"]').first
    assert inactive.evaluate("(d) => getComputedStyle(d, '::before').backgroundColor") == "rgb(140, 140, 140)"
    # 처음에는 마지막 타일이 반쯤 보인다(폭 360px): 왼쪽 끝은 화면 안, 오른쪽 끝은 화면 밖
    box = soon.bounding_box()
    assert box["x"] < 360 < box["x"] + box["width"]
    washer.focus()
    page.keyboard.press("ArrowRight")
    expect(aircon).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(soon).to_be_focused()
    page.keyboard.press("ArrowLeft")
    expect(aircon).to_be_focused()
    expect(soon).to_have_attribute("aria-disabled", "true")
    soon.click(force=True)  # aria-disabled라 Playwright가 누르기를 막으므로 강제로 누른다
    assert_screen(page, CATEGORY_H1)  # 더 추가 예정은 눌러도 이동하지 않는다


def test_recent_conversation_cards_landing_one_category_three(open_page):
    conversations = [_conversation(i, mid) for i, mid in
                     enumerate(["washer-lg-fx25", "aircon-lg-sq06fa1wds", "washer-lg-fx25", "washer-samsung-wd90h25"], 1)]
    page = open_page(conversations=conversations)
    landing = page.locator("#landing-recent .conv-card")
    expect(landing).to_have_count(1)
    expect(landing).to_contain_text("가짜 질문 4")  # 가장 최근(updated_at) 대화
    expect(landing).to_contain_text(NAMES["washer-samsung-wd90h25"])
    assert landing.get_attribute("href") == "#chat/washer-samsung-wd90h25/c4"
    go_category(page)
    category = page.locator("#category-recent .conv-card")
    expect(category).to_have_count(3)
    expect(category.nth(2)).to_contain_text("가짜 질문 2")


def test_no_recent_section_without_conversations(open_page):
    page = open_page()
    assert_screen(page, LANDING_H1)
    expect(page.locator(".conv-card")).to_have_count(0)
    expect(page.get_by_role("heading", name="최근 대화")).to_have_count(0)


def test_model_cards_have_no_external_links_and_ai_note_only_there(open_page):
    page = open_page()
    expect(page.get_by_text(AI_NOTE)).to_be_hidden()
    go_category(page)
    expect(page.get_by_text(AI_NOTE)).to_be_hidden()
    page.get_by_role("button", name="세탁기").click()
    expect(page.locator(".model-card")).to_have_count(2)
    expect(page.get_by_text(AI_NOTE)).to_be_visible()
    outside = page.evaluate("""() => [...document.querySelectorAll('.model-card a, a.model-card')]
        .filter((a) => new URL(a.href).origin !== location.origin).map((a) => a.href)""")
    assert outside == []


def test_pretendard_fonts_load_from_this_site(open_page):
    page = open_page()
    loaded = page.evaluate("""async () => { await document.fonts.ready;
        return [...document.fonts].filter((f) => f.family.replace(/"/g, '') === 'Pretendard' && f.status === 'loaded')
            .map((f) => f.weight); }""")
    assert set(loaded) == {"400", "600", "700"}  # 랜딩에 쓰는 굵기 세 개(본문·작은 제목과 버튼·큰 제목)


def test_model_codes_on_model_cards_never_split(open_page):
    page = open_page()
    go_category(page)
    page.get_by_role("button", name="세탁기").click()
    expect(page.locator(".model-card")).to_have_count(2)
    codes = page.locator(".model-card .model-code")
    washer_codes = [c for m in MODELS if m["appliance"] == "washer" for c in m["model_codes"]]
    expect(codes).to_have_text(washer_codes)
    for code in codes.all():   # 360px에서 코드 하나가 두 줄로 갈라지지 않는다
        assert code.evaluate("(c) => c.getClientRects().length") == 1, code.text_content()
        assert code.evaluate("(c) => getComputedStyle(c).whiteSpace") == "nowrap"  # 코드에 공백이 생겨도 갈라지지 않게


def test_model_codes_absent_outside_model_screen(open_page):
    conversations = [_conversation(i, mid) for i, mid in
                     enumerate(["washer-lg-fx25", "aircon-lg-sq06fa1wds", "washer-samsung-wd90h25"], 1)]
    page = open_page(conversations=conversations)

    def no_codes(locator):
        expect(locator.first).to_be_visible()
        for text in locator.all_text_contents():
            assert not [c for c in CODES if c in text], text

    no_codes(page.locator("#landing-recent .conv-card"))
    go_category(page)
    no_codes(page.locator("#category-recent .conv-card"))
    page.get_by_role("button", name="세탁기").click()
    page.locator(".model-card").first.click()
    assert_screen(page, TITLES["washer-samsung-wd90h25"])
    for m in MODELS:   # 채팅 위쪽 막대·h1은 세 모델 모두 코드 없음(Task 4 검토)
        open_chat(page, m["id"])
        no_codes(page.locator("#topbar"))
        no_codes(page.get_by_role("heading", level=1))


def test_manual_link_shows_search_codes_as_only_exception(open_page):
    # 2026-11-10 사용자 결정: 내려받기 페이지는 모델 코드로 찾으므로 설명서 링크 옆에만 1차처럼 검색어를 붙인다
    guide = {"doc_type": "guide", "title": "가짜 가이드", "page": None, "url": "https://example.com/guide",
             "quote": "가짜 가이드 인용입니다(테스트)."}
    page = open_page(ask=lambda body, route: fake(body, citations=[CITE, guide]))
    for m in MODELS:
        open_chat(page, m["id"])
        send(page, "가짜 질문입니다")
        wait_turns(page, 1)
        page.locator(".turn").last.get_by_role("button", name="공식 설명서·문서를 드릴까요?").click()
        links = page.locator(".turn").last.locator(".doc-links a")
        expect(links).to_have_text([f"공식 설명서 받기 (검색어: {'·'.join(m['model_codes'])})", "공식 문서 열기: 가짜 가이드"])
        rest = page.evaluate("""() => { const c = document.querySelector('[data-screen="chat"]').cloneNode(true);
            c.querySelectorAll('.doc-links a').forEach((a) => a.remove());
            return document.getElementById('topbar').textContent + c.textContent; }""")
        assert not [c for c in CODES if c in rest], rest   # 예외는 설명서 링크 하나뿐


def test_chat_screen_has_no_footer_note(open_page):
    page = open_page()
    # 랜딩에는 그대로. 서랍(Task 6)에도 같은 문구가 있어 랜딩 안으로 좁힌다
    expect(page.locator('[data-screen="landing"]').get_by_text("비영리 학습용 포트폴리오예요.")).to_be_visible()
    open_chat(page, "washer-lg-fx25")
    expect(page.locator('[data-screen="chat"]').get_by_text("비영리")).to_have_count(0)
    expect(page.get_by_text("비영리").locator("visible=true")).to_have_count(0)


# ── ④ 채팅(설계 2절 ④·5절, 계획 3 Task 5). /api/ask는 가짜 JSON으로만 답한다 ──
FAKE_PHONE = "010-1234-5678"
CITE = {"doc_type": "manual", "title": "가짜 제목", "page": 12, "url": "https://example.com/manual",
        "quote": "가짜 인용입니다(테스트)."}
SUPPORT_URL = "https://example.com/support"


def fake(body, **changes):
    """가짜 정상 응답: 가린 질문은 "가린:" + 질문, 답은 질문마다 다르게."""
    data = {"found": True, "answer": f"가짜 답입니다(테스트): {body['question']}", "citations": [CITE],
            "official_url": SUPPORT_URL, "latency_ms": 1, "pii_masked": False,
            "question_masked": f"가린:{body['question']}", "rewritten_question": None, "reason": None}
    data.update(changes)
    return 200, data


def echo(body, route):
    return fake(body)


def open_chat(page, model_id, conversation_id=None):
    page.evaluate("(h) => { location.hash = h; }", f"#chat/{model_id}" + (f"/{conversation_id}" if conversation_id else ""))
    expect(page.locator("#chat-title")).to_have_text(TITLES[model_id])


def send(page, text):
    page.locator("#question").fill(text)
    page.locator("#question").press("Enter")


def wait_turns(page, n):
    expect(page.locator(".turn")).to_have_count(n)
    expect(page.locator('.turn[data-state="loading"]')).to_have_count(0)


def wait_until(page, check):
    # 가로챈 요청 처리기는 Playwright 호출 사이에 돈다: 잠깐씩 기다리며 조건을 본다
    for _ in range(100):
        if check():
            return
        page.wait_for_timeout(20)
    raise AssertionError("기다린 조건이 오지 않음")


def stored(page):
    return page.evaluate(f"localStorage.getItem({json.dumps(STORE_KEY)})") or ""


def test_topbar_name_fits_one_line_at_360_for_every_model(open_page):
    page = open_page()
    for m in MODELS:   # 모델이 늘어 넘치면 실패해야 한다(말줄임·줄바꿈으로 숨기지 않음)
        open_chat(page, m["id"])
        expect(page.locator("#chat-title")).to_have_text(m.get("short_name") or m["name"])
        # 막대 글자(17px/600)의 Pretendard를 실제로 불러온 뒤 잰다(대체 글꼴로 재지 않게)
        loaded = page.locator("#chat-title").evaluate("""async (h) => { const s = getComputedStyle(h);
            const faces = await document.fonts.load(`${s.fontWeight} ${s.fontSize} Pretendard`);
            return faces.map((f) => [f.family.replace(/"/g, ''), f.weight, f.status]); }""")
        assert loaded == [["Pretendard", "600", "loaded"]], loaded
        expect(page.get_by_role("button", name="새 대화")).to_be_visible()
        box = page.locator("#chat-title").evaluate("""(h) => { const s = getComputedStyle(h);
            return {sw: h.scrollWidth, cw: h.clientWidth, height: h.getBoundingClientRect().height,
                    line: parseFloat(s.lineHeight), overflow: s.textOverflow, space: s.whiteSpace}; }""")
        assert box["overflow"] == "clip" and box["space"] == "normal", box
        assert box["sw"] <= box["cw"] and box["height"] <= box["line"] + 0.5, (m["id"], box)


def test_empty_chat_shows_two_suggestion_cards_that_send(open_page):
    page, asks = open_page(ask=echo, with_asks=True)
    open_chat(page, "washer-lg-fx25")
    cards = page.locator(".suggestion")
    expect(cards).to_have_count(2)
    for card in cards.all():   # 굵은 첫 줄(질문) + 회색 둘째 줄
        expect(card.locator("strong")).not_to_be_empty()
        expect(card.locator(".muted")).not_to_be_empty()
    expect(page.locator("#counter")).to_have_text("500자 남음")
    expect(page.get_by_text("앞 대화를 기억해요 · 모델을 바꾸면 새 대화")).to_be_visible()
    first = cards.first.locator("strong").text_content()
    cards.first.click()
    wait_turns(page, 1)
    assert asks == [{"model_id": "washer-lg-fx25", "question": first}]   # 앞 대화가 없으면 history를 보내지 않음
    expect(page.locator("#suggestions")).to_be_hidden()


def test_pii_bubble_shows_typed_then_masked_and_storage_never_has_number(open_page):
    held = []
    page = open_page(ask=lambda body, route: held.append(route))
    open_chat(page, "washer-samsung-wd90h25")
    typed = f"제 번호는 {FAKE_PHONE}이에요 IE 에러"
    send(page, typed)
    expect(page.locator(".turn .bubble")).to_have_text(typed)   # 기다리는 동안은 입력한 문장
    expect(page.locator('.turn[data-state="loading"]')).to_contain_text("설명서를 펴 보는 중…")
    expect(page.locator("#chat-status")).to_have_text("설명서를 펴 보는 중…")
    wait_until(page, lambda: held)
    held[0].fulfill(json=fake({"question": typed}, question_masked="제 번호는 [전화번호]이에요 IE 에러", pii_masked=True,
                              answer="가짜 답입니다(테스트)")[1])   # 실제 서버 답에는 원래 질문이 들어가지 않는다
    wait_turns(page, 1)
    expect(page.locator(".turn .bubble")).to_have_text("제 번호는 [전화번호]이에요 IE 에러")
    expect(page.locator("#pii-note")).to_be_visible()
    expect(page.locator("#pii-note")).to_contain_text("개인정보 안내")
    assert "[전화번호]" in stored(page) and FAKE_PHONE not in stored(page)
    assert FAKE_PHONE not in page.evaluate("JSON.stringify(Object.entries(localStorage))")


def test_pii_question_with_error_is_not_saved_at_all(open_page):
    page = open_page()   # 기본 가짜 /api/ask는 504
    open_chat(page, "washer-samsung-wd90h25")
    send(page, f"제 번호는 {FAKE_PHONE}이에요 IE 에러")
    expect(page.locator('.turn[data-state="error"]')).to_contain_text("가짜 오류입니다(테스트)")
    assert FAKE_PHONE not in page.evaluate("JSON.stringify(Object.entries(localStorage))")
    assert stored(page) == ""   # 첫 질문에 오류가 오면 대화를 만들지 않는다


def test_history_uses_masked_questions_and_keeps_last_three(open_page):
    page, asks = open_page(ask=echo, with_asks=True)
    open_chat(page, "washer-lg-fx25")
    for i in range(1, 6):
        send(page, f"가짜 질문 {i}")
        wait_turns(page, i)
    assert "history" not in asks[0]
    assert asks[1]["history"] == [{"question": "가린:가짜 질문 1", "answer": "가짜 답입니다(테스트): 가짜 질문 1"}]
    assert [h["question"] for h in asks[4]["history"]] == ["가린:가짜 질문 2", "가린:가짜 질문 3", "가린:가짜 질문 4"]


def test_error_turn_not_in_history_and_retry_resends_same(open_page):
    replies = iter(["ok", "504", "504", "ok"])

    def ask(body, route):
        return fake(body) if next(replies) == "ok" else _ask_504(body, route)

    page, asks = open_page(ask=ask, with_asks=True)
    open_chat(page, "washer-lg-fx25")
    send(page, "가짜 질문 1")
    wait_turns(page, 1)
    send(page, "가짜 질문 2")
    error = page.locator('.turn[data-state="error"]')
    expect(error.locator('[role="alert"]')).to_contain_text("가짜 오류입니다(테스트)")
    error.get_by_role("button", name="다시 시도").click()
    wait_until(page, lambda: len(asks) == 3)
    expect(error.get_by_role("button", name="다시 시도")).to_be_visible()
    assert asks[2] == asks[1]   # 같은 질문·같은 history
    send(page, "가짜 질문 3")
    wait_turns(page, 2)   # 오류 턴은 화면에서도 새 질문으로 바뀐다
    assert asks[3]["history"] == [{"question": "가린:가짜 질문 1", "answer": "가짜 답입니다(테스트): 가짜 질문 1"}]


def test_rewritten_line_only_when_different(open_page):
    def ask(body, route):
        q = body["question"]
        rewritten = {"가짜 질문 2": "  가린:가짜 질문   2 ", "가짜 질문 3": "가짜 바꾼 질문입니다"}.get(q)
        return fake(body, rewritten_question=rewritten)

    page = open_page(ask=ask)
    open_chat(page, "washer-lg-fx25")
    for i in range(1, 4):
        send(page, f"가짜 질문 {i}")
        wait_turns(page, i)
        if i < 3:
            expect(page.get_by_text("로 찾았어요")).to_have_count(0)
    expect(page.locator(".turn").last.locator(".rewritten")).to_have_text("'가짜 바꾼 질문입니다'로 찾았어요")


def test_not_found_and_other_brand_are_distinct_states(open_page):
    def ask(body, route):
        if body["question"] == "가짜 브랜드 질문":
            return fake(body, found=False, citations=[], reason="other_brand", answer="가짜 브랜드 안내입니다(테스트)",
                        official_url="https://example.com/brand")
        return fake(body, found=False, citations=[], answer="가짜 찾지 못함입니다(테스트)")

    page = open_page(ask=ask)
    open_chat(page, "washer-samsung-wd90h25")
    send(page, "가짜 질문입니다")
    wait_turns(page, 1)
    not_found = page.locator('.turn[data-state="not-found"]')
    expect(not_found).to_contain_text("가짜 찾지 못함입니다(테스트)")
    expect(not_found.get_by_role("link", name="공식 고객센터에서 찾아보기")).to_have_attribute("href", SUPPORT_URL)
    send(page, "가짜 브랜드 질문")
    wait_turns(page, 2)
    expect(not_found.get_by_role("button", name="이전 답 · 근거 없음")).to_have_attribute("aria-expanded", "false")
    brand = page.locator('.turn[data-state="other-brand"]')
    expect(brand).to_contain_text("가짜 브랜드 안내입니다(테스트)")   # 서버 답 그대로
    expect(brand.get_by_role("link")).to_have_count(0)   # 고객센터 링크 대신 앱 안 버튼
    expect(brand.locator(".evidence")).to_have_count(0)
    brand.get_by_role("button", name="모델 다시 고르기").click()
    assert_screen(page, CATEGORY_H1)
    assert page.evaluate("location.hash") == "#category"


def test_only_latest_answer_expanded_previous_folded(open_page):
    def ask(body, route):
        return fake(body, citations=[CITE, {**CITE, "page": 13}] if body["question"] == "가짜 질문 1" else [CITE])

    page = open_page(ask=ask)
    open_chat(page, "washer-lg-fx25")
    send(page, "가짜 질문 1")
    wait_turns(page, 1)
    send(page, "가짜 질문 2")
    wait_turns(page, 2)
    first, last = page.locator(".turn").first, page.locator(".turn").last
    expect(last.locator(".answer")).to_be_visible()
    expect(last.locator(".evidence")).to_be_hidden()   # 최신 답도 근거는 접힌 한 줄(2026-11-11 근거 접기)
    last.get_by_role("button", name="근거 보기 · 사용설명서 12쪽").click()
    expect(last.locator(".evidence")).to_be_visible()
    last.get_by_role("button", name="공식 설명서를 드릴까요?").click()
    expect(last.locator(".doc-links a")).to_have_attribute("target", "_blank")
    assert "noopener" in last.locator(".doc-links a").get_attribute("rel")
    fold = first.get_by_role("button", name="이전 답 · 근거 2개")
    expect(fold).to_have_attribute("aria-expanded", "false")
    expect(first.locator(".answer")).to_be_hidden()
    expect(first.locator(".evidence")).to_have_count(2)
    expect(first.locator(".evidence").first).to_be_hidden()
    fold.click()
    expect(fold).to_have_attribute("aria-expanded", "true")
    expect(first.locator(".answer")).to_be_visible()
    expect(first.locator(".evidence").nth(1)).to_be_hidden()   # 이전 답 안에서도 근거는 다시 접힌 한 줄
    first.get_by_role("button", name="근거 보기 · 사용설명서 12·13쪽").click()
    expect(first.locator(".evidence").nth(1)).to_be_visible()


def test_double_enter_while_waiting_sends_once(open_page):
    held = []
    page, asks = open_page(ask=lambda body, route: held.append(route), with_asks=True)
    open_chat(page, "washer-lg-fx25")
    send(page, "가짜 질문입니다")
    expect(page.locator("#send")).to_be_disabled()
    page.locator("#question").fill("가짜 질문입니다")
    page.locator("#question").press("Enter")
    page.locator("#question").press("Enter")
    page.wait_for_timeout(200)
    assert len(asks) == 1 and len(held) == 1
    held[0].fulfill(json=fake(asks[0])[1])
    wait_turns(page, 1)
    expect(page.locator("#send")).to_be_enabled()


def visible_save_notices(page):
    return page.evaluate("""() => [...document.querySelectorAll('body *')].filter((e) =>
        e.childElementCount === 0 && e.textContent.includes('이 대화는 저장되지 않아요') && e.checkVisibility()).length""")


def test_save_failure_notice_once_and_answers_still_shown(open_page):
    init = "Storage.prototype.setItem = function () { throw new DOMException('가짜 공간 부족', 'QuotaExceededError'); };"
    page = open_page(ask=echo, init=init)
    open_chat(page, "washer-lg-fx25")
    assert visible_save_notices(page) == 0   # 저장에 실패하기 전에는 없다
    send(page, "가짜 질문 1")
    wait_turns(page, 1)
    assert visible_save_notices(page) == 1
    send(page, "가짜 질문 2")
    wait_turns(page, 2)
    expect(page.locator('.turn[data-state="answer"]')).to_have_count(2)   # 답은 그대로 보인다
    assert visible_save_notices(page) == 1   # 같은 대화에서 두 번 실패해도 안내는 하나
    page.get_by_role("button", name="새 대화").click()
    expect(page.locator(".turn")).to_have_count(0)
    assert visible_save_notices(page) == 0   # 새 대화에서는 꺼진다
    send(page, "가짜 질문 3")
    wait_turns(page, 1)
    assert visible_save_notices(page) == 1   # 새 대화에서 실패하면 다시 한 번


def go_lg_washer_chat(page):
    go_category(page)
    page.get_by_role("button", name="세탁기").click()
    page.locator(".model-card").nth(1).click()   # LG 드럼세탁기
    expect(page.locator("#chat-title")).to_have_text(TITLES["washer-lg-fx25"])


def saved_conversations(page):
    return json.loads(stored(page) or '{"conversations": []}')["conversations"]


def test_answer_arriving_on_other_screen_is_saved_without_changing_screen(open_page):
    held = []
    page, asks = open_page(ask=lambda body, route: held.append(route), with_asks=True)
    go_lg_washer_chat(page)
    send(page, "가짜 질문 1")
    wait_until(page, lambda: held)
    page.go_back()   # 답을 기다리는 동안 모델 화면으로
    expect(page.locator(".model-card")).to_have_count(2)
    held[0].fulfill(json=fake(asks[0])[1])
    page.wait_for_function(f"localStorage.getItem({json.dumps(STORE_KEY)}) !== null")
    assert page.evaluate("location.hash") == "#model/washer"   # 지금 화면과 주소는 그대로
    expect(page.locator(".model-card")).to_have_count(2)
    saved = saved_conversations(page)
    assert [t["question_masked"] for t in saved[0]["turns"]] == ["가린:가짜 질문 1"]
    page.go_back()   # 카테고리 화면의 최근 대화 카드로 그 대화를 연다
    assert_screen(page, CATEGORY_H1)
    page.locator("#category-recent .conv-card").first.click()
    wait_turns(page, 1)
    expect(page.locator(".turn .bubble")).to_have_text("가린:가짜 질문 1")
    expect(page.locator(".turn .answer")).to_have_text("가짜 답입니다(테스트): 가짜 질문 1")
    assert page.evaluate("location.hash") == f"#chat/washer-lg-fx25/{saved[0]['id']}"


def test_same_model_card_again_opens_new_chat(open_page):
    page = open_page(ask=echo)
    go_lg_washer_chat(page)
    send(page, "가짜 질문 1")
    wait_turns(page, 1)
    page.go_back()
    expect(page.locator(".model-card")).to_have_count(2)
    page.locator(".model-card").nth(1).click()   # 같은 모델을 다시 고르면 새 대화
    expect(page.locator("#chat-title")).to_have_text(TITLES["washer-lg-fx25"])
    expect(page.locator(".turn")).to_have_count(0)
    expect(page.locator("#suggestions")).to_be_visible()
    assert page.evaluate("location.hash") == "#chat/washer-lg-fx25"


def test_answer_after_reopening_same_model_goes_to_original_conversation(open_page):
    held = []

    def ask(body, route):   # 첫 질문의 답만 붙잡아 둔다
        if held:
            return fake(body)
        held.append(route)

    page, asks = open_page(ask=ask, with_asks=True)
    go_lg_washer_chat(page)
    send(page, "가짜 질문 1")
    wait_until(page, lambda: held)
    page.go_back()
    page.locator(".model-card").nth(1).click()   # 기다리는 중에 같은 모델로 새 대화
    expect(page.locator("#suggestions")).to_be_visible()
    expect(page.locator("#send")).to_be_enabled()
    held[0].fulfill(json=fake(asks[0])[1])
    page.wait_for_function(f"localStorage.getItem({json.dumps(STORE_KEY)}) !== null")
    saved = saved_conversations(page)
    assert len(saved) == 1 and [t["question_masked"] for t in saved[0]["turns"]] == ["가린:가짜 질문 1"]
    expect(page.locator(".turn")).to_have_count(0)   # 새 대화 화면에는 나타나지 않는다
    expect(page.locator("#suggestions")).to_be_visible()
    assert page.evaluate("location.hash") == "#chat/washer-lg-fx25"
    send(page, "가짜 질문 2")   # 새 대화는 앞 대화 없이 따로 저장된다
    wait_turns(page, 1)
    assert "history" not in asks[1]
    assert len(saved_conversations(page)) == 2


def test_late_answer_kept_when_same_conversation_reopened_and_continued(open_page):
    held = []

    def ask(body, route):   # 두 번째 질문의 답만 붙잡아 둔다
        if body["question"] == "가짜 질문 2":
            held.append(route)
            return None
        return fake(body)

    page, asks = open_page(ask=ask, conversations=[_conversation(1, "washer-lg-fx25")], with_asks=True)
    open_chat(page, "washer-lg-fx25", "c1")
    send(page, "가짜 질문 2")
    wait_until(page, lambda: held)
    open_chat(page, "aircon-lg-sq06fa1wds")   # 다른 화면(다른 모델 대화)으로 갔다가
    page.evaluate("location.hash = '#category'")
    assert_screen(page, CATEGORY_H1)
    page.locator("#category-recent .conv-card").first.click()   # 최근 대화 카드로 같은 대화를 다시 연다
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 1"])
    held[0].fulfill(json=fake(asks[0])[1])
    # 늦게 온 답은 원래 대화에 저장되고, 지금 같은 대화를 보고 있으므로 화면에도 나타난다
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 1", "가린:가짜 질문 2"])
    send(page, "가짜 질문 3")
    wait_turns(page, 3)
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 1", "가린:가짜 질문 2", "가린:가짜 질문 3"])
    assert [h["question"] for h in asks[1]["history"]] == ["가짜 질문 1", "가린:가짜 질문 2"]
    saved = {c["id"]: c for c in json.loads(stored(page))["conversations"]}
    assert [t["question_masked"] for t in saved["c1"]["turns"]] == ["가짜 질문 1", "가린:가짜 질문 2", "가린:가짜 질문 3"]


def test_turn_kept_when_one_save_failed_in_between(open_page):
    # 두 번째 저장만 실패(공간 부족 등): 저장소 사본(턴 1)이 메모리(턴 1·2)보다 오래됐으므로 메모리 쪽에 이어 붙인다
    init = """(() => { let n = 0; const orig = Storage.prototype.setItem;
        Storage.prototype.setItem = function (k, v) { n += 1; if (n === 2) throw new DOMException('가짜', 'QuotaExceededError');
            return orig.call(this, k, v); }; })();"""
    page = open_page(ask=echo, init=init)
    open_chat(page, "washer-lg-fx25")
    for i in range(1, 4):
        send(page, f"가짜 질문 {i}")
        wait_turns(page, i)
    expect(page.locator(".turn .bubble")).to_have_text([f"가린:가짜 질문 {i}" for i in range(1, 4)])
    turns = json.loads(stored(page))["conversations"][0]["turns"]
    assert [t["question_masked"] for t in turns] == [f"가린:가짜 질문 {i}" for i in range(1, 4)]


def test_malformed_stored_turn_still_renders_and_can_ask(open_page):
    bad = _conversation(9, "washer-lg-fx25")
    bad["turns"] = [{"question_masked": "가짜 질문 9", "rewritten_question": 5, "answer": "가짜 답", "found": True,
                     "citations": [None, "가짜", CITE], "kind": "answer"}]
    page, asks = open_page(ask=echo, conversations=[_conversation(1, "washer-lg-fx25"), bad], with_asks=True)
    open_chat(page, "washer-lg-fx25", "c1")   # 먼저 다른 대화를 연 뒤
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 1"])
    open_chat(page, "washer-lg-fx25", "c9")   # 망가진 턴이 든 대화로
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 9"])
    expect(page.locator(".turn .evidence")).to_have_count(1)   # 객체가 아닌 근거는 버린다
    expect(page.locator(".turn .rewritten")).to_have_count(0)   # 문자열이 아닌 바꾼 질문은 없는 것으로
    send(page, "가짜 질문입니다")
    wait_turns(page, 2)
    expect(page.locator("#send")).to_be_enabled()
    assert asks[0]["history"] == [{"question": "가짜 질문 9", "answer": "가짜 답"}]


def test_conversation_saved_then_reopened_continues_with_its_history(open_page):
    page, asks = open_page(ask=echo, with_asks=True)
    open_chat(page, "washer-lg-fx25")
    send(page, "가짜 질문 1")
    wait_turns(page, 1)
    saved = json.loads(stored(page))["conversations"]
    assert len(saved) == 1 and saved[0]["model_id"] == "washer-lg-fx25" and saved[0]["title"] == "가린:가짜 질문 1"
    assert saved[0]["turns"][0] == {"question_masked": "가린:가짜 질문 1", "rewritten_question": None,
                                    "answer": "가짜 답입니다(테스트): 가짜 질문 1", "found": True,
                                    "citations": [CITE], "kind": "answer"}
    assert page.evaluate("location.hash") == f"#chat/washer-lg-fx25/{saved[0]['id']}"
    page.get_by_role("button", name="새 대화").click()
    expect(page.locator(".turn")).to_have_count(0)
    assert page.evaluate("location.hash") == "#chat/washer-lg-fx25"
    page.go_back()   # 새 대화에서 뒤로 가면 앞 대화로 돌아간다
    expect(page.locator(".turn .bubble")).to_have_text(["가린:가짜 질문 1"])
    page.go_forward()   # 대화 id 없는 주소는 새 대화
    expect(page.locator(".turn")).to_have_count(0)
    expect(page.locator("#suggestions .suggestion")).to_have_count(2)
    expect(page.locator("#suggestions")).to_be_visible()
    send(page, "가짜 질문 2")
    wait_turns(page, 1)
    assert "history" not in asks[1]   # 새 대화는 앞 대화를 비운다
    open_chat(page, "washer-lg-fx25", saved[0]["id"])
    expect(page.locator(".turn .bubble")).to_have_text(["가린:가짜 질문 1"])
    send(page, "가짜 질문 3")
    wait_turns(page, 2)
    assert asks[2]["history"] == [{"question": "가린:가짜 질문 1", "answer": "가짜 답입니다(테스트): 가짜 질문 1"}]
    assert len(json.loads(stored(page))["conversations"]) == 2


def test_conversation_of_other_model_or_unknown_id_opens_new_chat(open_page):
    page, asks = open_page(ask=echo, conversations=[_conversation(1, "washer-lg-fx25")], with_asks=True)
    open_chat(page, "aircon-lg-sq06fa1wds", "c1")   # 주소의 모델과 대화의 모델이 다름
    expect(page.locator("#suggestions .suggestion")).to_have_count(2)
    expect(page.locator("#suggestions")).to_be_visible()
    expect(page.locator(".turn")).to_have_count(0)
    open_chat(page, "washer-lg-fx25", "없는-대화")
    expect(page.locator("#suggestions .suggestion")).to_have_count(2)
    expect(page.locator("#suggestions")).to_be_visible()
    expect(page.locator(".turn")).to_have_count(0)
    send(page, "가짜 질문입니다")
    wait_turns(page, 1)
    assert "history" not in asks[0]


# ── ⑤ 지난 대화 서랍(설계 2절 ⑤, 계획 3 Task 6) ──
STORE_NOTE = "대화는 이 기기에만 저장돼요. 공용 기기라면 다 쓴 뒤 지워 주세요."
FOOTER_NOTE = "비영리 학습용 포트폴리오예요. 설명서 저작권은 각 제조사에 있어요."


def open_drawer(page):
    page.get_by_role("button", name="지난 대화").click()
    expect(page.locator("#drawer")).to_be_visible()
    return page.locator("#drawer")


def drawer_cards(page):
    return page.locator("#drawer .conv-card")


def delete_button(page, title):
    return page.get_by_role("button", name=f"'{title}' 대화 지우기")


def stored_ids(page):
    return [c["id"] for c in saved_conversations(page)]


def test_drawer_opens_from_menu_on_topbar_screens_modal_and_esc_returns_focus(open_page):
    page = open_page()
    expect(page.get_by_role("button", name="지난 대화")).to_have_count(0)   # 랜딩은 위쪽 막대가 없어 서랍 버튼도 없다
    go_category(page)
    menu = page.get_by_role("button", name="지난 대화")
    expect(menu).not_to_have_attribute("aria-disabled", "true")
    drawer = open_drawer(page)
    assert drawer.evaluate("(d) => d.matches(':modal')")   # showModal: 바깥은 누를 수도 포커스할 수도 없다
    expect(page.get_by_role("dialog", name="지난 대화")).to_be_visible()
    for _ in range(6):   # Tab이 서랍 밖 화면 요소로 가지 않는다(끝에서는 브라우저 UI를 거쳐 서랍으로 돌아온다)
        page.keyboard.press("Tab")
        assert page.evaluate("![...document.querySelectorAll('header, main')].some((e) => e.contains(document.activeElement))")
    page.keyboard.press("Escape")
    expect(drawer).to_be_hidden()
    expect(menu).to_be_focused()
    page.get_by_role("button", name="세탁기").click()
    expect(page.locator(".model-card")).to_have_count(2)
    open_drawer(page)   # 모델 화면에서도
    page.keyboard.press("Escape")
    open_chat(page, "washer-lg-fx25")
    open_drawer(page)   # 채팅 화면에서도
    page.get_by_role("button", name="닫기").click()
    expect(page.locator("#drawer")).to_be_hidden()
    expect(menu).to_be_focused()


def test_drawer_has_store_note_and_footer_note_at_bottom(open_page):
    page = open_page()
    go_category(page)
    drawer = open_drawer(page)
    expect(drawer.get_by_text(STORE_NOTE)).to_be_visible()
    expect(drawer.get_by_text("저장된 대화가 없어요")).to_be_visible()   # 빈 서랍
    expect(drawer.get_by_role("link", name="새 대화")).to_be_visible()
    expect(drawer.get_by_role("button", name="전체 삭제")).to_be_hidden()   # 지울 대화가 없으면 숨긴다
    footer = drawer.get_by_text(FOOTER_NOTE)
    expect(footer).to_be_visible()
    # 하단 고지는 서랍 맨 아래: 고지를 감싸지 않는 서랍 안 보이는 요소는 모두 고지 위에서 끝난다
    above = footer.evaluate("""(f) => [...document.querySelectorAll('#drawer *')]
        .filter((e) => e.checkVisibility() && !e.contains(f) && !f.contains(e))
        .map((e) => e.getBoundingClientRect().bottom <= f.getBoundingClientRect().top)""")
    assert above and all(above), above


def test_drawer_cards_title_name_date_newest_first_without_codes(open_page):
    conversations = [_conversation(i, mid) for i, mid in
                     enumerate(["washer-lg-fx25", "aircon-lg-sq06fa1wds", "washer-samsung-wd90h25", "없는-모델"], 1)]
    page = open_page(conversations=conversations)
    go_category(page)
    open_drawer(page)
    cards = drawer_cards(page)
    expect(cards).to_have_count(3)   # 목록에 없는 모델의 대화는 보이지 않는다(깨진 링크 방지)
    expect(cards.locator(".card-title")).to_have_text(["가짜 질문 3", "가짜 질문 2", "가짜 질문 1"])   # updated_at 최신순
    expect(cards.locator(".card-meta")).to_have_text([f"{NAMES['washer-samsung-wd90h25']} · 11월 3일",
                                                      f"{NAMES['aircon-lg-sq06fa1wds']} · 11월 2일",
                                                      f"{NAMES['washer-lg-fx25']} · 11월 1일"])
    for text in cards.all_text_contents():
        assert not [c for c in CODES if c in text], text   # 모델 코드 없음, 이름은 name
    assert cards.first.get_attribute("href") == "#chat/washer-samsung-wd90h25/c3"
    box = delete_button(page, "가짜 질문 3").bounding_box()
    assert box["width"] >= 44 and box["height"] >= 44


def test_drawer_conversation_of_other_model_continues_with_its_own_history(open_page):
    # 계획 Review Focus 3: 모델 A 채팅 중 서랍에서 모델 B 대화를 열고 물으면 B의 모델·B의 앞 대화만 간다
    b = _conversation(1, "aircon-lg-sq06fa1wds")
    b["turns"].append({**b["turns"][0], "question_masked": "가짜 질문 1-2", "answer": "가짜 답 2"})
    page, asks = open_page(ask=echo, conversations=[b], with_asks=True)
    open_chat(page, "washer-lg-fx25")
    send(page, "가짜 A 질문")
    wait_turns(page, 1)
    open_drawer(page)
    drawer_cards(page).filter(has_text="가짜 질문 1").click()
    expect(page.locator("#drawer")).to_be_hidden()
    expect(page.locator("#chat-title")).to_have_text(TITLES["aircon-lg-sq06fa1wds"])
    assert page.evaluate("location.hash") == "#chat/aircon-lg-sq06fa1wds/c1"
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 1", "가짜 질문 1-2"])
    send(page, "가짜 B 질문")
    wait_turns(page, 3)
    assert asks[1]["model_id"] == "aircon-lg-sq06fa1wds"
    assert asks[1]["history"] == [{"question": "가짜 질문 1", "answer": "가짜 답"},
                                  {"question": "가짜 질문 1-2", "answer": "가짜 답 2"}]


def test_drawer_new_chat_goes_to_category(open_page):
    page = open_page()
    open_chat(page, "washer-lg-fx25")
    open_drawer(page).get_by_role("link", name="새 대화").click()
    expect(page.locator("#drawer")).to_be_hidden()
    assert_screen(page, CATEGORY_H1)
    assert page.evaluate("location.hash") == "#category"


def test_drawer_delete_one_updates_list_storage_recent_and_focus(open_page):
    conversations = [_conversation(i, "washer-lg-fx25") for i in range(1, 4)]
    page = open_page(conversations=conversations)
    go_category(page)
    expect(page.locator("#category-recent .conv-card")).to_have_count(3)
    open_drawer(page)
    delete_button(page, "가짜 질문 2").click()   # 바로 지운다(전체 삭제만 한 번 더 확인)
    expect(drawer_cards(page).locator(".card-title")).to_have_text(["가짜 질문 3", "가짜 질문 1"])
    assert stored_ids(page) == ["c3", "c1"]
    expect(delete_button(page, "가짜 질문 1")).to_be_focused()   # 다음 카드의 삭제 버튼
    delete_button(page, "가짜 질문 1").click()
    expect(delete_button(page, "가짜 질문 3")).to_be_focused()   # 다음이 없으면 이전 것
    delete_button(page, "가짜 질문 3").click()
    expect(page.locator("#drawer").get_by_text("저장된 대화가 없어요")).to_be_visible()
    expect(page.locator("#drawer-title")).to_be_focused()   # 목록이 비면 서랍 제목
    assert stored_ids(page) == []
    page.keyboard.press("Escape")
    expect(page.locator("#category-recent .conv-card")).to_have_count(0)   # 뒤 화면의 최근 대화 카드도 남지 않는다
    page.go_back()
    assert_screen(page, LANDING_H1)
    expect(page.locator(".conv-card").locator("visible=true")).to_have_count(0)


def test_drawer_delete_all_needs_in_page_confirm(open_page):
    page = open_page(conversations=[_conversation(i, "washer-lg-fx25") for i in range(1, 4)])
    native = []
    page.on("dialog", lambda d: (native.append(d.type), d.dismiss()))   # 브라우저 기본 confirm 창을 쓰지 않는다
    go_category(page)
    drawer = open_drawer(page)
    drawer.get_by_role("button", name="전체 삭제").click()
    expect(drawer.get_by_text("대화 3개를 모두 지울까요?")).to_be_visible()
    expect(drawer.get_by_role("button", name="취소")).to_be_focused()
    drawer.get_by_role("button", name="취소").click()
    expect(drawer.get_by_text("대화 3개를 모두 지울까요?")).to_be_hidden()
    expect(drawer.get_by_role("button", name="전체 삭제")).to_be_focused()
    expect(drawer_cards(page)).to_have_count(3)
    assert sorted(stored_ids(page)) == ["c1", "c2", "c3"]   # 저장소 원본 순서는 넣은 순서 그대로
    drawer.get_by_role("button", name="전체 삭제").click()
    drawer.get_by_role("button", name="모두 지우기").click()
    expect(drawer_cards(page)).to_have_count(0)
    expect(drawer.get_by_text("저장된 대화가 없어요")).to_be_visible()
    expect(page.locator("#drawer-title")).to_be_focused()
    assert stored_ids(page) == [] and native == []


def test_deleting_open_conversation_shows_new_chat_other_keeps_screen(open_page):
    conversations = [_conversation(i, "washer-lg-fx25") for i in range(1, 3)]
    page = open_page(conversations=conversations)
    open_chat(page, "washer-lg-fx25", "c1")
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 1"])
    open_drawer(page)
    delete_button(page, "가짜 질문 2").click()   # 다른 대화를 지우면 지금 화면은 그대로
    page.keyboard.press("Escape")
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 1"])
    assert page.evaluate("location.hash") == "#chat/washer-lg-fx25/c1"
    open_drawer(page)
    delete_button(page, "가짜 질문 1").click()   # 보고 있는 대화를 지우면 그 모델의 새 대화
    page.keyboard.press("Escape")
    expect(page.locator(".turn")).to_have_count(0)
    expect(page.locator("#suggestions")).to_be_visible()
    expect(page.locator("#chat-title")).to_have_text(TITLES["washer-lg-fx25"])
    assert page.evaluate("location.hash") == "#chat/washer-lg-fx25"


def test_delete_all_while_viewing_conversation_shows_new_chat(open_page):
    page = open_page(conversations=[_conversation(1, "aircon-lg-sq06fa1wds")])
    open_chat(page, "aircon-lg-sq06fa1wds", "c1")
    expect(page.locator(".turn")).to_have_count(1)
    drawer = open_drawer(page)
    drawer.get_by_role("button", name="전체 삭제").click()
    drawer.get_by_role("button", name="모두 지우기").click()
    page.keyboard.press("Escape")
    expect(page.locator(".turn")).to_have_count(0)
    assert page.evaluate("location.hash") == "#chat/aircon-lg-sq06fa1wds"


def test_delete_failure_shows_line_and_keeps_list(open_page):
    # 저장소 쓰기가 실패하면(deleteConversation이 false) 목록을 그대로 두고 한 줄 안내
    init = "Storage.prototype.setItem = function () { throw new DOMException('가짜 공간 부족', 'QuotaExceededError'); };"
    page = open_page(conversations=[_conversation(i, "washer-lg-fx25") for i in range(1, 3)], init=init)
    go_category(page)
    drawer = open_drawer(page)
    delete_button(page, "가짜 질문 2").click()
    expect(drawer.get_by_text("지우지 못했어요")).to_be_visible()
    expect(drawer_cards(page)).to_have_count(2)
    expect(drawer.locator(".error-card")).to_have_count(0)   # 오류 카드가 아니라 한 줄
    drawer.get_by_role("button", name="전체 삭제").click()
    drawer.get_by_role("button", name="모두 지우기").click()
    expect(drawer.get_by_text("지우지 못했어요")).to_be_visible()
    expect(drawer_cards(page)).to_have_count(2)
    assert sorted(stored_ids(page)) == ["c1", "c2"]


# 화면이 /api/ask 응답 본문을 다 읽은 횟수(window.__askBodiesRead). 읽은 뒤의 처리는 기다림 없이 이어진다
ASK_BODIES_READ = """(() => { const json = Response.prototype.json; window.__askBodiesRead = 0;
    Response.prototype.json = async function () {
        try { return await json.call(this); } finally { if (this.url.endsWith('/api/ask')) window.__askBodiesRead += 1; } }; })();"""


def test_deleted_conversation_not_resurrected_by_late_answer(open_page):
    # Task 5 검토: 답을 기다리는 동안 서랍에서 그 대화를 지우면, 늦게 온 답이 대화를 되살리지 않는다
    held = []

    def ask(body, route):
        if body["question"] == "가짜 질문 2":
            held.append(route)
            return None
        return fake(body)

    page, asks = open_page(ask=ask, with_asks=True, init=ASK_BODIES_READ)
    open_chat(page, "washer-lg-fx25")
    send(page, "가짜 질문 1")
    wait_turns(page, 1)
    send(page, "가짜 질문 2")
    wait_until(page, lambda: held)
    open_drawer(page)
    delete_button(page, "가린:가짜 질문 1").click()
    page.keyboard.press("Escape")
    expect(page.locator(".turn")).to_have_count(0)   # 보고 있던 대화를 지웠으므로 그 모델의 새 대화
    assert page.evaluate("location.hash") == "#chat/washer-lg-fx25"
    held[0].fulfill(json=fake(asks[1])[1])
    # 고정 대기 대신 양의 신호: 화면이 늦은 답의 본문을 다 읽었다(그 뒤 저장 처리는 같은 흐름에서 바로 끝난다)
    page.wait_for_function("window.__askBodiesRead === 2")
    assert saved_conversations(page) == []
    expect(page.locator(".turn")).to_have_count(0)


# ── Task 7: 동작 줄이기·아래 안내 줄 위치·서랍 포커스 ──
def moving_elements(page):
    """0보다 긴 transition·animation이 남은 요소(::before·::after 포함)."""
    return page.evaluate("""() => [...document.querySelectorAll('*')].flatMap((e) => [null, '::before', '::after'].map((p) => {
        const s = getComputedStyle(e, p);
        const long = (v) => v.split(',').some((d) => parseFloat(d) > 0);
        const moving = long(s.transitionDuration) || (s.animationName !== 'none' && long(s.animationDuration));
        return moving ? `${e.tagName.toLowerCase()}#${e.id}.${e.className}${p ?? ''}` : null;
    })).filter(Boolean)""")


def test_reduced_motion_turns_off_drawer_tiles_and_fold_motion(open_page):
    held = []

    def ask(body, route):   # 세 번째 답은 붙잡아 찾는 중(진행 막대)을 남긴다
        if body["question"] == "가짜 질문 3":
            held.append(route)
            return None
        return fake(body)

    page = open_page(ask=ask)
    open_chat(page, "washer-lg-fx25")
    for i in (1, 2):
        send(page, f"가짜 질문 {i}")
        wait_turns(page, i)
    send(page, "가짜 질문 3")
    wait_until(page, lambda: held)
    expect(page.get_by_role("button", name="이전 답 · 근거 1개")).to_have_count(2)
    open_drawer(page)
    styles = """() => ({drawer: getComputedStyle(document.getElementById('drawer')).animationName,
        fold: getComputedStyle(document.querySelector('.fold .icon')).transitionDuration,
        tiles: getComputedStyle(document.getElementById('tiles')).scrollBehavior,
        suggestions: getComputedStyle(document.getElementById('suggestions')).scrollBehavior})"""
    # 기준: 동작 줄이기가 아니면 서랍은 밀려 나오고, 펼침 화살표는 돌고, 타일은 부드럽게 넘어간다(같은 요소를 보는지 확인)
    assert page.evaluate(styles) == {"drawer": "drawer-in", "fold": "0.25s", "tiles": "smooth", "suggestions": "smooth"}
    assert moving_elements(page)
    page.emulate_media(reduced_motion="reduce")
    assert page.evaluate(styles) == {"drawer": "none", "fold": "0s", "tiles": "auto", "suggestions": "auto"}
    assert moving_elements(page) == []   # 버튼 색·진행 막대까지 움직임이 하나도 남지 않는다
    held[0].fulfill(json=fake({"question": "가짜 질문 3"})[1])   # 붙잡은 요청을 남기지 않고 닫는다
    wait_turns(page, 3)


def test_composer_meta_line_stays_put_when_answer_arrives(open_page):
    # 1차 CLS 0.080의 원인은 답이 오며 밀린 하단 고지였다. 채팅에는 하단 고지가 없으므로 입력창 아래 안내 줄을 본다
    held = []
    page = open_page(ask=lambda body, route: held.append(route))
    open_chat(page, "washer-lg-fx25")
    page.evaluate("async () => { await document.fonts.ready; }")
    meta = page.locator(".composer-meta")
    expect(meta).to_contain_text("앞 대화를 기억해요 · 모델을 바꾸면 새 대화")

    def top():
        return meta.evaluate("(m) => m.getBoundingClientRect().top")

    before = top()
    for i in (1, 2, 3):   # 첫 답, 이어지는 답(이전 답 접힘), 화면보다 길어진 대화
        send(page, f"가짜 질문 {i}")
        wait_until(page, lambda: len(held) == i)
        expect(page.locator('.turn[data-state="loading"]')).to_have_count(1)
        assert abs(top() - before) < 0.5, ("찾는 중", i, top(), before)
        held[-1].fulfill(json=fake({"question": f"가짜 질문 {i}"})[1])
        wait_turns(page, i)
        assert abs(top() - before) < 0.5, ("답", i, top(), before)


def test_drawer_card_of_open_conversation_moves_focus_to_chat_h1(open_page):
    page = open_page(conversations=[_conversation(i, "washer-lg-fx25") for i in (1, 2)])
    open_chat(page, "washer-lg-fx25", "c1")
    open_drawer(page)
    drawer_cards(page).filter(has_text="가짜 질문 1").click()   # 지금 보고 있는 대화(주소가 같아 hashchange가 없다)
    expect(page.locator("#drawer")).to_be_hidden()
    expect(page.locator("#chat-title")).to_be_focused()
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 1"])
    open_drawer(page)
    drawer_cards(page).filter(has_text="가짜 질문 2").click()   # 다른 대화 카드도 같은 곳
    expect(page.locator(".turn .bubble")).to_have_text(["가짜 질문 2"])
    expect(page.locator("#chat-title")).to_be_focused()
    open_drawer(page)
    page.keyboard.press("Escape")   # 카드를 누르지 않고 닫으면 ☰로
    expect(page.get_by_role("button", name="지난 대화")).to_be_focused()


# ── Task 8 Step 7 화면 확인에서 고친 것(2026-11-11 사용자 결정, 결정기록 024) ──
def tile_layout(page):
    return page.evaluate("""() => { const t = document.getElementById('tiles');
        return {sw: t.scrollWidth, cw: t.clientWidth,
                widths: [...t.querySelectorAll('.tile')].map((e) => e.getBoundingClientRect().width)}; }""")


def test_tiles_fixed_width_fit_on_pc_without_dots_and_scroll_with_dots_on_phone(open_page):
    page = open_page()
    go_category(page)
    phone = tile_layout(page)   # 360px: 넘기기 + 점
    assert phone["sw"] > phone["cw"] and phone["widths"] == [128, 128, 128], phone
    expect(page.locator("#tile-dots .dot").first).to_be_visible()
    page.set_viewport_size({"width": 1280, "height": 800})   # PC(내용 폭 640px): 3개가 다 보이고 점은 숨김
    expect(page.locator("#tile-dots")).to_be_hidden()
    pc = tile_layout(page)
    assert pc["sw"] <= pc["cw"] and pc["widths"] == [128, 128, 128], pc


def test_long_tile_name_wraps_inside_tile_without_breaking_words(open_page):
    page = open_page()
    go_category(page)
    result = page.evaluate("""() => {
        const tile = document.querySelector('.tile[aria-disabled="true"]');
        const text = [...tile.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
        text.textContent = '이름이 아주 긴 가전 종류 예시';   // 화면에서만 바꾸는 예시 문구
        const r = document.createRange(); let from = 0;
        const words = text.textContent.split(' ').map((w) => {
            const at = text.textContent.indexOf(w, from); from = at + w.length;
            r.setStart(text, at); r.setEnd(text, at + w.length);
            return new Set([...r.getClientRects()].map((x) => Math.round(x.top))).size; });
        r.selectNodeContents(text);
        const lines = new Set([...r.getClientRects()].map((x) => Math.round(x.top))).size;
        const boxes = [...document.querySelectorAll('.tile')].map((e) => e.getBoundingClientRect());
        return {words, lines, sw: tile.scrollWidth, cw: tile.clientWidth,
                width: boxes[2].width, heights: boxes.map((b) => Math.round(b.height))}; }""")
    assert result["lines"] > 1 and set(result["words"]) == {1}, result   # 줄은 바뀌되 단어 중간에서 끊지 않는다
    assert result["sw"] <= result["cw"] and result["width"] == 128, result   # 칸 밖으로 넘치지 않는다
    assert len(set(result["heights"])) == 1, result   # 같은 줄 타일 높이는 같다


def wheel_over(page, selector, dy):
    box = page.locator(selector).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, dy)


def scrolled(page, selector):
    return page.evaluate("(s) => ({left: document.querySelector(s).scrollLeft, y: window.scrollY})", selector)


def test_vertical_wheel_scrolls_row_sideways_then_page_at_end_or_when_it_fits(open_page):
    page = open_page(conversations=[_conversation(i, "washer-lg-fx25") for i in (1, 2, 3)])
    page.set_viewport_size({"width": 360, "height": 400})   # 화면도 위아래로 스크롤되는 높이
    go_category(page)
    wheel_over(page, "#tiles", 40)   # 넘칠 때: 세로 휠 → 가로 이동, 화면은 그대로
    wait_until(page, lambda: scrolled(page, "#tiles")["left"] > 0)
    assert scrolled(page, "#tiles")["y"] == 0
    page.evaluate("() => { const t = document.getElementById('tiles'); t.scrollTo({left: t.scrollWidth, behavior: 'instant'}); }")
    end = scrolled(page, "#tiles")["left"]
    wheel_over(page, "#tiles", 40)   # 오른쪽 끝: 휠이 갇히지 않고 화면이 내려간다
    wait_until(page, lambda: scrolled(page, "#tiles")["y"] > 0)
    assert scrolled(page, "#tiles")["left"] == end
    page.set_viewport_size({"width": 1280, "height": 300})   # 안 넘칠 때: 화면 스크롤
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    wheel_over(page, "#tiles", 40)
    wait_until(page, lambda: scrolled(page, "#tiles")["y"] > 0)
    assert scrolled(page, "#tiles")["left"] == 0
    page.set_viewport_size({"width": 360, "height": 640})   # 추천 카드도 같은 규칙
    open_chat(page, "washer-samsung-wd90h25")
    wheel_over(page, "#suggestions", 40)
    wait_until(page, lambda: scrolled(page, "#suggestions")["left"] > 0)


def test_suggestion_cards_fit_text_up_to_max_width(open_page):
    page = open_page()
    page.set_viewport_size({"width": 1280, "height": 800})
    open_chat(page, "washer-lg-fx25")
    widths = page.locator(".suggestion").evaluate_all("(cs) => cs.map((c) => c.getBoundingClientRect().width)")
    assert len(widths) == 2 and all(w <= 272 for w in widths), widths
    box = page.evaluate("() => { const s = document.getElementById('suggestions'); return [s.scrollWidth, s.clientWidth]; }")
    assert box[0] <= box[1], box   # PC에서는 두 장이 다 보인다


@pytest.mark.parametrize("size", [(360, 640), (1280, 800)])
def test_short_chat_has_no_vertical_scroll_and_new_chat_button_is_tap_min(open_page, size):
    page = open_page()
    page.set_viewport_size({"width": size[0], "height": size[1]})
    open_chat(page, "washer-lg-fx25")
    expect(page.locator(".suggestion")).to_have_count(2)
    assert page.locator("#new-chat").bounding_box()["height"] == 44
    assert page.evaluate("document.documentElement.scrollHeight") <= size[1]


def test_card_date_stays_on_one_line_in_drawer_at_360(open_page):
    conversation = {**_conversation(1, "washer-samsung-wd90h25"), "updated_at": "2026-11-11T09:00:00.000Z"}
    page = open_page(conversations=[conversation])
    go_category(page)
    open_drawer(page)
    meta = drawer_cards(page).first.locator(".card-meta")
    expect(meta).to_have_text(f"{NAMES['washer-samsung-wd90h25']} · 11월 11일")
    # 줄이 바뀌는 자리는 글꼴·기기 폭에 따라 달라서, 카드 글자 폭을 1px씩 바꿔 가며 날짜가 두 줄로 나뉘는 폭이 없는지 본다
    split = meta.evaluate("""(m) => {
        const nodes = []; const w = document.createTreeWalker(m, NodeFilter.SHOW_TEXT);
        while (w.nextNode()) nodes.push(w.currentNode);
        const at = (i) => { for (const n of nodes) { if (i < n.length) return [n, i]; i -= n.length; } };
        const date = '11월 11일';
        const start = nodes.map((n) => n.textContent).join('').indexOf(date);
        const [last, end] = at(start + date.length - 1);
        const r = document.createRange(); r.setStart(...at(start)); r.setEnd(last, end + 1);
        const bad = [];
        for (let px = 100; px <= 320; px++) {
            m.style.width = `${px}px`;
            if (new Set([...r.getClientRects()].filter((x) => x.width > 0).map((x) => Math.round(x.top))).size > 1) bad.push(px);
        }
        m.style.width = '';
        return bad; }""")
    assert split == []


def test_first_screen_has_no_console_errors_or_failed_requests(open_page):
    page = open_page(path="about:blank")
    errors, failed = [], []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("response", lambda r: failed.append((r.status, r.url)) if r.status >= 400 else None)
    page.goto("/")
    assert_screen(page, LANDING_H1)
    page.wait_for_load_state("networkidle")
    assert errors == [] and failed == [], (errors, failed)


# ── 포커스 링: 회색 면 요소는 회색 틈(--focus-ring-surface), 그 밖은 흰 틈(--focus-ring). 2026-11-11 결정기록 024 결정 11 ──
RING_SURFACE = "rgb(242, 242, 242) 0px 0px 0px 2px, rgb(17, 17, 17) 0px 0px 0px 4px"
RING_WHITE = "rgb(255, 255, 255) 0px 0px 0px 2px, rgb(17, 17, 17) 0px 0px 0px 4px"


def tab_to(page, selector):
    # 키보드(Tab)로만 옮겨 :focus-visible 상태를 실제와 같게 만든다
    for _ in range(30):
        page.keyboard.press("Tab")
        if page.evaluate("(s) => document.activeElement.matches(s)", selector):
            return
    raise AssertionError(f"Tab으로 {selector}에 가지 못함")


def ring(page, selector=None):
    return page.evaluate("(s) => getComputedStyle(s ? document.querySelector(s) : document.activeElement).boxShadow", selector)


def test_focus_ring_gray_gap_on_surface_elements_white_gap_on_buttons(open_page):
    page = open_page(conversations=[_conversation(1, "washer-lg-fx25")])
    tab_to(page, ".conv-card")   # 랜딩 최근 대화 카드(회색 면)
    assert ring(page) == RING_SURFACE
    tab_to(page, ".pill")   # 랜딩 "시작하기"(검은 버튼): 흰 틈
    assert ring(page) == RING_WHITE
    go_category(page)
    tab_to(page, ".tile")
    assert ring(page) == RING_SURFACE
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")   # 더 추가 예정(aria-disabled)도 같은 면
    assert page.evaluate("document.activeElement.textContent.trim()") == "더 추가 예정" and ring(page) == RING_SURFACE
    page.get_by_role("button", name="세탁기").click()
    expect(page.locator(".model-card").first).to_be_visible()
    tab_to(page, ".model-card")
    assert ring(page) == RING_SURFACE
    open_chat(page, "washer-samsung-wd90h25")
    tab_to(page, ".suggestion")
    assert ring(page) == RING_SURFACE
    tab_to(page, "#question")   # 입력창: 알약 전체(.composer-box)에 회색 틈
    assert ring(page, ".composer-box") == RING_SURFACE and ring(page) == "none"
    page.keyboard.type("가짜 질문")
    tab_to(page, "#send")   # 보내기(검은 동그라미): 흰 틈
    assert ring(page) == RING_WHITE
    open_drawer(page)
    for selector in ("#drawer-close", "#drawer .pill"):   # 흰 바탕 글자 버튼·검은 버튼은 흰 틈
        tab_to(page, selector)
        assert ring(page) == RING_WHITE, selector
        assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") == "solid"   # 강제 색 모드용 outline 유지
    tab_to(page, "#drawer .conv-card")
    assert ring(page) == RING_SURFACE


# ── 근거 접기(2026-11-11 사용자 결정): 접힌 한 줄 + 같은 출처 한 상자 + "드릴까요?" 버튼 하나 ──
GUIDE_CITE = {"doc_type": "guide", "title": "가짜 가이드", "page": None, "url": "https://example.com/guide",
              "quote": "가짜 가이드 인용입니다(테스트).", "warning": GUIDE_WARNING}
MIXED = [CITE, {**CITE, "page": 13, "quote": "가짜 인용 둘(테스트)."}, {**CITE, "quote": "가짜 인용 셋(테스트)."},
         GUIDE_CITE, {**GUIDE_CITE, "quote": "가짜 가이드 인용 둘(테스트)."}]
MIXED_LABEL = "근거 보기 · 사용설명서 12·13쪽 · 공식 해결 가이드 1개"


def test_evidence_folded_grouped_and_links_only_after_offer(open_page):
    page = open_page(ask=lambda body, route: fake(body, citations=MIXED))
    open_chat(page, "washer-samsung-wd90h25")
    send(page, "가짜 질문입니다")
    wait_turns(page, 1)
    turn = page.locator(".turn").last
    fold = turn.get_by_role("button", name=MIXED_LABEL)
    expect(fold).to_have_attribute("aria-expanded", "false")   # 처음에는 접힘, 라벨에 쪽(중복 없이 오름차순)과 가이드 수
    controls = fold.get_attribute("aria-controls")
    expect(page.locator(f"#{controls}")).to_be_hidden()
    warning = turn.locator(".notice", has_text=GUIDE_WARNING)
    expect(warning).to_have_count(1)   # 공용 가이드 경고는 한 번만, 접힌 줄 밖(위)에 보인다
    expect(warning).to_be_visible()
    assert warning.evaluate("(n, id) => !n.closest('#' + id)", controls)
    assert warning.evaluate("(n) => !!(n.compareDocumentPosition(n.parentElement.querySelector('.fold')) & Node.DOCUMENT_POSITION_FOLLOWING)")
    fold.click()
    expect(fold).to_have_attribute("aria-expanded", "true")
    boxes = turn.locator(".evidence")
    expect(boxes).to_have_count(3)   # 12쪽·13쪽·가이드 한 상자씩(인용이 처음 나온 순서)
    expect(boxes.locator(".evidence-label")).to_have_text(["사용설명서 12쪽", "사용설명서 13쪽", "공식 해결 가이드: 가짜 가이드"])
    expect(boxes.nth(0).locator("li")).to_have_text(["가짜 인용입니다(테스트).", "가짜 인용 셋(테스트)."])
    expect(boxes.nth(2).locator("li")).to_have_count(2)
    expect(page.locator(f"#{controls} a")).to_have_count(0)   # 상자 안에는 링크가 없다
    offer = turn.get_by_role("button", name="공식 설명서·문서를 드릴까요?")
    expect(offer).to_have_count(1)
    assert offer.bounding_box()["height"] >= 44
    offer.click()
    expect(offer).to_have_count(0)   # 버튼 자리에 링크가 나온다(한 번만, URL 중복 없이)
    links = turn.locator(".doc-links a")
    codes = "·".join(next(m for m in MODELS if m["id"] == "washer-samsung-wd90h25")["model_codes"])
    expect(links).to_have_text([f"공식 설명서 받기 (검색어: {codes})", "공식 문서 열기: 가짜 가이드"])
    expect(links.first).to_be_focused()
    expect(turn.locator("a")).to_have_count(2)


def test_evidence_keyboard_only_expand_and_offer(open_page):
    page = open_page(ask=lambda body, route: fake(body, citations=MIXED))
    open_chat(page, "washer-samsung-wd90h25")
    send(page, "가짜 질문입니다")
    wait_turns(page, 1)
    tab_to(page, ".turn .fold")
    page.keyboard.press("Enter")
    expect(page.locator(".turn .fold")).to_have_attribute("aria-expanded", "true")
    tab_to(page, ".turn .offer")
    assert ring(page) == RING_SURFACE   # 회색 면 버튼이라 회색 틈(결정기록 024 결정 11)
    page.keyboard.press("Enter")
    expect(page.locator(".turn .doc-links a").first).to_be_focused()


def test_saved_conversation_renders_evidence_the_same_way(open_page):
    conversation = _conversation(1, "washer-samsung-wd90h25")
    conversation["turns"] = [{"question_masked": f"가짜 질문 {i}", "rewritten_question": None, "answer": "가짜 답", "found": True,
                              "citations": MIXED, "kind": "answer"} for i in (1, 2)]
    page = open_page(conversations=[conversation])
    open_chat(page, "washer-samsung-wd90h25", "c1")
    expect(page.locator(".turn")).to_have_count(2)
    expect(page.locator(".turn .fold", has_text=MIXED_LABEL)).to_have_count(2)   # 이전 답(접힌 안, 숨김)과 최신 답 모두 같은 구조
    expect(page.locator(".turn").last.get_by_role("button", name="공식 설명서·문서를 드릴까요?")).to_be_visible()
    page.get_by_role("button", name="이전 답 · 근거 5개").click()
    first = page.locator(".turn").first
    expect(first.get_by_role("button", name=MIXED_LABEL)).to_be_visible()
    expect(first.get_by_role("button", name="공식 설명서·문서를 드릴까요?")).to_be_visible()


# ── 아래 고정 입력창에 포커스가 가려지지 않음(WCAG 2.2 2.4.11, 2026-11-11 사용자 결정). 위쪽 막대는 고정이 아니라 아래만 본다 ──
def assert_focus_above_composer(page, step):
    box = page.evaluate("""() => { const a = document.activeElement.getBoundingClientRect();
        const c = document.querySelector('.composer').getBoundingClientRect();
        return {bottom: a.bottom, top: a.top, composer: c.top, tag: document.activeElement.className || document.activeElement.tagName}; }""")
    assert box["top"] >= 0 and box["bottom"] <= box["composer"], (step, box)


@pytest.fixture(scope="module")
def chrome(playwright):
    # 입력창 높이는 ResizeObserver(화면 갱신 프레임 때 불림)로 잰다. 기본 headless shell에서는 이 페이지에서
    # requestAnimationFrame이 1초 안에 한 번도 돌지 않아(2026-11-11 확인) 설치된 Chrome으로 연다(measure/a11y.py와 같음)
    b = playwright.chromium.launch(channel="chrome")
    yield b
    b.close()


@pytest.mark.parametrize("size", [(360, 640), (360, 560)])
def test_keyboard_focus_never_hidden_under_sticky_composer(chrome, base_url, size):
    page, _ = _open(chrome, base_url, ask=lambda body, route: fake(body, citations=MIXED))
    page.set_viewport_size({"width": size[0], "height": size[1]})
    open_chat(page, "washer-samsung-wd90h25")
    for i in (1, 2):
        send(page, f"가짜 질문 {i}")
        wait_turns(page, i)
    tab_to(page, ".turn:last-child .fold")   # 최신 답의 근거 줄
    assert_focus_above_composer(page, "근거 줄")
    page.keyboard.press("Enter")
    tab_to(page, ".turn:last-child .offer")
    assert_focus_above_composer(page, "드릴까요 버튼")
    page.keyboard.press("Enter")   # 버튼 자리에 링크, 포커스는 첫 링크
    expect(page.locator(".turn:last-child .doc-links a").first).to_be_focused()
    assert_focus_above_composer(page, "첫 링크")
    page.keyboard.press("Tab")
    expect(page.locator(".turn:last-child .doc-links a").nth(1)).to_be_focused()
    assert_focus_above_composer(page, "둘째 링크")
    tab_to(page, ".turn:first-child > .fold")   # 이전 답 접기 줄
    assert_focus_above_composer(page, "이전 답 줄")
    page.keyboard.press("Enter")
    tab_to(page, ".turn:first-child .answer-body .fold")   # 이전 답 안의 근거 줄
    assert_focus_above_composer(page, "이전 답 근거 줄")
    page.context.close()
