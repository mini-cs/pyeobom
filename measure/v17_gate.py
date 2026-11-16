"""v1.7 Task 4: 0단계 탈락 검사 함수 (설계 6절). 쪽 글은 (쪽 번호, 평문)."""
import re
from collections import Counter

Pages = list[tuple[int, str]]

# 깨진 글자 판정 집합(pypdfium2에 먼저 센 뒤 바꾸지 않는다): U+FFFD, 사용자 정의 영역 U+E000~F8FF, \t\n\r 말고 C0 제어 문자
BROKEN_CHARS = frozenset(["\ufffd", *map(chr, range(0xE000, 0xF900)),
                          *(chr(c) for c in range(0x20) if chr(c) not in "\t\n\r")])


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def page_count_ok(tool: Pages, base: Pages) -> bool:
    return len(tool) == len(base)


def page_alignment(tool: Pages, base: Pages) -> float:
    lines = Counter(s for _, t in base for s in (x.strip() for x in t.splitlines()))
    tool_text = {p: _squash(t) for p, t in tool}
    hit = total = 0
    for p, t in base:
        pick = next((s for s in (x.strip() for x in t.splitlines()) if len(s) >= 15 and lines[s] == 1), None)
        if pick is None:
            continue
        total += 1
        hit += _squash(pick) in tool_text.get(p, "")
    return hit / total if total else 0.0


def _has_in_order(text: str, patterns: list[str]) -> bool:
    pos = 0
    for pat in patterns:
        m = re.compile(pat).search(text, pos)
        if not m:
            return False
        pos = m.end()
    return True


def _page(pages: Pages, n: int) -> str:
    return next((t for p, t in pages if p == n), "")


def decimal_ok(samsung: Pages) -> bool:
    t = _page(samsung, 38)
    return "4.0 kg" in t and "4 0 kg" not in t


def table_rows_ok(lg_drum: Pages) -> bool:
    return _has_in_order(_page(lg_drum, 16), [r"40\s+15\s+30", r"50\s+20\s+35", r"60\s+25\s+45"])


def broken_lines(pages: Pages) -> int:
    return sum("(cid:" in ln or any(c in BROKEN_CHARS for c in ln) for _, t in pages for ln in t.splitlines())


def char_ratio(tool: Pages, base: Pages) -> float:
    n = lambda pages: sum(len(_squash(t)) for _, t in pages)
    return n(tool) / n(base)


def heading_hit_rate(headings: dict[int, list[str]], toc: list[tuple[int, str]]) -> float:
    if not toc:
        raise ValueError("목차가 비어 있다 (목차 없는 설명서는 호출하지 않는다)")
    hits = 0
    for page, item in toc:
        i = _squash(item)
        hits += any((s := _squash(h)) and (s in i or i in s) for h in headings.get(page, []))
    return hits / len(toc)
