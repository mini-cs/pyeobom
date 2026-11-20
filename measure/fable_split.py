"""Fable 분할 실험 (설계 `docs/superpowers/specs/2026-11-19-fable-split-design.md` 5-2·5-3).

Fable 답(위치만)을 읽어 운영과 같은 쪽 글에 자를 위치를 붙인다. 읽는 규칙(`parse_*`, `normalize_alnum`,
`locate_start`의 key_len=12·min_len=4)은 Fable 답을 받기 전에 고정했다. 답을 본 뒤 고치지 않는다(계획 Global Constraints).
"""
import hashlib
import json
import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ingest.load import ROOT
from ingest.plaintext import PlainPage
from measure.v17_bundle import manual_pages_from_pypdfium2
from measure.v17_gate import DOCS, EXTRACT, _load

FABLE = ROOT / "measure" / "out" / "fable"  # git 밖: 줄 번호 파일·Fable 답 원문·자를 위치
ELIMINATE_OVER = 0.10
_LINE_ITEM = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")
_PDF_ITEM = re.compile(r"^\s*(\d+)\s*\|\s*(\S.*?)\s*$")
_ALNUM = re.compile(r"[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]")


def numbered_lines(pages: list[tuple[int, PlainPage]]) -> tuple[str, dict[tuple[int, int], int]]:
    """(파일 글, (쪽, 줄) → 쪽 글 안 시작 위치). 공백뿐이 아닌 줄만 쪽마다 1부터 번호."""
    out, index = [], {}
    for page, pp in pages:
        n, off = 0, 0
        for line in pp.text.split("\n"):
            if line.strip():
                n += 1
                index[(page, n)] = off
                out.append(f"{page}:{n}\t{line}")
            off += len(line) + 1
    return "".join(s + "\n" for s in out), index


def text_hash(pages: list[tuple[int, PlainPage]]) -> str:
    return hashlib.sha256("".join(f"{p}\n{pp.text}\n" for p, pp in pages).encode("utf-8")).hexdigest()


@dataclass
class Parsed:
    items: list
    received: int
    bad_format: int


def _block_lines(text: str) -> list[str]:
    """모든 ``` 코드 블록 안의 공백 아닌 줄. 닫히지 않은 마지막 블록은 글 끝까지."""
    inside, lines = False, []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip().startswith("```"):
            inside = not inside
        elif inside and line.strip():
            lines.append(line)
    return lines


def _parse(text: str, pattern: re.Pattern, convert) -> Parsed:
    lines = _block_lines(text)
    found = [convert(m) for m in map(pattern.match, lines) if m]
    return Parsed(items=sorted(set(found)), received=len(lines), bad_format=len(lines) - len(found))


def parse_line_answer(text: str) -> Parsed:
    return _parse(text, _LINE_ITEM, lambda m: (int(m[1]), int(m[2])))


def parse_pdf_answer(text: str) -> Parsed:
    return _parse(text, _PDF_ITEM, lambda m: (int(m[1]), m[2]))


def normalize_alnum(s: str) -> str:
    return "".join(_ALNUM.findall(unicodedata.normalize("NFKC", s)))


def locate_start(page_text: str, start: str, key_len: int = 12, min_len: int = 4) -> int | None:
    key = normalize_alnum(start)[:key_len]
    if len(key) < min_len:
        return None
    norm, pos = [], []  # 정리한 글자마다 원래 쪽 글 위치
    for i, ch in enumerate(page_text):
        for c in normalize_alnum(ch):
            norm.append(c)
            pos.append(i)
    at = "".join(norm).find(key)
    return None if at < 0 else pos[at]


def cuts_from_lines(index: dict[tuple[int, int], int], items: list[tuple[int, int]]) -> tuple[dict[int, list[int]], int]:
    cuts: dict[int, list[int]] = {}
    missing = 0
    for page, line in items:
        if (page, line) in index:
            cuts.setdefault(page, []).append(index[(page, line)])
        else:
            missing += 1
    return cuts, missing


def cuts_from_pdf(pages: list[tuple[int, PlainPage]], items: list[tuple[int, str]]) -> tuple[dict[int, list[int]], int]:
    texts = {p: pp.text for p, pp in pages}
    cuts: dict[int, list[int]] = {}
    missing = 0
    for page, start in items:
        off = locate_start(texts[page], start) if page in texts else None
        if off is None:
            missing += 1
        else:
            cuts.setdefault(page, []).append(off)
    return cuts, missing


def with_cuts(pages: list[tuple[int, PlainPage]], cuts: dict[int, list[int]]) -> list[tuple[int, PlainPage]]:
    return [(p, PlainPage(pp.text, [(off, "") for off in sorted(set(cuts.get(p, [])))])) for p, pp in pages]


def dropped_ratio(parsed: Parsed, missing: int) -> float:
    if parsed.received == 0:
        raise ValueError("답 전체를 읽을 수 없음")
    return (parsed.bad_format + missing) / parsed.received


def base_pages(root: Path = EXTRACT) -> dict[str, list[tuple[int, PlainPage]]]:
    """운영·strip_800과 같은 쪽 글(pypdfium2 → clean_text → 쪽 표시 지우기)."""
    return manual_pages_from_pypdfium2({d: _load(root / "pypdfium2", d) for d in DOCS})


def write_lines(out: Path = FABLE / "input") -> dict:
    """설명서마다 `<doc_id>-lines.txt`(LF)와 meta.json. 글자는 출력하지 않는다."""
    pages = base_pages()
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    for d in DOCS:
        text, index = numbered_lines(pages[d])
        (out / f"{d}-lines.txt").write_text(text, encoding="utf-8", newline="\n")
        meta[d] = {"text_hash": text_hash(pages[d]), "pages": len(pages[d]), "lines": len(index), "chars": len(text)}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def build_cuts(bundle: Literal["fable_lines", "fable_pdf"], answers: Path = FABLE / "answers",
               out: Path = FABLE / "cuts") -> dict:
    if bundle not in ("fable_lines", "fable_pdf"):
        raise SystemExit(f"모르는 한 벌 이름이라 멈춤: {bundle}")
    pages = base_pages()
    meta = json.loads((FABLE / "input" / "meta.json").read_text(encoding="utf-8"))
    hashes = {d: text_hash(pages[d]) for d in DOCS}
    changed = [d for d in DOCS if meta.get(d, {}).get("text_hash") != hashes[d]]
    if changed:
        raise SystemExit(f"줄 번호 파일을 만든 글과 지금 글이 달라 멈춤: {changed}")
    cuts, stats = {}, {}
    for d in DOCS:
        path = answers / bundle / f"{d}.md"
        if not path.exists():
            raise SystemExit(f"Fable 답 파일이 없어 멈춤: {path}")
        text = path.read_text(encoding="utf-8")
        if bundle == "fable_lines":
            parsed = parse_line_answer(text)
            cuts[d], missing = cuts_from_lines(numbered_lines(pages[d])[1], parsed.items)
        else:
            parsed = parse_pdf_answer(text)
            cuts[d], missing = cuts_from_pdf(pages[d], parsed.items)
        ratio = dropped_ratio(parsed, missing)  # 읽을 항목이 0이면 ValueError(다시 돌리기 대상)
        stats[d] = {"received": parsed.received, "bad_format": parsed.bad_format, "missing": missing,
                    "ratio": round(ratio, 4), "eliminated": ratio > ELIMINATE_OVER}
    result = {"cuts": cuts, "stats": stats, "eliminated": any(s["eliminated"] for s in stats.values()),
              "text_hash": hashes}
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{bundle}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def fable_pages(bundle: str) -> Callable[[dict], dict]:
    """v17_stage1.BUNDLES의 두 번째 자리: raw → 운영과 같은 쪽 글 → cuts/<bundle>.json의 자를 위치."""
    def make(raw: dict) -> dict:
        data = json.loads((FABLE / "cuts" / f"{bundle}.json").read_text(encoding="utf-8"))
        if data["eliminated"]:
            raise SystemExit(f"{bundle}은 탈락이라 멈춤: {data['stats']}")
        return {d: with_cuts(pages, {int(p): offs for p, offs in data["cuts"].get(d, {}).items()})
                for d, pages in manual_pages_from_pypdfium2(raw).items()}
    return make


def main() -> None:
    args = sys.argv[1:]
    if args == ["lines"]:
        print(json.dumps(write_lines(), ensure_ascii=False, indent=1))
    elif len(args) == 2 and args[0] == "cuts":
        r = build_cuts(args[1])
        print(json.dumps({"stats": r["stats"], "eliminated": r["eliminated"]}, ensure_ascii=False, indent=1))
    else:
        raise SystemExit("사용법: python -m measure.fable_split lines | cuts <fable_lines|fable_pdf>")


if __name__ == "__main__":
    main()
