# 2차 Task 11 ① "내 요청" 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인한 사람의 첫 화면에 "내 요청" 요약 한 줄을 보이고, 누르면 내 요청 전부를 보는 `#requests` 화면을 연다.

**Architecture:** 화면이 Supabase(RLS "본인 요청만 읽기")에서 바로 읽는다. 첫 화면은 이 브라우저에 Supabase 로그인 기록이 있을 때만 `initAuth()`를 부른다. 개수 세기·정렬·한 줄 모양·로그인 기록 확인은 `public/js/request.js`의 순수 함수, 그리기는 `public/app.js`.

**Tech Stack:** 정적 HTML·CSS·ES 모듈, supabase-js 2.119.2 사본, node 테스트(`tests/web/js/*.test.mjs`), pytest + Playwright(가짜 Supabase).

**Spec:** `docs/superpowers/specs/2026-11-27-my-requests-design.md`

**브랜치:** `feat/phase2-my-requests`(최신 `main`에서), PR 하나.

## Global Constraints

- 서버 코드·DB 구조·RLS는 바꾸지 않는다. `app/ask/`·`app/retrieval/`·`app/answer/`는 손대지 않는다
- 로그인하지 않은 방문자의 첫 화면은 공개 설정·Supabase를 한 번도 부르지 않는다(기존 테스트 "⑦ 첫 화면에서는 공개 설정·Supabase 주소를 한 번도 부르지 않는다"가 계속 통과)
- 읽는 칸은 `id,category,brand,model_text,status,model_id,reason,updated_at`만(이메일·`user_id`는 읽지 않는다)
- 브랜드·모델명·사유는 `textContent`로만 넣는다
- 문구(설계 원문 그대로): `내 요청 N건` / `추가됨 n · 확인 중 n · 대기 n · 추가 어려움 n`(이 순서, 0은 뺌, "추가됨 n"만 굵게) / 화면 제목 `내 요청` / 한 줄 아래 `<가전> · <상태> · <바뀐 날>`(상태 굵게) / `눌러서 바로 질문하기` / `사유: <사유>` / `아직 요청이 없어요` + [시작하기](`#category`) / 안내 `추가됨이나 추가 어려움으로 바뀌면 메일로도 알려 드려요.`
- 로그인 기록 = localStorage 키 중 `/^sb-.+-auth-token$/`에 맞는 것(값은 읽지 않음, localStorage를 못 쓰면 기록 없음)
- 모양은 `.conv-card`·`.card-title`·`.card-meta`·`.notice`를 다시 쓰고, 새 CSS는 `docs/design/디자인-가이드.md` 변수만
- 테스트는 실제 Supabase·OpenAI를 부르지 않는다(가짜 값만). 테스트 먼저 커밋 → 구현 커밋, 커밋 형식·push 전 점검은 CLAUDE.md
- 이 계획에서 채팅 Claude가 더한 것(설계에 없던 세부, 사용자에게 보고함): `#requests`에서 Supabase를 쓸 수 없으면 요청 화면처럼 `잠시 쓸 수 없어요`(`UNAVAILABLE`)를 보인다

## Review Focus

1. 로그인 기록은 있는데 세션이 끝났을 때(만료·망가진 값) → 첫 화면에 요약 줄 없음, 오류 없이 나머지 그대로. Task 2 테스트 `test_my_requests_stale_login_record_shows_nothing`
2. 로그인 기록이 있는 채로 Supabase가 응답하지 않을 때 → 첫 화면·[시작하기]는 그대로, 요약 줄만 없음. Task 2 `test_my_requests_supabase_down_keeps_landing`
3. 운영자가 적은 사유에 HTML 모양 글이 있을 때 → 글자 그대로 보임. Task 2 `test_my_requests_reason_is_plain_text`
4. 추가됨인데 이 배포 모델 목록에 그 모델이 없을 때 → 누를 수 없음. Task 1 `requestView` 테스트 + Task 2 `test_my_requests_card_shows_status`
5. A 계정으로 요약을 본 뒤 로그아웃할 때 → 첫 화면에 A의 요약이 남지 않음(RLS 시연에서 B로 바꾸는 장면). Task 2 `test_my_requests_cleared_after_logout`

---

### Task 0: 설계·계획 커밋

- [ ] **Step 1:** `git switch main && git pull && git switch -c feat/phase2-my-requests`. `docs/Claude outputs/phase2/my-requests/`의 `spec.md`·`plan.md`를 `docs/superpowers/specs/2026-11-27-my-requests-design.md`·`docs/superpowers/plans/2026-11-27-my-requests-plan.md`로 그대로 복사(SHA-256은 지시 블록 값과 대조) → 커밋 `docs(docs): 내 요청 설계·계획 추가`

### Task 1: 순수 함수 (`public/js/request.js`)

**Files:**
- Modify: `public/js/request.js`
- Test: `tests/web/js/request.test.mjs`

**Interfaces (Produces):**
- `export const REQUEST_STATUSES = ["추가됨", "확인 중", "대기", "추가 어려움"]`
- `export function hasSavedLogin(storage) -> boolean` — Storage 같은 객체(`length`, `key(i)`). 키 하나라도 `/^sb-.+-auth-token$/`이면 true. 던지면 false
- `export function sortRequests(rows) -> row[]` — 객체가 아닌 항목은 버리고 `updated_at` 내림차순(새 배열, 같으면 원래 순서)
- `export function summarizeRequests(rows) -> { total: number, parts: { status: string, count: number }[] }` — `total`은 객체인 항목 수, `parts`는 `REQUEST_STATUSES` 순서·0은 뺌
- `export function requestView(row, deployedIds) -> { title, category, status, updatedAt, extra, href }` — `deployedIds`는 `Set<string>`. `title` = `` `${brand} ${model_text}` ``(앞뒤 공백 정리). 추가됨이고 `deployedIds.has(model_id)`면 `extra` = `눌러서 바로 질문하기`, `href` = `` `#chat/${encodeURIComponent(model_id)}` ``, 아니면 둘 다 null. 추가 어려움이고 사유가 비어 있지 않으면 `extra` = `` `사유: ${reason.trim()}` ``. 나머지는 `extra`·`href` null

- [ ] **Step 1: 실패하는 node 테스트 쓰기** (`tests/web/js/request.test.mjs` 끝에 더함)

```js
test("hasSavedLogin: Supabase 로그인 기록 키가 있을 때만 true(값은 보지 않음)", () => {
  const store = (keys) => ({ length: keys.length, key: (i) => keys[i] });
  assert.equal(hasSavedLogin(store(["pyeobom.conversations", "sb-supabase-auth-token"])), true);
  assert.equal(hasSavedLogin(store(["pyeobom.conversations", "sb-auth-token", "sb-x-auth-token-code-verifier"])), false);
  assert.equal(hasSavedLogin({ get length() { throw new Error("막힘"); } }), false);
});

test("sortRequests·summarizeRequests: 최근에 바뀐 순, 상태 개수는 정한 순서·0은 뺌", () => {
  const rows = [
    { id: 1, status: "대기", updated_at: "2026-11-26T03:00:00Z" },
    null,
    { id: 2, status: "추가됨", updated_at: "2026-11-27T03:00:00Z" },
    { id: 3, status: "확인 중", updated_at: "2026-11-27T01:00:00Z" },
  ];
  assert.deepEqual(sortRequests(rows).map((r) => r.id), [2, 3, 1]);
  assert.deepEqual(summarizeRequests(rows), { total: 3, parts: [
    { status: "추가됨", count: 1 }, { status: "확인 중", count: 1 }, { status: "대기", count: 1 }] });
});

test("requestView: 추가됨은 배포된 모델일 때만 누를 수 있고, 추가 어려움은 사유", () => {
  const deployed = new Set(["washer-lg-fx21wnc"]);
  const base = { brand: " LG ", model_text: "FX21WNC ", category: "washer", updated_at: "2026-11-27T03:00:00Z" };
  assert.deepEqual(requestView({ ...base, status: "추가됨", model_id: "washer-lg-fx21wnc" }, deployed), {
    title: "LG FX21WNC", category: "washer", status: "추가됨", updatedAt: "2026-11-27T03:00:00Z",
    extra: "눌러서 바로 질문하기", href: "#chat/washer-lg-fx21wnc" });
  const hidden = requestView({ ...base, status: "추가됨", model_id: "dryer-fake-not-deployed" }, deployed);
  assert.equal(hidden.href, null); assert.equal(hidden.extra, null);
  assert.equal(requestView({ ...base, status: "추가 어려움", reason: " 글자가 없는 설명서(테스트) " }, deployed).extra,
    "사유: 글자가 없는 설명서(테스트)");
  assert.equal(requestView({ ...base, status: "대기" }, deployed).extra, null);
});
```

- [ ] **Step 2: 실패 확인** — Run: `node --test tests/web/js/request.test.mjs` / Expected: 새 테스트 3개 FAIL(함수 없음)
- [ ] **Step 3: 테스트 커밋** `test(request): 내 요청 순수 함수 테스트 추가 (실패 확인)`
- [ ] **Step 4: 위 Interfaces대로 구현**
- [ ] **Step 5: 통과 확인** — Run: `node --test tests/web/js/` / Expected: 모두 PASS
- [ ] **Step 6: 구현 커밋** `feat(request): 내 요청 개수·정렬·한 줄 모양·로그인 기록 확인 함수`

### Task 2: 첫 화면 요약 줄과 `#requests` 화면

**Files:**
- Modify: `public/index.html`(첫 화면 `.landing-bottom` 안 `#landing-recent` 앞에 요약 링크 `id="landing-requests"`(`href="#requests"`, 처음엔 `hidden`), 새 `<section class="screen" data-screen="requests" hidden>`: `h1 tabindex="-1"` `내 요청`, 목록 `ul.conv-list`, 빈 상태, 안내, 오류 자리)
- Modify: `public/app.js`(`parseRoute`에 `requests`, `render`에서 첫 화면 요약·`#requests` 그리기, `onAuthChange` 처리)
- Modify: `public/styles.css`(필요할 때만, 가이드 변수만)
- Test: `tests/web/test_ui_request.py`(`FakeSupabase`에 `self.rows = []`를 두고 `/rest/v1/model_requests` GET 응답을 `(200, self.rows)`로)

**Interfaces (Consumes):** Task 1의 `hasSavedLogin`·`sortRequests`·`summarizeRequests`·`requestView`·`REQUEST_STATUSES`, 기존 `initAuth`·`openLogin`·`formatDate`·`APPLIANCES`·`modelsReady`·`UNAVAILABLE`

**동작(설계 "정한 것"·"채팅 Claude가 정한 것" 그대로):**
- 첫 화면: `hasSavedLogin(localStorage)`가 false면 아무것도 부르지 않고 요약 줄 숨김. true면 `initAuth()` → 세션 → `client.from("model_requests").select("id,category,brand,model_text,status,model_id,reason,updated_at")`. 세션 없음·실패·0건이면 숨김. 다른 화면으로 옮긴 뒤 도착한 응답은 버린다(기존 `renderId` 방식)
- `#requests`: 구글에서 돌아오는 중이면 요청 화면처럼 교환을 기다린다. 세션이 없으면 `openLogin({ then: "#requests" })`, 로그인하면 다시 그린다. Supabase를 못 쓰면 `잠시 쓸 수 없어요`. 0건이면 빈 상태, 있으면 `sortRequests` 순서로 `requestView` 한 줄씩(`href`가 있으면 `a.conv-card` + › 아이콘, 없으면 누를 수 없는 카드), 목록이 있을 때만 안내
- `onAuthChange`: `SIGNED_OUT`이면 첫 화면 요약 줄을 숨기고, `#requests`에 있으면 첫 화면(`#`)으로
- 새로 읽기: 첫 화면·`#requests`에 들어올 때마다

- [ ] **Step 1: 실패하는 화면 테스트 쓰기** (`tests/web/test_ui_request.py`, 날짜는 UTC 03:00 = 한국 정오라 어느 시간대에서도 같은 날)

```python
ROWS = [  # 가짜 요청(누가 봐도 가짜인 값)
    {"id": 11, "category": "dryer", "brand": "가짜브랜드", "model_text": "DV90-FAKE1", "status": "확인 중",
     "model_id": None, "reason": None, "updated_at": "2026-11-27T01:00:00Z"},
    {"id": 12, "category": "washer", "brand": "LG", "model_text": "FX21WNC", "status": "추가됨",
     "model_id": "washer-lg-fx21wnc", "reason": None, "updated_at": "2026-11-27T03:00:00Z"},
    {"id": 13, "category": "aircon", "brand": "가짜브랜드", "model_text": "AB-1234", "status": "추가 어려움",
     "model_id": None, "reason": "글자가 없는 설명서라 추가하기 어려워요(테스트)", "updated_at": "2026-11-26T03:00:00Z"},
    {"id": 14, "category": "washer", "brand": "가짜브랜드", "model_text": "CD-5678", "status": "대기",
     "model_id": None, "reason": None, "updated_at": "2026-11-25T03:00:00Z"},
]

def _login_then_landing(page, fake, rows):
    fake.rows = rows
    page.goto("/#requests")
    log_in_with_code(page, fake)
    page.goto("/")

def test_my_requests_card_shows_status(open_app):
    page, fake = open_app()
    _login_then_landing(page, fake, ROWS)
    card = page.get_by_role("link", name=re.compile("내 요청 4건"))
    expect(card).to_contain_text("추가됨 1 · 확인 중 1 · 대기 1 · 추가 어려움 1")
    card.click()
    expect(page.get_by_role("heading", level=1)).to_have_text("내 요청")
    items = page.locator('[data-screen="requests"] .conv-list > li')
    expect(items).to_have_count(4)
    expect(items.nth(0)).to_contain_text("LG FX21WNC")
    expect(items.nth(0)).to_contain_text("세탁기 · 추가됨 · 11월 27일")
    expect(items.nth(0).get_by_role("link")).to_have_attribute("href", "#chat/washer-lg-fx21wnc")
    expect(items.nth(1)).to_contain_text("건조기 · 확인 중")
    expect(items.nth(1).get_by_role("link")).to_have_count(0)
    expect(items.nth(2)).to_contain_text("사유: 글자가 없는 설명서라 추가하기 어려워요(테스트)")
    expect(page.locator('[data-screen="requests"]')).to_contain_text("추가됨이나 추가 어려움으로 바뀌면 메일로도 알려 드려요.")
    gets = [c for c in fake.calls if c["method"] == "GET" and c["path"].startswith("/rest/v1/model_requests")]
    assert gets and all(parse_qs(urlsplit(c["path"]).query)["select"] == ["id,category,brand,model_text,status,model_id,reason,updated_at"]
                        for c in gets)   # 이메일·user_id를 읽지 않는다

def test_my_requests_zero_and_not_deployed(open_app):
    page, fake = open_app()
    _login_then_landing(page, fake, [])
    expect(page.get_by_role("link", name="시작하기")).to_be_visible()
    expect(page.locator("#landing-requests")).to_be_hidden()
    page.goto("/#requests")
    expect(page.get_by_text("아직 요청이 없어요")).to_be_visible()
    fake.rows = [{**ROWS[1], "model_id": "dryer-fake-not-deployed"}]
    page.reload()
    expect(page.locator('[data-screen="requests"] .conv-list > li').get_by_role("link")).to_have_count(0)

def test_my_requests_direct_without_login_opens_sheet(open_app):
    page, fake = open_app()
    fake.rows = ROWS
    page.goto("/#requests")
    expect(login_sheet(page)).to_be_visible()
    log_in_with_code(page, fake)
    expect(page.locator('[data-screen="requests"] .conv-list > li')).to_have_count(4)

def test_my_requests_stale_login_record_shows_nothing(open_app):   # Review Focus 1
    page, fake = open_app(init="localStorage.setItem('sb-supabase-auth-token', '망가진 값(테스트)')")
    expect(page.get_by_role("link", name="시작하기")).to_be_visible()
    expect(page.locator("#landing-requests")).to_be_hidden()

def test_my_requests_supabase_down_keeps_landing(open_app):   # Review Focus 2
    page, fake = open_app()
    _login_then_landing(page, fake, ROWS)
    fake.down = True
    page.reload()
    expect(page.locator("#landing-requests")).to_be_hidden()
    page.get_by_role("link", name="시작하기").click()
    expect(page.get_by_role("heading", level=1)).to_have_text(CATEGORY_H1)

def test_my_requests_reason_is_plain_text(open_app):   # Review Focus 3
    page, fake = open_app()
    _login_then_landing(page, fake, [{**ROWS[2], "reason": "<b>굵게</b>(테스트)"}])
    page.goto("/#requests")
    expect(page.get_by_text("사유: <b>굵게</b>(테스트)")).to_be_visible()

def test_my_requests_cleared_after_logout(open_app):   # Review Focus 5
    page, fake = open_app()
    _login_then_landing(page, fake, ROWS)
    expect(page.locator("#landing-requests")).to_be_visible()
    page.goto("/#requests")
    row = drawer_row(page)   # 기존 test_logout_on_request_screen_returns_to_model_screen과 같은 조작
    row.get_by_role("button", name="로그아웃").click()
    expect(row.get_by_role("button", name="로그인")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator('[data-screen="landing"]')).to_be_visible()
    expect(page.locator("#landing-requests")).to_be_hidden()
    assert "내 요청 4건" not in (page.locator("#landing-requests").text_content() or "")   # 숨긴 줄에도 A의 요약이 남지 않는다
```

  - 파일 위 import에 `from urllib.parse import parse_qs, urlsplit`를 더한다

- [ ] **Step 2: 실패 확인** — Run: `pytest tests/web/test_ui_request.py -k my_requests -v` / Expected: 새 테스트 FAIL(요약 줄·화면 없음). 기존 테스트는 통과
- [ ] **Step 3: 테스트 커밋** `test(request): 내 요청 첫 화면 요약·목록 화면 테스트 추가 (실패 확인)`
- [ ] **Step 4: 위 "동작"대로 구현** (index.html·app.js·필요하면 styles.css)
- [ ] **Step 5: 통과 확인** — Run: `pytest tests/web -v` 와 `node --test tests/web/js/` / Expected: 모두 PASS(기존 "⑦ 첫 화면에서는 공개 설정·Supabase 주소를 한 번도 부르지 않는다" 포함)
- [ ] **Step 6: 구현 커밋** `feat(request): 첫 화면 내 요청 요약과 내 요청 화면`

### Task 3: 확인·기록·PR

- [ ] **Step 1:** `pytest -v -m "not integration"` 실패 0, `node --test tests/web/js/` 실패 0
- [ ] **Step 2:** 화면 사진(로컬 서버 + 가짜 Supabase, 360px, deviceScaleFactor 2) 세 장을 `docs/Claude outputs/phase2/my-requests/`에: 첫 화면 요약 줄, `#requests` 목록(위 ROWS), 다른 계정(0건) 첫 화면
- [ ] **Step 3:** 개발일지 `docs/개발일지/2026-11-27.md` 끝에 절 하나(한 것·결정한 것·AI 실수, 채팅 Claude가 원문을 주면 그대로) — 원문은 지시 블록에 있음
- [ ] **Step 4:** 커밋 → push 전 점검 → push → PR(양식) → 보고하고 멈춤(병합은 채팅 Claude 대조 뒤)

## 덧붙임 (2026-11-27, 실행 중)

- Task 2: 첫 화면에 숨긴 요약 링크(`.conv-card`)가 생겨 기존 `tests/web/test_ui_flow.py` `test_no_recent_section_without_conversations`의 `.conv-card` 개수 0이 깨짐 → 그 줄을 `.conv-card:visible`(보이는 카드 0개)로 바꿈. 테스트 뜻("대화가 없으면 카드가 보이지 않음")은 그대로이고, 로그인하지 않았을 때 요약 줄이 보이지 않는 것도 함께 확인한다(Claude Code가 멈춰 물음, 사용자 결정 2026-11-27)
- Task 2 `test_my_requests_zero_and_not_deployed`: 앱은 새로 불러오면 첫 화면이 열려(2차 계획 기본값 3) `page.reload()` 뒤의 확인이 빈 목록을 셌음 → `page.goto("/")` 뒤 `page.goto("/#requests")`로 바꾸고, 배포 안 된 모델의 한 줄이 1개 보이고 그 안에 링크가 0개인지 확인
- JS 테스트 명령: `node --test tests/web/js/`(폴더)는 이 환경에서 바꾸기 전에도 실패 1개로 끝나(2026-11-12·11-25 개발일지와 같음) `node --test "tests/web/js/*.test.mjs"`로 돌림
- 화면 접근성: 지금까지 화면 작업처럼 `measure/a11y.py`(axe)에 첫 화면 요약 줄·`#requests` 목록 상태를 더해 위반 0을 확인한다(계획에서 빠졌던 것)
- `test_my_requests_stale_login_record_shows_nothing`은 실패 확인 단계에서 이미 통과했다(요약 줄 요소가 아직 없어 "숨김"이 바로 맞음). 구현 뒤에 망가진 로그인 기록으로도 오류 없이 숨는지를 지키는 테스트로 둔다
