"""pymupdf4llm 쪽별 마크다운 추출: python run_pymupdf4llm.py <PDF> <출력 json>"""
import json, sys, time
import pymupdf, pymupdf4llm

pdf, out = sys.argv[1], sys.argv[2]
doc = pymupdf.open(pdf)
t = time.time()
chunks = pymupdf4llm.to_markdown(doc, page_chunks=True)  # 바꾼 옵션: 쪽별 출력
sec = time.time() - t
nums = [c["metadata"].get("page_number", c["metadata"].get("page")) for c in chunks]
print("page keys", list(chunks[0]["metadata"].keys()), "first/last", nums[0], nums[-1], "n", len(chunks), "pages", len(doc))
# 쪽 번호는 metadata에서 확인한 값(1부터)을 쓰고 PDF 쪽 순서와 같은지 검증
assert len(chunks) == len(doc) and nums == list(range(1, len(doc) + 1)), "page numbering mismatch"
res = [{"page": n, "markdown": c["text"]} for n, c in zip(nums, chunks)]
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"seconds={sec:.1f} chars_nospace={sum(len(''.join(r['markdown'].split())) for r in res)}")
