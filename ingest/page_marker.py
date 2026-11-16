"""쪽 표시 지우기(v1.7 설계 6절). 운영 적재(ingest/clean.py)에는 연결하지 않는다."""
import re

WINDOW = 20  # 앞(또는 끝) 20자 안
_BREAK = r"(?:\r\n|[ \n])"  # 지울 공백·줄바꿈 하나(\r\n은 하나)


def _pattern(page: int, *, attached_only: bool = False) -> re.Pattern:
    n = rf"(?<!\d){page}(?!\d)"
    alts = [rf"한국어\s+{n}", rf"{n}[ \t]+한국어"] + ([] if attached_only else [n])
    return re.compile(rf"(?<!\S)(?:{'|'.join(alts)})(?!\S)")


def _num_span(m: re.Match, page: int) -> tuple[int, int]:
    s = m.group()
    i = s.index(str(page)) if s.startswith(str(page)) else s.rindex(str(page))
    return m.start() + i, m.start() + i + len(str(page))


def strip_page_marker(text: str, page: int, *, check_tail: bool = False) -> tuple[str, list[str]]:
    """(지운 뒤 글, 지운 글자 목록). 쪽 번호 N이 앞(옵션: 끝) 20자 안에 홀로 있을 때만 지운다."""
    removed: list[str] = []
    pat = _pattern(page)
    for m in pat.finditer(text):
        if _num_span(m, page)[1] <= WINDOW:
            after = re.match(_BREAK, text[m.end():])
            if not after:  # 글 끝에 홀로 있는 숫자는 앞 쪽 표시가 아니다(짧은 글의 끝 표시는 check_tail로)
                continue
            end = m.end() + len(after.group())
            removed.append(text[m.start():end])
            text = text[:m.start()] + text[end:]
            break
    if check_tail:
        for m in pat.finditer(text):
            if _num_span(m, page)[0] >= len(text) - WINDOW:
                before = re.search(_BREAK + r"\Z", text[:m.start()])
                start = before.start() if before else m.start()
                removed.append(text[start:m.end()])
                text = text[:start] + text[m.end():]
                break
    return text, removed


def count_remaining_markers(text: str, page: int) -> int:
    """자기 쪽 번호만 있는 줄 + '한국어 N'·'N 한국어'의 수."""
    lines = sum(1 for line in text.splitlines() if line.strip() == str(page))
    return lines + len(_pattern(page, attached_only=True).findall(text))
