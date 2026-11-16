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
