import pytest

from measure.search_variants import doc_headings, m1_text, page_heading


@pytest.mark.parametrize("page, text, expected", [
    (16, "16 사용하기\n세제 넣고 사용하기\n액체 세제 넣고 사용하기\n1 세탁기 왼쪽에 있는 세제함을 당기세요.", ("사용하기", "세제 넣고 사용하기")),
    (41, "관리하기 41\n급수구 거름망 청소하기\n• 급수가 약해지면", ("관리하기", "급수구 거름망 청소하기")),
    # 삼성: 짝수 쪽은 "장 이름\n18 한국어", 홀수 쪽은 "한국어 11"(장 이름 없음)
    (18, "사용 전 확인사항\n18 한국어\n 세탁 및 건조 표시 안내 (KSK-0021 규격)\n주의", ("사용 전 확인사항", "세탁 및 건조 표시 안내 (KSK-0021 규격)")),
    (11, "한국어 11\n 오프라인 기기 진단\n• 스마트싱스 앱 내의", (None, "오프라인 기기 진단")),
])
def test_page_heading_takes_running_header_and_first_heading_line(page, text, expected):
    assert page_heading(page, text) == expected


@pytest.mark.parametrize("text", [
    "사용하기 15\n• 슬리브, 스타킹 같은 작은\n세탁물의 경우 드럼 틈새에 낄 수 있으므로 세탁망을\n이용하여 세탁하세요.",  # 문장 중간 줄(조사로 끝남)
    "사용하기 27\n버튼을 누르세요. 리모컨 표시부에 간접바람이\n표시됩니다.",  # 문장
    "고장 신고 전 확인하기 51\n제품 근처에 강한 빛이 나오는 물건이 있나요?",  # 질문 문장
    "사용하기 20\n주의\n• 세탁물을 드럼 안쪽으로",  # 주의·경고·알아두기 같은 표시 말
    "사용하기 30\n→ 스마트케어 냉방 운전 → 아이스 쿨파워 냉방 운전\n• 버튼을",  # 화살표로 시작하는 본문 줄
])
def test_sentence_lines_are_not_headings(text):
    page = int(text.split("\n")[0].split()[-1])
    assert page_heading(page, text)[1] is None


def test_missing_values_are_inherited_from_previous_page():
    pages = [(10, "관리 방법\n10 한국어\n 내부 관리하기\n• 문"), (11, "한국어 11\n• 계속되는 설명"), (12, "설치 방법\n12 한국어\n 설치하기\n• 위치")]
    assert doc_headings(pages) == {10: ("관리 방법", "내부 관리하기"), 11: ("관리 방법", "내부 관리하기"), 12: ("설치 방법", "설치하기")}


def test_m1_text_puts_title_line_before_chunk():
    assert m1_text(["LG 드럼세탁기 (FX25*N*)"], "LG 드럼세탁기 사용설명서", ("관리하기", "통살균 하기"), "본문") == \
        "LG 드럼세탁기 (FX25*N*) · LG 드럼세탁기 사용설명서 · 관리하기 · 통살균 하기\n본문"
    # 가이드(쪽 없음)는 모델·문서 제목만
    assert m1_text(["LG 드럼세탁기 (FX25*N*)"], "[LG 드럼세탁기 에러코드] 표시창에 에러표시가 나타나요", (None, None), "본문") == \
        "LG 드럼세탁기 (FX25*N*) · [LG 드럼세탁기 에러코드] 표시창에 에러표시가 나타나요\n본문"
