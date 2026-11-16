"""Unstructured 쪽별 마크다운 추출: python run_unstructured.py <PDF> <출력 json>
partition_pdf(strategy="hi_res"), 쪽 번호는 element.metadata.page_number(native)."""
import collections, json, sys, time

pdf, out = sys.argv[1], sys.argv[2]

import pypdfium2
from unstructured.partition.pdf import partition_pdf

n = len(pypdfium2.PdfDocument(pdf))
t = time.time()
els = partition_pdf(filename=pdf, strategy="hi_res")
sec = time.time() - t
cats = collections.Counter(e.category for e in els)
nopage = sum(1 for e in els if e.metadata.page_number is None)
pn = [e.metadata.page_number for e in els if e.metadata.page_number is not None]
assert nopage == 0, f"elements without page_number: {nopage}"
assert 1 <= min(pn) and max(pn) <= n, "page numbering out of range"
by = collections.defaultdict(list)
for e in els:
    by[e.metadata.page_number].append("# " + e.text if e.category == "Title" else e.text)
res = [{"page": p, "markdown": "\n".join(by.get(p, []))} for p in range(1, n + 1)]
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"pages={n} seconds={sec:.1f} elements={len(els)} no_page_number={nopage} "
      f"page_range={min(pn)}-{max(pn)} pages_with_elements={len(set(pn))} "
      f"Title={cats.get('Title', 0)} categories={dict(cats)} "
      f"chars_nospace={sum(len(''.join(r['markdown'].split())) for r in res)}")
