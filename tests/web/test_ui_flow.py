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


def _open(browser, base_url, path="/", conversations=None):
    context = browser.new_context(viewport={"width": 360, "height": 780}, base_url=base_url)
    context.set_default_timeout(5000)  # 실패할 때 30초씩 기다리지 않게
    context.route(re.compile(r"^(?!http://127\.0\.0\.1)"), lambda route: route.abort())  # 외부로 나가는 요청 없음
    context.route("**/api/models", lambda route: route.fulfill(json=MODELS))
    context.route("**/api/ask", lambda route: route.fulfill(
        status=504, json={"error_code": "AI_TIMEOUT", "message": "가짜 오류"}))  # 실제 /api/ask에 붙지 않는다
    if conversations is not None:
        state = json.dumps({"version": 1, "conversations": conversations}, ensure_ascii=False)
        context.add_init_script(f"localStorage.setItem({json.dumps(STORE_KEY)}, {json.dumps(state)})")
    page = context.new_page()
    page.goto(path)
    return page


@pytest.fixture
def open_page(browser, base_url):
    pages = []

    def opener(path="/", conversations=None):
        pages.append(_open(browser, base_url, path, conversations))
        return pages[-1]

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
    assert_screen(page, NAMES["aircon-lg-sq06fa1wds"])
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
    assert_screen(page, NAMES["washer-samsung-wd90h25"])
    assert_focus_on_h1(page, NAMES["washer-samsung-wd90h25"])
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
    assert_screen(page, NAMES["washer-samsung-wd90h25"])
    no_codes(page.locator("#topbar"))
    no_codes(page.get_by_role("heading", level=1))
