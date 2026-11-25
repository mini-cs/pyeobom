"""개인정보 처리방침 페이지(public/privacy.html, 2026-11-25 사용자 결정). 문구는 채팅 Claude 초안 3판 그대로."""
from pathlib import Path

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui

CONTACT = "pyeobom@gmail.com"
# 문구 3판의 줄(2판에서 "요청 알림" 줄만 고침)(목록 머리 "- "만 뺌). 페이지에 글자 그대로 있어야 한다. 쿠키 문장은 운영 응답에 Set-Cookie가 없어 확정(2026-11-25)
LINES = (Path(__file__).with_name("privacy_v3.txt")).read_text(encoding="utf-8").splitlines()


@pytest.fixture
def page(browser, base_url):
    context = browser.new_context(base_url=base_url, viewport={"width": 360, "height": 740})
    p = context.new_page()
    yield p
    context.close()


def test_privacy_page_is_served_with_title_and_contact(page):
    res = page.goto("/privacy.html")
    assert res.status == 200
    expect(page.get_by_role("heading", level=1)).to_have_text("펴봄 개인정보 처리방침")
    contact = page.get_by_role("link", name=CONTACT).first
    expect(contact).to_be_visible()
    assert contact.get_attribute("href") == f"mailto:{CONTACT}"


def test_privacy_page_has_every_line_of_draft_3(page):
    page.goto("/privacy.html")
    text = " ".join(page.locator("body").inner_text().split())
    missing = [line for line in LINES if line.strip() and " ".join(line.split()) not in text]
    assert missing == []


def test_privacy_page_links_home_and_fits_phone_width(page):
    page.goto("/privacy.html")
    home = page.get_by_role("link", name="펴봄", exact=True)
    assert home.get_attribute("href") == "/"
    assert page.evaluate("document.documentElement.scrollWidth") <= 360   # 휴대폰 폭에서 가로로 넘치지 않음
    home.click()
    expect(page.get_by_role("heading", level=1)).to_have_text("가전 설명서, 대신 펴 봐 드려요")
