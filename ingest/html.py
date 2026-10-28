import re

from bs4 import BeautifulSoup

BLOCK_TAGS = ["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "dt", "dd", "table", "ul", "ol", "section"]
BREAK = "\x00"  # 문단 경계 표시


def extract_html(path: str, content_selector: str, title: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    content = soup.select_one(content_selector)
    if content is None:
        raise ValueError(f"본문 영역을 찾지 못함: {content_selector} ({path})")
    for el in content.select("script, style, noscript, button"):
        el.decompose()
    # 탭 이름이 <select>에만 있으면(LG) 각 탭 내용 앞에 붙인다. 숨은 탭도 글자는 그대로 읽는다(textContent 기준)
    labels = [o.get_text(" ", strip=True) for o in content.select("select option")]
    panels = content.select("[role=tabpanel]")
    if labels and len(labels) == len(panels):
        for label, panel in zip(labels, panels):
            panel.insert(0, f"{BREAK}{label}{BREAK}")
    for el in content.select("select"):
        el.decompose()
    for el in content.find_all(BLOCK_TAGS):
        el.insert_before(BREAK)
        el.insert_after(BREAK)
    for br in content.find_all("br"):
        br.replace_with("\n")
    paragraphs = []
    for part in content.get_text("").split(BREAK):
        lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in part.split("\n")]
        text = "\n".join(line for line in lines if line)
        if text:
            paragraphs.append(text)
    return "\n\n".join([title, *paragraphs])
