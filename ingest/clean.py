import re

CID = re.compile(r"\(cid:\d+\)")
UNTITLED = re.compile(r"^Untitled-\d+\s+\d+(?:\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})?$")  # 49쪽은 날짜 없이 남는다
SUBTITLE = re.compile(r"^\[.*\]$")


def _is_doubled(line: str) -> bool:
    # 글자가 두 번씩 반복된 깨진 바닥글: "UUnnttiittlleedd--11 1122"
    s = line.replace(" ", "")
    return len(s) >= 8 and len(s) % 2 == 0 and all(s[i] == s[i + 1] for i in range(0, len(s), 2))


def clean_text(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = CID.sub("", line).rstrip()
        if line.strip() and not stripped.strip():
            continue  # (cid:…)만 있던 줄
        if _is_doubled(stripped) or UNTITLED.match(stripped.strip()):
            continue
        kept.append(stripped)
    return "\n".join(kept)


def drop_out_of_scope(text: str, keywords: list[str]) -> tuple[str, int]:
    if not keywords:
        return text, 0
    has_kw = lambda s: any(k in s for k in keywords)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    kept, dropped, skipping = [], 0, False
    for p in paragraphs:
        first = p.strip().splitlines()[0].strip()
        if SUBTITLE.match(first):
            # 키워드가 든 [소제목]부터 다음 [소제목] 전까지 통째로 뺀다 (결정기록 014, LC1 블록 포함)
            skipping = has_kw(first)
        if skipping or has_kw(p):
            dropped += 1
            continue
        kept.append(p)
    return "\n\n".join(kept), dropped
