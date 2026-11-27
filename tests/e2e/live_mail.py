"""실제 흐름 테스트(test_request_flow_live.py)의 순수 함수: 받기 주소 만들기·코드 메일 고르기·코드 뽑기·비밀 가리기.

실제 연결 없이 기본 실행(test_live_mail.py)에서 확인한다. 받기 주소·도메인·코드를 출력하지 않는다.
"""
import re
import secrets
from datetime import datetime

_BLOCKS = re.compile(r"<(style|script)\b.*?</\1\s*>", re.I | re.S)
_TAGS = re.compile(r"<[^>]*>")
_LINKS = re.compile(r"https?://\S+", re.I)
# 앞뒤가 영문·숫자·밑줄·#이 아닌 6~10자리(한글은 붙어 있어도 됨). \d는 다른 문자권 숫자도 잡아 [0-9]로 쓴다
_CODE = re.compile(r"(?<![A-Za-z0-9_#])[0-9]{6,10}(?![A-Za-z0-9_#])")


def make_address(role: str, domain: str) -> str:
    return f"e2e-{role}-{secrets.token_hex(4)}@{domain}".lower()


def extract_code(text: str | None) -> str | None:
    if not text:
        return None
    plain = _LINKS.sub(" ", _TAGS.sub(" ", _BLOCKS.sub(" ", text)))
    m = _CODE.search(plain)
    return m.group(0) if m else None


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pick_mail(items: list[dict], address: str, since: datetime) -> str | None:
    want = address.lower()
    hits = [m for m in items
            if want in [t.lower() for t in (m.get("to") or [])] and parse_time(m["created_at"]) >= since]
    return max(hits, key=lambda m: parse_time(m["created_at"]))["id"] if hits else None


def scrub(text: str, secrets: list[str | None]) -> str:
    # 긴 것부터: 주소 안의 도메인이 먼저 바뀌어 주소 앞부분이 남는 일이 없게
    for s in sorted((s for s in secrets if s), key=len, reverse=True):
        text = re.sub(re.escape(s), "<가림>", text, flags=re.I)
    return text
