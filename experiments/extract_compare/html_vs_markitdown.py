"""HTML 비교: MarkItDown vs 본문 영역만 뽑기 — 글자 수, 사이트 잡음, LG 숨은 탭, 플렉스워시 문단 (결정기록 016)

사용법: python html_vs_markitdown.py <data/guides 폴더>
본문 영역: LG는 #viewContent, 삼성은 div.editor-view. 결과는 out/에 쓴다(커밋하지 않는다).
"""
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from markitdown import MarkItDown

OUT = Path(__file__).parent / "out"
NOISE = ["로그인", "회원가입", "개인정보처리방침", "이용약관", "사이트맵", "Copyright", "장바구니", "검색", "공유하기"]


def squash(s: str) -> str:
    return re.sub(r"[\s*_\[\]()#>|`\-]+", "", s)  # 공백과 마크다운 기호를 지워 문장 단위로 대조


def body_text(soup: BeautifulSoup, selector: str) -> str:
    el = soup.select_one(selector)
    for x in el.select("script,style,noscript,select,button"):
        x.decompose()
    lines = (l.strip() for l in el.get_text("\n").splitlines())
    return re.sub(r"\n\s*\n+", "\n\n", "\n".join(lines)).strip()


def main(guides: str) -> None:
    OUT.mkdir(exist_ok=True)
    md = MarkItDown()
    for f in sorted(Path(guides).glob("*.html")):
        raw = f.read_text(encoding="utf-8", errors="replace")
        selector = "#viewContent" if "-lg-" in f.name else "div.editor-view"
        a = md.convert(str(f)).text_content
        b = body_text(BeautifulSoup(raw, "html.parser"), selector)
        (OUT / f"{f.stem}.markitdown.md").write_text(a, encoding="utf-8")
        (OUT / f"{f.stem}.selector.txt").write_text(b, encoding="utf-8")
        print(f"\n## {f.name} ({selector})")
        for name, t in (("markitdown", a), ("본문만", b)):
            noise = {k: t.count(k) for k in NOISE if k in t}
            print(f"  {name:10s} 글자={len(t):6d} 잡음={noise} 플렉스워시={t.count('플렉스워시')}")
        panels = BeautifulSoup(raw, "html.parser").select(f"{selector} [id^=cs-tabpanel-]")
        if panels:
            sents = [squash(s) for p in panels for s in re.split(r"[.\n]", p.get_text()) if len(squash(s)) >= 12]
            print(f"  숨은 탭 {len(panels)}개 문장 {len(sents)}개: markitdown {sum(s in squash(a) for s in sents)}, "
                  f"본문만 {sum(s in squash(b) for s in sents)}")


if __name__ == "__main__":
    main(sys.argv[1])
