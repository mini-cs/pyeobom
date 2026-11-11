"""화면 흐름(랜딩 → 카테고리 → 모델) Playwright 테스트. 로컬 정적 서버에서 열고 /api/*는 가로챈다(AI 비용 없음)."""
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

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
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
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
    soon = page.get_by_role("button", name="곧 추가")
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
    assert_screen(page, CATEGORY_H1)  # 곧 추가는 눌러도 이동하지 않는다


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
        links = page.locator(".turn .evidence a")
        expect(links).to_have_text([f"공식 설명서 받기 (검색어: {'·'.join(m['model_codes'])})", "공식 문서 열기"])
        rest = page.evaluate("""() => { const c = document.querySelector('[data-screen="chat"]').cloneNode(true);
            c.querySelectorAll('.evidence a').forEach((a) => a.remove());
            return document.getElementById('topbar').textContent + c.textContent; }""")
        assert not [c for c in CODES if c in rest], rest   # 예외는 설명서 링크 하나뿐


def test_chat_screen_has_no_footer_note(open_page):
    page = open_page()
    expect(page.get_by_text("비영리 학습용 포트폴리오예요.")).to_be_visible()   # 랜딩에는 그대로
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
    expect(last.locator(".evidence")).to_be_visible()
    expect(last.locator(".evidence a")).to_have_attribute("target", "_blank")
    assert "noopener" in last.locator(".evidence a").get_attribute("rel")
    fold = first.get_by_role("button", name="이전 답 · 근거 2개")
    expect(fold).to_have_attribute("aria-expanded", "false")
    expect(first.locator(".answer")).to_be_hidden()
    expect(first.locator(".evidence")).to_have_count(2)
    expect(first.locator(".evidence").first).to_be_hidden()
    fold.click()
    expect(fold).to_have_attribute("aria-expanded", "true")
    expect(first.locator(".answer")).to_be_visible()
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
    page, asks = open_page(ask=lambda body, route: held.append(route), with_asks=True)
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
