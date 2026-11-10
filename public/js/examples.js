// 채팅 추천 카드(대화가 없을 때). question은 1차 예시 질문 그대로(실제 /api/ask로 근거가 나오는 것을 확인한 문장,
// 평가 질문 30개와 겹치지 않게, 2026-10-29). hint는 카드 둘째 줄의 짧은 화면 문구로, 설명서 내용을 지어내지 않는다.
// 테스트가 JSON으로 읽으므로 키는 큰따옴표로 쓴다(tests/web/test_public_page.py, tests/core/test_brand_guard.py).
export const EXAMPLES = {
  "washer-samsung-wd90h25": [
    { "question": "이불 코스는 어떻게 해요?", "hint": "코스 쓰는 방법" },
    { "question": "물이 안 빠지고 5C가 떠요", "hint": "원인과 해결 방법" },
  ],
  "washer-lg-fx25": [
    { "question": "통세척은 어떻게 해요?", "hint": "세탁조 관리 방법" },
    { "question": "UE 에러가 떴어요", "hint": "원인과 해결 방법" },
  ],
  "aircon-lg-sq06fa1wds": [
    { "question": "필터 청소는 어떻게 해요?", "hint": "관리 방법" },
    { "question": "꺼짐 예약은 어떻게 해요?", "hint": "예약 설정 방법" },
  ],
};
