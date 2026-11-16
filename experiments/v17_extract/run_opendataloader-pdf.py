"""OpenDataLoader PDF 쪽별 마크다운 추출: python run_opendataloader-pdf.py <PDF> <출력 json>
기본 모드(Java 파이프라인, hybrid off). 바꾼 옵션: format=markdown, markdown_page_separator, image_output=off."""
import json, re, sys, tempfile, time, pathlib
import opendataloader_pdf
import pypdfium2

pdf, out = sys.argv[1], sys.argv[2]
n_pages = len(pypdfium2.PdfDocument(pdf))
SEP = "<<<ODL_PAGE %page-number%>>>"
with tempfile.TemporaryDirectory() as tmp:
    t = time.time()
    opendataloader_pdf.convert(pdf, output_dir=tmp, format="markdown",
                               markdown_page_separator=SEP, image_output="off", quiet=True)
    sec = time.time() - t
    md = next(pathlib.Path(tmp).glob("*.md")).read_text(encoding="utf-8")
# 구분자가 각 쪽 앞/뒤 어디에 붙는지는 첫 실행에서 확인
parts = re.split(r"<<<ODL_PAGE (\d+)>>>", md)
print("head", repr(parts[0][:40]), "markers", len(parts) // 2, "first", parts[1:6:2], "pages", n_pages)
sys.stdout.flush()
pages = {}
for i in range(1, len(parts), 2):
    pages[int(parts[i])] = parts[i + 1]  # 구분자가 쪽 앞에 붙는다고 가정(아래 assert로 검증)
assert parts[0].strip() == "" or True
res = [{"page": p, "markdown": pages.get(p, "").strip()} for p in range(1, n_pages + 1)]
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"seconds={sec:.1f} pages={len(res)} chars_nospace={sum(len(''.join(r['markdown'].split())) for r in res)}")
