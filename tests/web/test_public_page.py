import json
import re
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[2] / "public"
TITLE = "펴봄 — 가전 설명서, 대신 펴 봐 드려요"
SUBTITLE = "공식 설명서에서 근거를 찾아 페이지와 함께 알려 드려요"
GUIDE = PUBLIC.parent / "docs" / "design" / "디자인-가이드.md"


def read(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_head_has_exact_title_and_link_preview_text():
    html = read("index.html")
    assert f"<title>{TITLE}</title>" in html and '<html lang="ko">' in html
    assert f'<meta name="description" content="{SUBTITLE}">' in html
    assert f'<meta property="og:title" content="{TITLE}">' in html
    assert f'<meta property="og:description" content="{SUBTITLE}">' in html
    assert 'name="viewport"' in html


def test_landing_and_footer_copy_are_exact():
    # v1.5 랜딩(설계 2절 ①, 시안 5번)과 카테고리·모델 화면 문구. 줄바꿈 위치는 시안 5번처럼 <br>로 고정
    html = re.sub(r"<br>\s*", " ", read("index.html"))
    for text in ["펴봄", "가전 설명서, 대신 펴 봐 드려요", "고른 모델의 공식 설명서에서 근거를 찾아 답해요.",
                 "근거 쪽을 보여 줘요", "설명서 몇 쪽인지와 원문을 함께",
                 "모르면 모른다고 해요", "설명서에 없으면 지어내지 않아요",
                 "개인정보는 적지 마세요", "적어도 AI에 보내기 전에 가려요", "시작하기",
                 "비영리 학습용 포트폴리오예요. 설명서 저작권은 각 제조사에 있어요.",
                 "어떤 가전이 궁금하세요?", "더 추가 예정",
                 "제품 그림은 AI로 그린 일러스트예요. 실제 제품과 다를 수 있어요."]:
        assert text in html, text


def test_styles_use_only_design_tokens_for_colors():
    css = read("styles.css")
    root, rest = css.split("}", 1) if css.lstrip().startswith(":root") else ("", css)
    assert "--color-text: #111111" in root   # 디자인 가이드 v1.5 토큰을 그대로 씀
    assert "--color-dot: #8C8C8C" in root   # 비활성 점 표시(누르는 버튼, 흰 바탕 3.36:1)
    assert re.search(r"\.dot::before \{[^}]*background: var\(--color-dot\)", rest)
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rest), "색은 :root의 CSS 변수만 쓴다(디자인 가이드)"


def declarations(block: str) -> dict:
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", block))


def test_root_tokens_match_design_guide_block():
    # 색·글꼴·크기·간격 토큰이 가이드 7절 CSS 블록과 같다(더 많지도 적지도 않게)
    guide = re.search(r"```css\n(:root \{.*?\})\n```", GUIDE.read_text(encoding="utf-8"), re.S)[1]
    root = read("styles.css").split("}", 1)[0]
    assert declarations(root) == declarations(guide)


def test_self_hosted_fonts_and_icons_with_licenses():
    # Pretendard 1.3.9 woff2-subset 공식 파일(결정기록 024 크기)과 Tabler 아이콘, 각 라이선스 원문
    sizes = {"Pretendard-Regular.subset.woff2": 267_096, "Pretendard-SemiBold.subset.woff2": 268_752,
             "Pretendard-Bold.subset.woff2": 270_784}
    for name, size in sizes.items():
        assert (PUBLIC / "fonts" / name).stat().st_size == size, name
    assert "Reserved Font Name Pretendard" in read("fonts/LICENSE.txt")
    assert "MIT License" in read("icons/LICENSE") and "Paweł Kuna" in read("icons/LICENSE")
    css = read("styles.css")
    assert "font-display: swap" in css
    urls = re.findall(r'url\("(/(?:fonts|icons)/[^"]+)"\)', css)
    assert {u for u in urls if u.startswith("/fonts/")} == {f"/fonts/{n}" for n in sizes}
    assert any(u.startswith("/icons/") for u in urls)
    for u in urls:   # CSS가 부르는 글꼴·아이콘 파일이 모두 있다
        assert (PUBLIC / u.lstrip("/")).is_file(), u


def test_script_never_injects_api_text_as_html():
    js = read("app.js")
    assert "/api/models" in js and "/api/ask" in js
    for path in PUBLIC.rglob("*.js"):   # public/ 아래 모든 .js(하위 폴더 포함)
        text = path.read_text(encoding="utf-8")
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text, path.name   # API 글자는 textContent로만 넣는다(XSS 방지)


def test_reduced_motion_block_turns_off_slide_fold_and_smooth_scroll():
    # 1차 소개 접기 대신 v1.5 움직임(서랍 슬라이드·이전 답 펼침 화살표·타일 넘기기). 실제 계산 값은 test_ui_flow에서 본다
    css = read("styles.css")
    block = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    for text in ["transition: none", "animation: none", "scroll-behavior: auto"]:
        assert text in block, text


def screen_examples() -> dict:
    # 채팅 추천 카드: public/js/examples.js의 {모델 id: [{question, hint}, ...]}
    block = re.search(r"export const EXAMPLES = (\{.*?\});", read("js/examples.js"), re.S)[1]
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", block))   # 끝 쉼표를 지우고 JSON으로 읽는다


def test_examples_per_model_and_not_eval_questions():
    import csv
    examples = screen_examples()
    model_ids = {m["id"] for m in json.loads((PUBLIC.parent / "data" / "models.json").read_text(encoding="utf-8"))}
    assert set(examples) == model_ids and all(len(v) == 2 for v in examples.values())
    for item in (i for items in examples.values() for i in items):   # 카드 첫 줄(질문)과 둘째 줄(짧은 화면 문구)
        assert set(item) == {"question", "hint"} and item["question"].strip() and item["hint"].strip(), item
    eval_questions = []
    for name in ("questions.csv", "followups.csv"):   # 연 평가 질문(30문항·새 세트). 확인용 세트는 열지 않는다
        with (PUBLIC.parent / "evaluation" / name).open(encoding="utf-8-sig") as f:
            eval_questions += [r["question"] for r in csv.DictReader(line for line in f if not line.startswith("#"))]
    for q in (i["question"] for items in examples.values() for i in items):   # 평가 질문과 같거나 겹치는 문장은 예시로 쓰지 않는다
        assert not any(q in e or e in q for e in eval_questions), q


def test_samsung_second_example_is_the_rechecked_sentence():
    # "물이 안 빠지고 5C가 떠요"는 2026-11-11 로컬 3회 모두 찾지 못함(인용 번호가 검색된 조각에 없어 검증에서 떨어짐)이라 바꿈.
    # 바꾼 문장은 로컬 3회 모두 찾음·72쪽 인용으로 확인(docs/평가/v15-ui.md "추천 카드 5C 재현 확인"). 다시 바꾸면 다시 확인한다
    assert screen_examples()["washer-samsung-wd90h25"][1] == {"question": "물이 안 빠지고 탈수가 안 돼요", "hint": "원인과 해결 방법"}


def test_chat_copy_is_exact():
    # 설계 2절 ④: 위쪽 막대 "새 대화", 입력창 아래 안내, 저장 실패 안내(설계 5절)
    html = read("index.html")
    for text in ["새 대화", "앞 대화를 기억해요 · 모델을 바꾸면 새 대화", "이 대화는 저장되지 않아요", "500자 남음",
                 'aria-label="보내기"']:
        assert text in html, text


def test_third_tile_more_coming_with_tabler_dots_icon_and_no_fridge():
    # 2026-11-11 사용자 결정(결정기록 024): 특정 가전 없이 "더 추가 예정". 냉장고는 다루지 않는다(결정기록 003·008)
    html, css = read("index.html"), read("styles.css")
    assert re.search(r'class="tile" aria-disabled="true">\s*<span class="icon icon-dots" aria-hidden="true"></span>더 추가 예정</button>', html)
    assert "icon-tabler-dots" in read("icons/dots.svg")   # Tabler 3.19.0 파일 그대로(다른 아이콘과 같은 꾸러미)
    assert "fridge" not in html and "fridge" not in css and not (PUBLIC / "icons" / "fridge.svg").exists()


def test_favicon_request_blocked_with_empty_data_url():
    # 로고 아이콘은 나중에. 그전까지 /favicon.ico 404 콘솔 오류가 나지 않게 요청만 막는다
    assert '<link rel="icon" href="data:,">' in read("index.html")
