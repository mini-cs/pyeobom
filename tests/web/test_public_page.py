import re
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[2] / "public"
TITLE = "펴봄 — 가전 설명서, 대신 펴 봐 드려요"
SUBTITLE = "공식 설명서에서 근거를 찾아 페이지와 함께 알려 드려요"
FOOTER = "비영리 학습용 포트폴리오이며, 설명서 저작권은 각 제조사에 있습니다. 정확한 내용은 공식 설명서를 확인하세요."


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_head_has_exact_title_and_link_preview_text():
    html = read("index.html")
    assert f"<title>{TITLE}</title>" in html and '<html lang="ko">' in html
    assert f'<meta name="description" content="{SUBTITLE}">' in html
    assert f'<meta property="og:title" content="{TITLE}">' in html
    assert f'<meta property="og:description" content="{SUBTITLE}">' in html
    assert 'name="viewport"' in html


def test_intro_and_footer_copy_are_exact():
    html = read("index.html")
    for text in ["펴봄", "세탁기·에어컨, 설명서 대신 물어보세요", SUBTITLE,
                 "공식 설명서 근거", "근거 페이지 표시", "모르면 모른다고 해요", FOOTER]:
        assert text in html, text


def test_styles_use_only_design_tokens_for_colors():
    css = read("styles.css")
    root, rest = css.split("}", 1) if css.lstrip().startswith(":root") else ("", css)
    assert "--color-primary: #1F5E5B" in root   # 디자인 가이드 토큰을 그대로 씀
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rest), "색은 :root의 CSS 변수만 쓴다(디자인 가이드)"


def test_script_never_injects_api_text_as_html():
    js = read("app.js")
    assert "/api/models" in js and "/api/ask" in js
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js   # API 글자는 textContent로만 넣는다(XSS 방지)


def test_reduced_motion_disables_collapse_animation():
    css = read("styles.css")
    assert "prefers-reduced-motion: reduce" in css and "transition: none" in css


def test_examples_per_model_and_not_eval_questions():
    import csv
    import json
    js = read("app.js")
    block = re.search(r"const EXAMPLES = (\{.*?\});", js, re.S)[1]
    examples = json.loads(re.sub(r",(\s*[}\]])", r"\1", block))   # 끝 쉼표를 지우고 JSON으로 읽는다
    model_ids = {m["id"] for m in json.loads((PUBLIC.parent / "data" / "models.json").read_text(encoding="utf-8"))}
    assert set(examples) == model_ids and all(len(v) == 2 for v in examples.values())
    with (PUBLIC.parent / "evaluation" / "questions.csv").open(encoding="utf-8") as f:
        eval_questions = [r["question"] for r in csv.DictReader(f)]
    for q in (q for qs in examples.values() for q in qs):   # 평가 질문과 같거나 겹치는 문장은 예시로 쓰지 않는다
        assert not any(q in e or e in q for e in eval_questions), q
