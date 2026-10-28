"""2차 비교: pdfplumber vs pypdfium2 — 쪽 수, 소수점 유지, 바닥글, (cid:) 잡음, 추출 시간 (결정기록 016 수정)

사용법: python pdf_vs_pypdfium2.py <설명서.pdf> [...]
추출 글자는 out/에 쓴다(커밋하지 않는다). 삼성 38쪽·LG 드럼 16쪽은 out/의 결과에서 직접 확인한다.
"""
import re
import sys
import time
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium

OUT = Path(__file__).parent / "out"
DEC = re.compile(r"\d\.\d ?kg")      # 소수점 유지
SPLIT = re.compile(r"\d \d ?kg")     # 소수점 손실 ("4.0 kg" → "4 0 kg")
DOUBLED = re.compile(r"(?:([A-Za-z가-힣])\1){4,}")
CID = re.compile(r"\(cid:\d+\)")


def by_pdfplumber(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [pg.extract_text() or "" for pg in pdf.pages]


def by_pypdfium2(path: Path) -> list[str]:
    doc = pdfium.PdfDocument(path)
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


def main(paths: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    for p in map(Path, paths):
        for tool, extract in (("pdfplumber", by_pdfplumber), ("pypdfium2", by_pypdfium2)):
            t = time.time()
            pages = extract(p)
            dt = time.time() - t
            (OUT / f"{p.stem[:20]}.{tool}.txt").write_text("\f".join(pages), encoding="utf-8")
            text = "\n".join(pages)
            lines = text.splitlines()
            print(f"{p.name[:30]}\t{tool}\t쪽={len(pages)}\t소수점유지={len(DEC.findall(text))}\t"
                  f"소수점손실={len(SPLIT.findall(text))}\t반복글자줄={sum(bool(DOUBLED.search(l)) for l in lines)}\t"
                  f"Untitled줄={sum('Untitled' in l for l in lines)}\tcid줄={sum(bool(CID.search(l)) for l in lines)}\t{dt:.1f}초")


if __name__ == "__main__":
    main(sys.argv[1:])
