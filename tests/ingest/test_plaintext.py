from ingest.plaintext import markdown_to_plain


def test_heading():
    p = markdown_to_plain("## 쾌속\n일상 세탁물을 빠르게")
    assert (p.text, p.headings) == ("쾌속\n일상 세탁물을 빠르게", [(0, "쾌속")])


def test_table():
    md = "| 설정 | 온도 (°C) |\n|---|---|\n| 선택 가능 | 냉수 / 20 / 30 |"
    assert markdown_to_plain(md).text == "설정 온도 (°C)\n선택 가능 냉수 / 20 / 30"


def test_bold_image_comment():
    assert markdown_to_plain("**주의** ![](a.png)<!-- image -->내용").text == "주의 내용"


def test_model_star_kept():
    assert markdown_to_plain("WD90H25AH*/WD90H25BH*").text == "WD90H25AH*/WD90H25BH*"


def test_numbers_kept():
    t = "최대 용량: 4.0 kg, 1/2, 220 V/60 Hz"
    assert markdown_to_plain(t).text == t


def test_list_kept():
    assert markdown_to_plain("- 세탁물을 분류하세요.").text == "- 세탁물을 분류하세요."


def test_heading_offsets_after_table():  # 표 줄이 바뀐 뒤에도 제목 위치가 평문 기준인지
    p = markdown_to_plain("| a | b |\n|---|---|\n# 미세플라스틱저감\n본문")
    assert p.text[p.headings[0][0]:].startswith("미세플라스틱저감")


def test_crlf_normalized():
    p = markdown_to_plain("| a | b |\r\n|---|---|\r\n# 제목\r\n본문")
    assert p.text == "a b\n제목\n본문" and p.headings == [(4, "제목")]


def test_empty_table_cells_dropped():
    assert markdown_to_plain("| a | | c |").text == "a c"
    assert markdown_to_plain("| a | ![](x.png) | c |").text == "a c"


def test_clean_plain_page():
    from ingest.clean import clean_text
    from ingest.plaintext import PlainPage, clean_plain_page

    text = "머리말\n(cid:12)\n## 쾌속 (cid:3)\n본문\nUntitled-1 12\n## 바닥\n끝"
    pp = markdown_to_plain(text)
    out = clean_plain_page(pp)
    assert out.text == clean_text(pp.text) == "머리말\n쾌속\n본문\n바닥\n끝"
    assert [h for _, h in out.headings] == ["바닥"] or all(out.text[i:].startswith(h) for i, h in out.headings)
    assert all(out.text[i:].startswith(h) for i, h in out.headings)
    assert ("바닥" in [h for _, h in out.headings])  # 뒤 제목은 앞 줄이 지워져도 남고 위치가 당겨진다
    assert out.text.index("바닥") == dict((h, i) for i, h in out.headings)["바닥"]
    # 지워진 줄에 걸린 제목은 버린다
    pp2 = PlainPage("a\n(cid:12)\nb", [(2, "(cid:12)")])
    assert clean_plain_page(pp2).headings == []
    pp3 = PlainPage("Untitled-1 12\n본문", [(0, "Untitled-1 12")])
    assert clean_plain_page(pp3) == PlainPage("본문", [])


def test_html_table():
    md = "<table><tr><td></td><td>(ml)</td></tr><tr><td>1/2</td><td>40</td><td>15</td></tr></table>"
    assert markdown_to_plain(md).text == "(ml)\n1/2 40 15"


def test_br_to_space():
    assert markdown_to_plain("내일 날씨 알려줘<br>오늘 습도 어때?").text == "내일 날씨 알려줘 오늘 습도 어때?"


def test_span_removed_heading_kept():
    p = markdown_to_plain('<span id="page-2-0"></span>\n\n## 안전을 위해 주의하기')
    assert "<span" not in p.text and (p.headings[0][1]) == "안전을 위해 주의하기"
    assert p.text[p.headings[0][0]:].startswith("안전을 위해 주의하기")


def test_other_tags_and_strike():
    assert markdown_to_plain("<mark>2 한</mark> ~~<mark>국어</mark>~~").text == "2 한 국어"
    assert markdown_to_plain("kgf/cm<sup>2</sup>").text == "kgf/cm2"


def test_backslash_escape():
    assert markdown_to_plain(r"WD90H25AH\*/WD90H25BH\*").text == "WD90H25AH*/WD90H25BH*"
    assert markdown_to_plain(r"AR60F\*\*C\*\*\*\*").text == "AR60F**C****"
    assert markdown_to_plain(r"<보기> 18℃\~30℃").text == "<보기> 18℃~30℃"
    assert markdown_to_plain(r"\alpha").text == r"\alpha"


def test_link_and_img_tag():
    assert markdown_to_plain("[센터(1544-7777)로 연락하세요.](tel:1544-7777)").text == "센터(1544-7777)로 연락하세요."
    assert markdown_to_plain('<img src="data:image/jpeg;base64,AAAA"/>1/2').text == "1/2"


def test_noise_kept():
    t = "_<| 4 FR) Su | <i | our"
    assert markdown_to_plain(t).text == t


def test_invisible_chars_removed():  # 결정 ⑭: U+FEFF·U+200B는 str.split()이 공백으로 치지 않아 인용 확인을 깬다
    assert markdown_to_plain("세탁﻿코스와 건​조").text == "세탁코스와 건조"
    assert markdown_to_plain("| ﻿ 설정 | 30 |").text == "설정 30"
    assert markdown_to_plain("위\n﻿\n​ ﻿\n아래").text == "위\n아래"


def test_invisible_chars_only_those():
    t = "4.0 kg · 1/2 • WD90H25AH*/WD90H25BH* 220 V/60 Hz\n\n빈 줄 위"
    assert markdown_to_plain(t).text == t
    p = markdown_to_plain("﻿\n## 제목﻿ 하나\n본문")
    assert p.text == "제목 하나\n본문" and p.headings == [(0, "제목 하나")]
