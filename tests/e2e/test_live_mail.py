import re
from datetime import datetime, timezone

from tests.e2e.live_mail import extract_code, make_address, parse_time, pick_mail, scrub

SINCE = datetime(2026, 11, 27, 7, 0, 0, tzinfo=timezone.utc)


def test_make_address_is_new_lowercase_each_time():
    a1, a2 = make_address("a", "Fake.Test"), make_address("a", "Fake.Test")
    assert re.fullmatch(r"e2e-a-[0-9a-f]{8}@fake\.test", a1)
    assert a1 != a2


def test_extract_code_takes_six_to_ten_digits_only():
    assert extract_code("2026년 11월 펴봄 로그인 코드: 482913 (1시간 안에 입력)") == "482913"
    assert extract_code("코드 12345678") == "12345678"
    assert extract_code("코드는482913입니다") == "482913"
    assert extract_code("12345 은 너무 짧고 12345678901 은 너무 길어요") is None
    assert extract_code(None) is None


def test_extract_code_ignores_colors_links_and_attributes_in_html():
    html = ('<style>p{color:#333333}</style><p style="color:#111111">코드</p>'
            '<a href="https://fake.test/verify?token=9876543210abc">열기</a> https://fake.test/1234567 '
            '<strong>482913</strong>')
    assert extract_code(html) == "482913"


def test_parse_time_accepts_resend_iso_form():
    assert parse_time("2026-11-27T07:00:05.123Z") == datetime(2026, 11, 27, 7, 0, 5, 123000, tzinfo=timezone.utc)


def test_pick_mail_only_this_address_after_start():
    items = [
        {"id": "old", "to": ["e2e-a-aaaa@fake.test"], "created_at": "2026-11-27T06:59:59.000Z"},
        {"id": "other", "to": ["e2e-b-bbbb@fake.test"], "created_at": "2026-11-27T07:00:10.000Z"},
        {"id": "new1", "to": ["E2E-A-AAAA@fake.test"], "created_at": "2026-11-27T07:00:05.000Z"},
        {"id": "new2", "to": ["e2e-a-aaaa@fake.test"], "created_at": "2026-11-27T07:00:20.000Z"},
    ]
    assert pick_mail(items, "e2e-a-aaaa@fake.test", SINCE) == "new2"
    assert pick_mail(items, "e2e-c-cccc@fake.test", SINCE) is None


def test_scrub_hides_every_secret_case_insensitively():
    text = "to E2E-A-aaaa@fake.test code 482913 at fake.test"
    out = scrub(text, ["e2e-a-aaaa@fake.test", "482913", "fake.test", None, ""])
    assert "fake.test" not in out.lower() and "482913" not in out
    assert out.count("<가림>") >= 3
