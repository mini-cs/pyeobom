from pathlib import Path

import pytest

from ingest.chunk import chunk_pages
from ingest.pdf import extract_pages

SAMSUNG_PDF = Path(__file__).resolve().parents[2] / "data" / "manuals" / "OID140081_IB_WD80H-AD_7LCD_KO_260331.pdf"


@pytest.fixture
def samsung_pdf():
    if not SAMSUNG_PDF.exists():
        pytest.skip("설명서 PDF는 커밋하지 않아 이 컴퓨터에 있을 때만 확인한다")
    return str(SAMSUNG_PDF)


def test_chunks_never_cross_pages():
    pages = [(1, "가" * 1500), (2, "나" * 300)]
    chunks = chunk_pages(pages, max_chars=800, overlap=100)
    assert all(set(text) <= {"가"} for p, text in chunks if p == 1)
    assert [p for p, _ in chunks].count(2) == 1


def test_chunk_size_and_overlap():
    chunks = chunk_pages([(1, "".join(str(i % 10) for i in range(1500)))], 800, 100)
    assert all(len(t) <= 800 for _, t in chunks)
    assert chunks[0][1][-100:] == chunks[1][1][:100]


def test_blank_pages_are_skipped():
    assert chunk_pages([(1, "  \n ")]) == []


@pytest.mark.integration  # 로컬에 삼성 설명서 PDF가 있을 때만 실행
def test_samsung_manual_keeps_decimal_point(samsung_pdf):
    pages = extract_pages(samsung_pdf)
    assert [p for p, _ in pages] == list(range(1, 81))
    page38 = dict(pages)[38]
    assert "4.0 kg" in page38 and "4 0 kg" not in page38   # 소수점 손실 회귀 방지 (결정기록 016 수정)
