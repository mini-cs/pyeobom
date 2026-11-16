"""쪽 표시 지우기(v1.7 설계 6절). 운영 적재(ingest/clean.py)에는 연결하지 않는다."""
import re

from ingest.plaintext import PlainPage

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


def _strip(text: str, page: int, check_tail: bool) -> tuple[str, list[str], list[tuple[int, int]]]:
    """(지운 뒤 글, 지운 글자 목록, 지운 구간(원문 좌표)). 끝 검사는 앞에서 지운 것이 없을 때만 한다."""
    pat = _pattern(page)
    for m in pat.finditer(text):
        if _num_span(m, page)[1] <= WINDOW:
            after = re.match(_BREAK, text[m.end():])
            if not after:  # 글 끝에 홀로 있는 숫자는 앞 쪽 표시가 아니다(짧은 글의 끝 표시는 check_tail로)
                continue
            end = m.end() + len(after.group())
            return text[:m.start()] + text[end:], [text[m.start():end]], [(m.start(), end)]
    if check_tail:
        for m in pat.finditer(text):
            if _num_span(m, page)[0] >= len(text) - WINDOW:
                before = re.search(_BREAK + r"\Z", text[:m.start()])
                start = before.start() if before else m.start()
                return text[:start] + text[m.end():], [text[start:m.end()]], [(start, m.end())]
    return text, [], []


def strip_page_marker(text: str, page: int, *, check_tail: bool = False) -> tuple[str, list[str]]:
    """(지운 뒤 글, 지운 글자 목록). 쪽 번호 N이 앞(옵션: 앞에서 못 지웠을 때 끝) 20자 안에 홀로 있을 때만 지운다."""
    out, removed, _ = _strip(text, page, check_tail)
    return out, removed


def strip_plain_page(pp: PlainPage, page: int, *, check_tail: bool = False) -> tuple[PlainPage, list[str]]:
    """strip_page_marker를 PlainPage에 적용하고 제목 위치를 맞춘다.
    지운 구간과 글자 범위가 겹치는 제목은 버리고, 구간 뒤 제목은 지운 길이만큼 당긴다."""
    out, removed, spans = _strip(pp.text, page, check_tail)
    if not spans:
        return pp, removed
    s, e = spans[0]
    heads = []
    for pos, title in pp.headings:
        if pos + len(title) <= s:
            heads.append((pos, title))
        elif pos >= e:
            heads.append((pos - (e - s), title))
    return PlainPage(out, heads), removed


def count_remaining_markers(text: str, page: int) -> int:
    """자기 쪽 번호만 있는 줄 + '한국어 N'·'N 한국어'의 수."""
    lines = sum(1 for line in text.splitlines() if line.strip() == str(page))
    return lines + len(_pattern(page, attached_only=True).findall(text))
