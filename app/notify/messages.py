"""알림 메일 문구(계획 Task 7). 요청자 이메일·사용자 id는 넣지 않는다."""
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
CATEGORIES = {"washer": "세탁기", "dryer": "건조기", "aircon": "에어컨"}
SITE = "https://pyeobom.help"


def _kst(value) -> str:
    try:
        return datetime.fromisoformat(str(value)).astimezone(KST).strftime("%Y-%m-%d %H:%M (KST)")
    except ValueError:
        return str(value)


def operator_message(record: dict) -> tuple[str, str]:
    subject = f"[펴봄] 새 모델 요청 #{record['id']}"
    text = "\n".join([
        f"가전 종류: {CATEGORIES.get(record['category'], record['category'])}",
        f"브랜드: {record['brand']}",
        f"모델명: {record['model_text']}",
        f"요청 시각: {_kst(record['created_at'])}",
    ])
    return subject, text


def requester_message(record: dict) -> tuple[str, str]:
    model = f"{record['brand']} {record['model_text']}"
    if record["status"] == "추가됨":
        # "을/를"은 모델명 끝 받침에 따라 달라 "~에 대해"로 쓴다(2026-11-25 사용자 확인)
        return "요청하신 모델이 펴봄에 추가됐어요", f"이제 펴봄에서 {model}에 대해 물어볼 수 있어요. {SITE}"
    return "요청하신 모델을 추가하지 못했어요", f"요청: {model}\n사유: {record['reason']}\n\n궁금한 점은 이 메일에 답장해 주세요."
