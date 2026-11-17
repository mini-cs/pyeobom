"""소제목 단위 자르기 (v1.7 2단계, 설계 6절). 숫자 800·100·100은 고정. 글을 덧붙이지 않는다."""
from ingest.chunk import chunk_pages
from ingest.plaintext import PlainPage


def _spans(pp: PlainPage, min_chars: int) -> list[tuple[int, int]]:
    cuts = sorted({0, *(p for p, _ in pp.headings if 0 <= p < len(pp.text))}) + [len(pp.text)]
    merged: list[tuple[int, int]] = []
    a = None
    for s, e in zip(cuts, cuts[1:]):
        a = s if a is None else a
        if len(pp.text[a:e].strip()) >= min_chars:
            merged.append((a, e))
            a = None
    if a is not None:  # 짧은 마지막 절은 앞 절과, 절이 하나뿐이면 그대로
        merged[-1:] = [(merged[-1][0], len(pp.text))] if merged else [(a, len(pp.text))]
    return merged


def chunk_sections(pages: list[tuple[int, PlainPage]], max_chars: int = 800, overlap: int = 100,
                   min_chars: int = 100) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for page, pp in pages:
        for a, b in _spans(pp, min_chars):
            out += chunk_pages([(page, pp.text[a:b])], max_chars, overlap)
    return out
