"""알림 메일 문구(계획 Task 7, 요청자 "추가됨" 본문은 2026-11-25 사용자 확인). 값은 모두 가짜."""
from app.notify.messages import operator_message, requester_message

USER_ID = "00000000-0000-4000-8000-000000000001"
RECORD = {"id": 7, "user_id": USER_ID, "category": "dryer", "brand": "가짜브랜드", "model_text": "DV90-FAKE1",
          "status": "대기", "reason": None, "model_id": None, "created_at": "2026-11-25T05:03:00.123456+00:00"}


def test_operator_message_has_request_fields_in_kst():
    subject, text = operator_message(RECORD)
    assert subject == "[펴봄] 새 모델 요청 #7"
    assert text == "가전 종류: 건조기\n브랜드: 가짜브랜드\n모델명: DV90-FAKE1\n요청 시각: 2026-11-25 14:03 (KST)"


def test_operator_message_keeps_unreadable_time_as_is():
    _, text = operator_message({**RECORD, "created_at": "알 수 없음"})
    assert text.endswith("요청 시각: 알 수 없음")


def test_requester_added_message():
    subject, text = requester_message({**RECORD, "status": "추가됨", "model_id": "dryer-fake-a"})
    assert subject == "요청하신 모델이 펴봄에 추가됐어요"
    assert text == "이제 펴봄에서 가짜브랜드 DV90-FAKE1에 대해 물어볼 수 있어요. https://pyeobom.help"


def test_requester_hard_message_has_reason():
    subject, text = requester_message({**RECORD, "status": "추가 어려움", "reason": "공식 설명서를 찾지 못했어요(테스트)"})
    assert subject == "요청하신 모델을 추가하지 못했어요"
    assert text == ("요청: 가짜브랜드 DV90-FAKE1\n사유: 공식 설명서를 찾지 못했어요(테스트)\n\n"
                    "궁금한 점은 이 메일에 답장해 주세요.")


def test_messages_have_no_user_id_or_key():
    texts = [*operator_message(RECORD), *requester_message({**RECORD, "status": "추가됨"}),
             *requester_message({**RECORD, "status": "추가 어려움", "reason": "사유(테스트)"})]
    for t in texts:
        assert USER_ID not in t and "@" not in t and "sb_" not in t and "re_" not in t
