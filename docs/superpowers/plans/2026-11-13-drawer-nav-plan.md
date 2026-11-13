# 서랍 뒤로·처음으로 버튼 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ☰ "지난 대화" 서랍 맨 윗줄에 ←(한 단계 위)·⌂(첫 화면)·✕(닫기) 아이콘 버튼을 둔다.

**Architecture:** 한 단계 위 주소를 고르는 규칙은 작은 JS 모듈 `public/js/nav.js`로 나눠 `node --test`로 시험한다. ←·⌂는 서랍 안 `<a>` 링크라서 이미 있는 서랍 링크 처리(`closest("a")` → `closedByLink` → 닫기 → `hashchange` → 그 화면 h1로 포커스)를 그대로 쓴다. 서랍을 열 때마다 ←의 주소와 숨김을 다시 정한다. 화면 흐름은 Playwright(`ui` 표시)로 시험한다.

**Tech Stack:** 바닐라 JS ES 모듈·CSS(`public/`, 빌드 없음), Node v24 `node --test`, Playwright(Python) `pytest -m ui`

**Spec:** `docs/superpowers/specs/2026-11-13-drawer-nav-design.md`

## Global Constraints
- 브랜치 하나·PR 하나(`feat/drawer-nav`). main 병합 = 운영 배포이므로 PR을 올리고 멈춰 보고한다. 병합은 사용자 확인 뒤.
- 위쪽 막대(`#topbar`), 채팅 막대 "새 대화", 서랍 "새 대화" 링크는 바꾸지 않는다.
- 화면 읽기용 이름은 정확히 "뒤로", "처음으로", "닫기".
- 세 버튼의 누르는 자리는 각각 44×44px 이상(`--tap-min`)이고 서로 겹치지 않는다.
- 아이콘은 `public/icons/`의 기존 아이콘과 같은 Tabler outline 배포본에서 `arrow-left.svg`·`home.svg`·`x.svg`를 가져온다(LICENSE는 이미 있음). 직접 그리지 않는다.
- 글자·주소는 `textContent`·속성으로만 넣는다(innerHTML 금지 검사 `tests/web/test_public_page.py`).
- AI 비용 없음(`/api/ask`는 테스트에서 가로챔). 개인정보 시험 값은 누가 봐도 가짜인 값만.

## 채팅 Claude가 정한 기본값 (사용자가 계획을 읽으며 확인)
1. ←·⌂는 `<a>`다. 서랍 클릭 처리는 새로 만들지 않는다.
2. ⌂의 주소는 `#`(빈 경로를 `parseRoute`가 첫 화면으로 읽음).
3. 서랍을 열 때 포커스는 지금처럼 "지난 대화" 제목(`#drawer-title`)에 둔다. DOM 순서는 ← → ⌂ → ✕ → 제목 → 새 대화이고, 제목에서 Shift+Tab이면 ✕ → ⌂ → ← 순서다. → 2026-11-13 변경(사용자 결정): 코드 검토에서 ←가 ☰ 자리와 겹쳐 ✕를 맨 왼쪽으로. DOM 순서는 ✕ → ← → ⌂ → 제목 → 새 대화이고, 제목에서 Shift+Tab이면 ⌂ → ← → ✕ 순서다
4. 모델 목록을 못 받았거나 모르는 모델의 채팅이면 ←는 `#category`.
5. 가전 고르기에서 ←는 `hidden` 속성으로 숨긴다. 이때 ⌂가 맨 왼쪽에 온다. → 2026-11-13 변경(위 3과 같은 결정): ✕가 맨 왼쪽이라 가전 고르기에서는 [✕][⌂]

## Review Focus
1. 답을 기다리는 중에 ☰ → ←: 답은 보낸 대화에 저장되고 모델 고르기 화면에 그려지지 않는다.
2. 서랍을 열 때마다 ← 주소를 다시 정한다: 채팅에서 열고 닫은 뒤 브라우저 뒤로(모델 고르기)에서 다시 열면 ←는 `#category`.
3. 모델 목록 요청 실패(500) 상태의 모델 고르기 화면에서 ☰ → ←: 멈추지 않고 가전 고르기로 간다.
4. `.icon-button`의 왼쪽 음수 여백(`margin-left: calc(-1 * var(--space-3))`)이 모든 아이콘 버튼에 붙어 있어 ←·⌂가 겹칠 수 있다(360px).
5. ✕나 Esc로 닫으면 포커스가 ☰(`#drawer-open`)로 돌아온다(지금 "닫기"와 같게).

---

### Task 1: 한 단계 위 주소 규칙

**Files:**
- Create: `public/js/nav.js`
- Test: `tests/web/js/nav.test.mjs`

**Interfaces:**
- Produces: `parentHash(route, models) -> string | null`
  - `route`: `app.js` `parseRoute` 결과 `{ screen: "landing"|"category"|"model"|"chat", appliance?, modelId?, conversationId? }`
  - `models`: `/api/models` 목록(항목마다 `id`, `appliance`)

- [ ] **Step 1: 실패하는 테스트 작성** (`tests/web/js/nav.test.mjs`, 기존 `history.test.mjs`와 같은 `node:test`·`node:assert/strict` 방식)

```js
const models = [{ id: "washer-lg-fx25", appliance: "washer" }, { id: "aircon-lg-sq06fa1wds", appliance: "aircon" }];
test("채팅 → 그 가전의 모델 고르기", () =>
  assert.equal(parentHash({ screen: "chat", modelId: "aircon-lg-sq06fa1wds", conversationId: "c1" }, models), "#model/aircon"));
test("모델 고르기 → 가전 고르기", () =>
  assert.equal(parentHash({ screen: "model", appliance: "washer" }, models), "#category"));
test("가전 고르기·첫 화면은 없음", () => {
  assert.equal(parentHash({ screen: "category" }, models), null);
  assert.equal(parentHash({ screen: "landing" }, models), null);
});
test("모르는 모델·빈 목록이면 가전 고르기", () => {
  assert.equal(parentHash({ screen: "chat", modelId: "x" }, models), "#category");
  assert.equal(parentHash({ screen: "chat", modelId: "washer-lg-fx25" }, []), "#category");
});
```

- [ ] **Step 2: Run** `node --test tests/web/js/` → nav 테스트 FAIL(모듈 없음) → **Commit(테스트)**
- [ ] **Step 3: 구현** `export function parentHash(route, models)` in `public/js/nav.js`. 가전 값은 `encodeURIComponent`로 넣는다.
- [ ] **Step 4: Run** `node --test tests/web/js/` → 모두 PASS
- [ ] **Step 5: Commit(구현)**

### Task 2: 서랍 맨 윗줄 [←][⌂] … [✕]

**Files:**
- Modify: `public/index.html:29-32`(서랍 머리)
- Modify: `public/app.js`(import, 서랍 열기 `ui.menu` click 약 617행)
- Modify: `public/styles.css`(아이콘 클래스 103~114행 근처, `.drawer-head` 380행)
- Create: `public/icons/arrow-left.svg`, `public/icons/home.svg`, `public/icons/x.svg`
- Test: `tests/web/test_ui_flow.py`(`ui` 표시, 기존 고정 장치와 `/api/ask` 가로채기 그대로)

**Interfaces:**
- Consumes: `parentHash(route, models)` (Task 1)
- Produces: `#drawer-back`(a), `#drawer-home`(a, `href="#"`), `#drawer-close`(button, 기존 id 유지), 아이콘 클래스 `icon-arrow-left`·`icon-home`·`icon-x`

- [ ] **Step 1: 실패하는 화면 테스트 작성**
  - `test_drawer_back_from_chat`: 채팅에서 ☰ → ← → 서랍 닫힘, 주소 `#model/<그 가전>`, 포커스가 모델 고르기 h1
  - `test_drawer_back_from_model`: 모델 고르기에서 ☰ → ← → 주소 `#category`, 포커스가 가전 고르기 h1
  - `test_drawer_back_hidden_on_category`: 가전 고르기에서 ☰ → `#drawer-back` 안 보임, `#drawer-home` 보임
  - `test_drawer_home`: 채팅에서 ☰ → ⌂ → 첫 화면 보임, 위쪽 막대 숨김, 포커스가 첫 화면 h1
  - `test_drawer_close_icon`: ✕ → 서랍 닫힘, 포커스 `#drawer-open`. Esc도 같음
  - `test_drawer_nav_names_and_order`: 접근 이름 "뒤로"·"처음으로"·"닫기", DOM 순서 ← ⌂ ✕ 다음 `#drawer-title`, 열자마자 포커스 `#drawer-title`
  - `test_drawer_nav_tap_size_360`: 360px에서 세 버튼 상자가 각각 44×44 이상, 서로 겹치지 않음, 서랍 안에 있음
  - `test_drawer_back_while_waiting`: `/api/ask` 응답을 늦춤 → 질문 보냄 → ☰ → ← → 모델 고르기 화면에 답 없음, 응답 뒤 그 대화를 다시 열면 답이 저장돼 있음
  - `test_drawer_back_rechecked_on_open`: 채팅에서 서랍 열고 닫기 → 브라우저 뒤로(모델 고르기) → 다시 열기 → ← 주소 `#category`
  - `test_drawer_back_models_failed`: `/api/models` 500 → 모델 고르기 화면 → ☰ → ← → 가전 고르기, 페이지 오류 없음
- [ ] **Step 2: Run** `pytest -m ui tests/web/test_ui_flow.py -k drawer` → 새 테스트 FAIL → **Commit(테스트)**
- [ ] **Step 3: 구현**
  - index.html: `.drawer-head`를 `<a id="drawer-back" class="icon-button" aria-label="뒤로">`, `<a id="drawer-home" class="icon-button" href="#" aria-label="처음으로">`, `<button type="button" id="drawer-close" class="icon-button" aria-label="닫기">`(각 안에 `<span class="icon icon-…" aria-hidden="true">`)로 바꾸고 `<h2 id="drawer-title" tabindex="-1">지난 대화</h2>`는 그 아래로 옮긴다.
  - app.js: 서랍을 열 때(`renderDrawer()` 옆) `parentHash(parseRoute(location.hash), drawerModels)`로 ←의 `href`를 넣고, null이면 `hidden`.
  - styles.css: 아이콘 클래스 3개. 서랍 머리에서는 첫 버튼만 왼쪽 음수 여백, ✕는 오른쪽 끝(`margin-left: auto`) + 오른쪽 음수 여백. `<a>` 아이콘 버튼은 밑줄 없음.
- [ ] **Step 4: Run** `pytest -m "not integration"` + `node --test tests/web/js/` → PASS
- [ ] **Step 5: 캡처** `measure/out/drawer-nav/`(git 제외)에 360px·1280px × 가전 고르기·모델 고르기·채팅의 서랍 열린 화면 6장. 겹침·잘림이 없는지 보고에 적는다.
- [ ] **Step 6: Commit(구현)**

### Task 3: 기록과 PR

**Files:**
- Create: `docs/결정기록/030-서랍-뒤로-처음으로.md`: 고려한 방법 A·B·C·D·E, 고른 것 D(아이콘만 + ✕), 채팅 Claude 추천은 E였다는 것과 그 위험(테스트 때와 막대가 같아 보임, 뒤로가 두 번 누르기), 다음 테스트 기준(설계 문서 그대로)
- Modify: `docs/결정기록/021-채팅형-개편.md` 53행 아래에 "2026-11-13 재검토 → 결정기록 030" 한 줄
- Modify: `docs/개발일지/2026-11-13.md`: PR #64 병합(0586795)과 이번 작업

- [ ] **Step 1: 위 기록 작성**
- [ ] **Step 2: Run** `pytest -m "not integration"` + `node --test tests/web/js/` → PASS
- [ ] **Step 3: push → PR**(본문에 설계·계획 경로, 테스트 결과, 캡처 6장 경로) → 멈춰 보고
- [ ] **Step 4: (사용자가 병합한 뒤)** https://pyeobom.vercel.app 에서 360px로 세 화면의 서랍을 확인하고 개발일지에 한 줄
