"""마크다운 → 평문 (v1.7 1단계, 규칙은 Task 6 측정 전 고정, 설계 6절).

규칙 (이 순서, 표준 라이브러리 re만):
0. 줄바꿈 CRLF·CR은 LF로 통일한다.
1. HTML 주석 `<!-- … -->`(여러 줄 포함)과 이미지 `![alt](url)`를 지운다.
   지운 줄은 연속 공백을 한 칸으로 줄이고 앞뒤 공백을 자른다(지운 줄만). 글자 없이 비면 줄째 버린다.
2. 줄 단위로: 제목 `#`~`######` + 공백은 기호만 지우고 글자는 남긴다.
   표 구분줄(`|---|:--:|`)은 줄째 버린다. 표 줄(`|`로 시작·끝)은 칸 글자를 strip하고 빈 칸은 버린 뒤 공백 한 칸으로 잇는다.
3. 굵게는 짝이 맞는 `**…**`만 지운다. 홑 `*`·`_`는 모델명에 쓰이므로 그대로 둔다.
   목록 기호 `-`·`•`와 숫자는 건드리지 않는다.
headings는 (최종 text 안 제목 시작 위치, 제목 글자).
"""
import re
from dataclasses import dataclass

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_SEPARATOR = re.compile(r"^\s*\|?(\s*:?-+:?\s*\|)+(\s*:?-+:?\s*)?$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


@dataclass(frozen=True)
class PlainPage:
    text: str
    headings: list[tuple[int, str]]


def markdown_to_plain(md: str) -> PlainPage:
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    md = _COMMENT.sub("\x00", md)  # 지운 자리를 표시해 두었다가 줄 단위로 공백 정리
    lines: list[str] = []
    headings: list[tuple[int, str]] = []
    pos = 0
    for line in md.split("\n"):
        touched = "\x00" in line or bool(_IMAGE.search(line))
        line = _IMAGE.sub("", line).replace("\x00", "")
        if touched:
            line = re.sub(r" {2,}", " ", line).strip()
            if not line:
                continue
        if "|" in line and _SEPARATOR.match(line):
            continue
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            line = " ".join(c for c in (c.strip() for c in s[1:-1].split("|")) if c)
        heading = _HEADING.match(line)
        if heading:
            line = heading.group(1)
        line = _BOLD.sub(r"\1", line)
        if heading:
            headings.append((pos, line))
        lines.append(line)
        pos += len(line) + 1
    return PlainPage("\n".join(lines), headings)
