"""Docling 쪽별 마크다운 추출: python run_docling.py <PDF> <출력 json> [cpu|cuda]"""
import json, sys, time

pdf, out = sys.argv[1], sys.argv[2]
device = sys.argv[3] if len(sys.argv) > 3 else "cpu"

from docling.document_converter import DocumentConverter

if device != "cpu":
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    opts = PdfPipelineOptions(accelerator_options=AcceleratorOptions(device=device))
    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
else:
    conv = DocumentConverter()  # 기본 설정

t = time.time()
doc = conv.convert(pdf).document
sec = time.time() - t
n = max(doc.pages.keys())
pages = sorted(doc.pages.keys())
assert pages == list(range(1, n + 1)), "page numbering mismatch"  # 1부터, 빠짐없음
res = [{"page": p, "markdown": doc.export_to_markdown(page_no=p)} for p in pages]
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"pages={n} seconds={sec:.1f} chars_nospace={sum(len(''.join(r['markdown'].split())) for r in res)}")
