"""v1.7 Task 4: 0단계 탈락 검사 함수 (설계 6절). 쪽 글은 (쪽 번호, 평문)."""
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from ingest.clean import clean_text
from ingest.load import ROOT, load_documents
from ingest.pdf import extract_pages
from ingest.plaintext import clean_plain_page, markdown_to_plain

Pages = list[tuple[int, str]]

# 깨진 글자 판정 집합(pypdfium2에 먼저 센 뒤 바꾸지 않는다): U+FFFD, 사용자 정의 영역 U+E000~F8FF, \t\n\r 말고 C0 제어 문자
BROKEN_CHARS = frozenset(["\ufffd", *map(chr, range(0xE000, 0xF900)),
                          *(chr(c) for c in range(0x20) if chr(c) not in "\t\n\r")])


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def page_count_ok(tool: Pages, base: Pages) -> bool:
    return len(tool) == len(base)


def _picks(base: Pages) -> list[tuple[int, str]]:
    """쪽마다 그 설명서에 한 번만 나오는 15자 이상 줄 중 첫 번째."""
    lines = Counter(s for _, t in base for s in (x.strip() for x in t.splitlines()))
    out = []
    for p, t in base:
        pick = next((s for s in (x.strip() for x in t.splitlines()) if len(s) >= 15 and lines[s] == 1), None)
        if pick is not None:
            out.append((p, pick))
    return out


def page_alignment(tool: Pages, base: Pages) -> float:
    tool_text = {p: _squash(t) for p, t in tool}
    picks = _picks(base)
    hit = sum(_squash(s) in tool_text.get(p, "") for p, s in picks)
    return hit / len(picks) if picks else 0.0


_NORM = re.compile(r"[\s•·◦▪●■□\-*|\ufeff\u200b]")


def _norm(s: str) -> str:
    return _NORM.sub("", s)


def page_shift(tool: Pages, base: Pages) -> dict:
    """고른 줄을 도구 글 어디서든 찾고, 같은 쪽에서도 찾은 비율을 낸다 (⑫). 못 찾은 줄은 비율에서 뺀다."""
    tool_text = {p: _norm(t) for p, t in tool}
    picks = _picks(base)
    found = same = 0
    for p, s in picks:
        n = _norm(s)
        if any(n in t for t in tool_text.values()):
            found += 1
            same += n in tool_text.get(p, "")
    return {"picked": len(picks), "found": found, "same": same, "not_found": len(picks) - found,
            "ratio": same / found if found else 0.0}


def _has_in_order(text: str, patterns: list[str]) -> bool:
    pos = 0
    for pat in patterns:
        m = re.compile(pat).search(text, pos)
        if not m:
            return False
        pos = m.end()
    return True


def _page(pages: Pages, n: int) -> str:
    return next((t for p, t in pages if p == n), "")


def decimal_ok(samsung: Pages) -> bool:
    t = _page(samsung, 38)
    return bool(re.search(r"(?<!\d)4\.0\s*kg", t)) and "4 0 kg" not in t


def table_rows_ok(lg_drum: Pages) -> bool:
    return _has_in_order(_page(lg_drum, 16), [r"40\s+15\s+30", r"50\s+20\s+35", r"60\s+25\s+45"])


def broken_lines(pages: Pages) -> int:
    return sum("(cid:" in ln or any(c in BROKEN_CHARS for c in ln) for _, t in pages for ln in t.splitlines())


def char_ratio(tool: Pages, base: Pages) -> float:
    n = lambda pages: sum(len(_squash(t)) for _, t in pages)
    return n(tool) / n(base)


def _match(a: str, b: str) -> bool:
    """한쪽이 다른 쪽에 들어 있고, 짧은 쪽이 2자 이상이며 긴 쪽의 절반 이상일 때만 맞다."""
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 2 and len(short) * 2 >= len(long_) and short in long_


def heading_hit_rate(headings: dict[int, list[str]], toc: list[tuple[int, str]]) -> float:
    if not toc:
        raise ValueError("목차가 비어 있다 (목차 없는 설명서는 호출하지 않는다)")
    hits = 0
    for page, item in toc:
        i = _squash(item)
        hits += any(_match(_squash(h), i) for h in headings.get(page, []))
    return hits / len(toc)


_LEFTOVER = {
    "html_tag": re.compile(r"</?[A-Za-z][^<>\n]*>"),
    "backslash_punct": re.compile(r"\\[!-/:-@\[-`{-~]"),
    "md_link": re.compile(r"(?<!!)\[[^\]\n]*\]\([^)\n]*\)"),
    "strike": re.compile(r"~~.+?~~"),
    # 아래는 기록만 한다 (멈춤에 넣지 않음)
    "star_wrapped": re.compile(r"(?<![\w*])\*(?![\s*])[^*\n]+?(?<![\s*])\*(?![\w*])"),
    "underscore_wrapped": re.compile(r"(?<!\w)_(?![\s_])[^_\n]+?(?<![\s_])_(?!\w)"),
    "backslash_latex": re.compile(r"\\[A-Za-z]"),
    "unclosed_lt": re.compile(r"</?[A-Za-z](?![^<>\n]*>)"),
}
STOP_KEYS = ("html_tag", "backslash_punct", "md_link", "strike")


def count_leftovers(text: str) -> dict[str, int]:
    """markdown_to_plain 뒤에도 남은 기호를 종류별 개수로만 센다 (R21, ⑨)."""
    return {k: len(rx.findall(text)) for k, rx in _LEFTOVER.items()}


# ---- 실행 (설계 6절 0단계 / 계획 Task 4 Step 7) ----
EXTRACT = ROOT / "measure" / "out" / "v17" / "extract"
SAMSUNG, DRUM = "manual-samsung-wd90h25", "manual-lg-fx25"
DOCS = (SAMSUNG, DRUM, "manual-lg-sq06fa1wds")
BASE_TOOL = "pypdfium2"


def _load(folder: Path, doc: str) -> list[tuple[int, str]]:
    return [(i["page"], i["markdown"]) for i in json.loads((folder / f"{doc}.json").read_text(encoding="utf-8"))]


def _complete_tools(root: Path) -> tuple[list[str], list[str]]:
    tools = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name != BASE_TOOL)
    ok = [t for t in tools if all((root / t / f"{d}.json").exists() for d in DOCS)]
    return ok, [t for t in tools if t not in ok]


def baseline(root: Path = EXTRACT) -> dict:
    out = root / BASE_TOOL
    out.mkdir(parents=True, exist_ok=True)
    seconds, pages = {}, {}
    for doc in (d for d in load_documents() if d["doc_type"] == "manual"):
        t0 = time.time()
        got = extract_pages(str(ROOT / doc["file"]))
        seconds[doc["id"]] = round(time.time() - t0, 2)
        pages[doc["id"]] = len(got)
        (out / f"{doc['id']}.json").write_text(
            json.dumps([{"page": p, "markdown": t} for p, t in got], ensure_ascii=False), encoding="utf-8")
    (out / "run.json").write_text(json.dumps({"seconds": seconds}), encoding="utf-8")
    return {"seconds": seconds, "pages": pages}


def run_leftover(root: Path = EXTRACT) -> bool:
    """도구 x 설명서별 남은 기호 개수(0 아닌 것만, 글자는 내지 않는다). STOP_KEYS가 하나라도 있으면 True."""
    tools, _ = _complete_tools(root)
    found = False
    for tool in tools:
        total = Counter()
        for doc in DOCS:
            c = Counter()
            for _, md in _load(root / tool, doc):
                c.update({k: v for k, v in count_leftovers(markdown_to_plain(md).text).items() if v})
            print(f"{tool} / {doc}: {dict(c) or 0}")
            total.update(c)
        print(f"{tool} 합계: {dict(total) or 0}")
        found |= any(total[k] for k in STOP_KEYS)
    if found:
        print("멈춤: 남은 기호 있음")
    return found


def run_gate(root: Path = EXTRACT, toc_path: Path = ROOT / "measure" / "v17_toc.json",
             out_path: Path = EXTRACT.parent / "gate.json") -> dict:
    toc = json.loads(toc_path.read_text(encoding="utf-8"))
    base = {d: [(p, clean_text(m)) for p, m in _load(root / BASE_TOOL, d)] for d in DOCS}
    tools, missing = _complete_tools(root)
    result: dict = {"not_run": missing}
    for tool in tools:
        plain = {d: [(p, clean_plain_page(markdown_to_plain(m))) for p, m in _load(root / tool, d)] for d in DOCS}  # R22
        pages = {d: [(p, pp.text) for p, pp in plain[d]] for d in DOCS}
        m: dict = {}
        for d in DOCS:
            heads = {p: [h for _, h in pp.headings] for p, pp in plain[d]}
            t = [(p, x) for p, x in toc.get(d, [])]
            m[d] = {"page_count_ok": page_count_ok(pages[d], base[d]),
                    "page_alignment": page_alignment(pages[d], base[d]),  # 기록용
                    "page_shift": (ps := page_shift(pages[d], base[d])),
                    "page_shift_undecidable": ps["found"] < 10,
                    "char_ratio": char_ratio(pages[d], base[d]),
                    "broken_lines": broken_lines(pages[d]), "base_broken_lines": broken_lines(base[d]),
                    "heading_hit_rate": heading_hit_rate(heads, t) if t else None}
        run_info = root / tool / "run.json"
        run = json.loads(run_info.read_text(encoding="utf-8")) if run_info.exists() else {}
        secs = run.get("run_seconds", {})  # 마지막으로 돈 장치 기준
        secs = secs.values() if isinstance(secs, dict) else [secs]
        eliminated = [n for n, bad in (
            (1, bool(run.get("excluded")) or any(s > 1800 for s in secs)),
            (2, any(not x["page_count_ok"] or x["page_shift_undecidable"] or x["page_shift"]["ratio"] < 0.9
                    for x in m.values())),
            (3, not decimal_ok(pages[SAMSUNG])),
            (4, not table_rows_ok(pages[DRUM])),
            (5, any(x["broken_lines"] > x["base_broken_lines"] for x in m.values())),
            (6, any(x["char_ratio"] < 0.9 for x in m.values()))) if bad]
        rates = [x["heading_hit_rate"] for x in m.values()]
        counted = [r for r in rates if r is not None]  # 목차 없는 설명서는 빼고 센다 (설계 6절)
        result[tool] = {"manuals": m, "eliminated": eliminated, "run": run,
                        "heading_skipped_no_toc": [d for d, r in zip(DOCS, rates) if r is None],
                        "heading_tool": bool(counted) and all(r >= 0.70 for r in counted)}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main() -> None:
    if "--baseline" in sys.argv:
        r = baseline()
        for d in DOCS:
            print(f"{d}: 쪽 {r['pages'][d]}, {r['seconds'][d]}초")
    elif "--leftover" in sys.argv:
        sys.exit(1 if run_leftover() else 0)
    else:
        r = run_gate()
        for tool, v in r.items():
            if tool == "not_run":
                print(f"돌리지 않음(3종 JSON 없음): {v}")
                continue
            r_ = v["run"]
            print(f"{tool}: 탈락 조건 {v['eliminated'] or '없음'}, 제목을 잡는 도구 {v['heading_tool']}, "
                  f"{'GPU 필요, ' if r_.get('gpu_required') else ''}장치 {r_.get('device')}, 설치 {r_.get('install_seconds')}초, "
                  f"모델 내려받기 {r_.get('model_download_seconds')}초, 실행 {r_.get('run_seconds')}")
            for d, x in v["manuals"].items():
                hr = x["heading_hit_rate"]
                print(f"  {d}: 쪽수 {x['page_count_ok']} 정렬 {x['page_alignment']:.3f} 글자비 {x['char_ratio']:.3f} "
                      f"쪽밀림 {x['page_shift']['same']}/{x['page_shift']['found']} 못찾음 {x['page_shift']['not_found']}"
                      f"{' 판단불가' if x['page_shift_undecidable'] else ''} "
                      f"깨진줄 {x['broken_lines']}/기준 {x['base_broken_lines']} 제목적중 "
                      f"{'목차 없음, 뺌' if hr is None else format(hr, '.3f')}")


if __name__ == "__main__":
    main()
