import pypdfium2 as pdfium


def extract_pages(pdf_path: str) -> list[tuple[int, str]]:
    # pypdfium2: pdfplumber와 달리 소수점("4.0 kg")을 지키고 2단 표를 칸 순서대로 뽑는다 (결정기록 016 수정)
    doc = pdfium.PdfDocument(pdf_path)
    try:
        return [(i + 1, doc[i].get_textpage().get_text_range().replace("\r\n", "\n").replace("\r", "\n"))
                for i in range(len(doc))]
    finally:
        doc.close()
