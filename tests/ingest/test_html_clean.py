from ingest.clean import clean_text, drop_out_of_scope
from ingest.html import extract_html


def test_html_includes_hidden_tab_panels_and_skips_nav():
    text = extract_html("tests/ingest/fixtures/sample_guide.html", "article", "샘플 에러코드 안내")
    assert text.startswith("샘플 에러코드 안내")                    # 제목을 앞에 붙임
    assert "첫째 패널 설명" in text and "숨은 패널 설명" in text   # display:none 패널 포함
    assert text.index("AA [첫째 코드]") < text.index("첫째 패널 설명")  # <select> 탭 이름이 패널 앞에
    assert text.index("BB [둘째 코드]") < text.index("숨은 패널 설명")
    assert "메뉴" not in text and "바닥글" not in text              # article 밖 제외
    assert "전원을 끄고 다시 켜세요." in text                       # 문단 안 강조 태그는 한 줄로 이어 붙임


def test_clean_text_removes_broken_footer():
    raw = "배수 필터를 청소하세요.\nUUnnttiittlleedd--11 1122\n(cid:31)(cid:32)\n전원을 끄세요."
    assert clean_text(raw) == "배수 필터를 청소하세요.\n전원을 끄세요."


def test_clean_text_removes_plain_untitled_footer():
    # pypdfium2는 바닥글을 깨지 않은 형태로 쪽마다 1줄 남긴다 (결정기록 016 수정)
    raw = "이불 코스\n• 최대 용량: 4.0 kg\nUntitled-1 38 2026-02-26 10:07:02"
    assert clean_text(raw) == "이불 코스\n• 최대 용량: 4.0 kg"


def test_drop_out_of_scope_paragraphs():
    raw = ("배수 필터를 청소하세요.\n\n"
           "플렉스워시 제품은 상부와 하부 표시가 다릅니다.\n\n"
           "[플렉스워시 제품 누수 점검 안내]\n상단에 호스를 고정하세요.\n\n"
           "[일반 안내]\n전원을 끄고 다시 켜세요.")
    text, n = drop_out_of_scope(raw, ["플렉스워시"])
    assert "플렉스워시" not in text and "상단에 호스를 고정" not in text
    assert "배수 필터를 청소하세요." in text and "전원을 끄고 다시 켜세요." in text and n == 2


def test_drop_out_of_scope_without_keywords_keeps_all():
    assert drop_out_of_scope("가\n\n나", []) == ("가\n\n나", 0)
