"""v1.7 Task 2: 쪽 표시 지우기를 설명서 3종 쪽 글에 돌려 보고 v1.6 셈법으로 다시 센다.
`python -m measure.v17_page_marker`. 지운 글자 전체는 measure/out/v17/page_marker/(git 제외), 화면에는 숫자·모양만 낸다."""
import json
import re
from collections import Counter

from ingest.chunk import chunk_pages
from ingest.clean import clean_text
from ingest.load import ROOT, load_documents
from ingest.page_marker import strip_page_marker
from ingest.pdf import extract_pages
from measure.v16_not_found import marker_shape, page_marker

OUT = ROOT / "measure" / "out" / "v17" / "page_marker"


def _count(pages) -> int:
    return sum(page_marker(c, p) for p, c in chunk_pages(pages, 800, 100))


def summarize(pages: list[tuple[int, str]]) -> dict:
    stripped, removed = [], []
    for p, t in pages:
        new, rm = strip_page_marker(t, p)
        stripped.append((p, new))
        if rm:
            removed.append({"page": p, "removed": rm})
    shapes = Counter(re.sub(rf"(?<!\d){item['page']}(?!\d)", "N", s.strip())
                     for item in removed for s in item["removed"])
    remaining = [(p, c) for p, c in chunk_pages(stripped, 800, 100) if page_marker(c, p)]
    return {"total_pages": len(pages), "removed_pages": len(removed), "shapes": dict(shapes), "removed": removed,
            "chunks": len(chunk_pages(stripped, 800, 100)), "chunks_before": len(chunk_pages(pages, 800, 100)),
            "before": _count(pages), "after": len(remaining), "remaining": remaining}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tot = Counter()
    for doc in (d for d in load_documents() if d["doc_type"] == "manual"):
        pages = [(p, clean_text(t)) for p, t in extract_pages(str(ROOT / doc["file"]))]
        r = summarize(pages)
        (OUT / f"{doc['id']}.json").write_text(json.dumps(r["removed"], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{doc['id']}: 쪽 {r['total_pages']}, 지운 쪽 {r['removed_pages']}, 모양 {r['shapes']}, "
              f"조각 {r['chunks_before']}→{r['chunks']}, v1.6 셈 {r['before']}→{r['after']}")
        for p, c in r["remaining"]:
            m = re.search(rf"(?<!\d){p}(?!\d)", c[:20])
            print(f"  남음: 쪽 {p}, 모양 {marker_shape(c, p)}, 뒤 글자 {c[m.end()] if m and m.end() < len(c) else ''!r}")
        tot.update(chunks=r["chunks_before"], before=r["before"], after=r["after"])
    print(f"합계: 조각 {tot['chunks']}, v1.6 셈 {tot['before']}→{tot['after']}")


if __name__ == "__main__":
    main()
