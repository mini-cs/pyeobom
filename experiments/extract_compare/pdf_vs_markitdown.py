"""1차 비교: pdfplumber vs MarkItDown — 쪽 수, 깨진 바닥글, (cid:) 잡음 (결정기록 016)

사용법: python pdf_vs_markitdown.py <설명서.pdf> [...]
추출 글자는 out/에 쓴다(설명서 본문이 들어 있어 커밋하지 않는다).
"""
import re
import sys
import time
from pathlib import Path

import pdfplumber
from markitdown import MarkItDown

OUT = Path(__file__).parent / "out"
DOUBLED = re.compile(r"(?:([A-Za-z가-힣])\1){4,}")  # UUnnttiittlleedd 같은 반복 글자 줄
CID = re.compile(r"\(cid:\d+\)")


def metrics(text: str) -> str:
    lines = [l for l in text.splitlines() if l.strip()]
    doubled = [l for l in lines if DOUBLED.search(l)]
    body_cid = [l for l in lines if CID.search(l) and not DOUBLED.search(l)]
    return f"쪽(\f로 나눔)={len(text.split(chr(12)))} 글자={len(text)} 반복글자줄={len(doubled)} 본문cid줄={len(body_cid)}"


def main(paths: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    md = MarkItDown()
    for p in map(Path, paths):
        t = time.time()
        with pdfplumber.open(p) as pdf:
            pages = [pg.extract_text() or "" for pg in pdf.pages]
        plumber = "\f".join(pages)
        t1 = time.time() - t
        t = time.time()
        markitdown = md.convert(str(p)).text_content
        t2 = time.time() - t
        (OUT / f"{p.stem[:20]}.pdfplumber.txt").write_text(plumber, encoding="utf-8")
        (OUT / f"{p.stem[:20]}.markitdown.txt").write_text(markitdown, encoding="utf-8")
        print(f"{p.name}\t원본 쪽={len(pages)}")
        print(f"  pdfplumber ({t1:.1f}초)\t{metrics(plumber)}")
        print(f"  markitdown ({t2:.1f}초)\t{metrics(markitdown)}")


if __name__ == "__main__":
    main(sys.argv[1:])
