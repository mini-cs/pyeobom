# 2차 동결 전 고칠 것 2개 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이전 답 줄의 "근거 N개"를 펼친 근거 카드 수와 같게 하고, 카테고리 타일의 세탁기·건조기 아이콘을 MDI 쌍으로 바꾼다.

**Architecture:** 숫자는 근거 카드를 만드는 `groupCitations`(public/js/evidence.js)를 `renderEntry`(public/app.js)에서 다시 쓴다. 아이콘은 MDI SVG 두 개를 받은 그대로 `public/icons/`에 두고 CSS 두 줄만 바꾼다(마스크 방식은 그대로).

**Tech Stack:** 정적 HTML·CSS·ES 모듈, pytest + Playwright(화면 테스트), npm(`@mdi/svg@7.4.47` 받기).

**Spec:** `docs/superpowers/specs/2026-11-27-freeze-fixes-design.md`

**브랜치:** `fix/phase2-freeze-fixes`(최신 `main`에서), PR 하나.

## Global Constraints

- 문구는 그대로: `이전 답 · 근거 N개`, `이전 답 · 근거 없음`
- 근거 카드, 최신 답의 `근거 보기 · …` 줄(`evidenceLabel`), "드릴까요?" 버튼은 바꾸지 않는다
- `app/answer/`는 손대지 않는다(2차 계획 Global 1)
- MDI 파일은 받은 그대로(이름·내용). SHA-256: `washing-machine.svg` `13714999ceb1fe12e18df07a4f69047e659fd8aaba82c1fbea8ba779cfe5f475`(465바이트), `tumble-dryer.svg` `32f34559c1170b8e076adf30f134feec4d012c4512b833388c5cac242fa81347`(667바이트), 꾸러미 `LICENSE` → `LICENSE-mdi.txt` `f3bc8715bad84b26396bb42d2abd11f919cf58163be158eab79ecbaabf84cdf2`(1,012바이트). npm 꾸러미 SHA-256 `de92e5dc9ce46c392ab5c53aa7190b19f82b40cb48872a083f788c7e13e91fef`
- 에어컨·"더 추가 예정" 타일과 다른 화면의 Tabler 아이콘은 그대로
- 기록은 기존 문장을 지우지 않고 덧붙인다(CLAUDE.md)
- 테스트 먼저 커밋 → 구현 커밋(CLAUDE.md "테스트 먼저 커밋"), 커밋 형식·push 전 점검은 CLAUDE.md
- 테스터는 코드(D)로만 부른다
- 코드 동결 2026-11-30 밤 전에 병합

## Review Focus

1. 망가진 근거(객체가 아닌 항목)가 섞인 저장 대화를 열 때 → 이전 답 줄 숫자는 실제로 보이는 카드 수(망가진 항목은 세지 않음). Task 1 Step 1의 세 번째 테스트
2. 같은 가이드 문서의 인용이 여러 개일 때 → 카드 하나로 센다. Task 1 Step 1에서 고치는 `MIXED` 기대값(가이드 인용 2개 = 카드 1개)
3. 근거가 없는 이전 답 → `이전 답 · 근거 없음` 그대로. 기존 테스트(`test_ui_flow.py` "이전 답 · 근거 없음")가 계속 통과해야 함
4. 휴대폰에서 MDI 아이콘이 보이는지(크기 정보 없이 `viewBox`만 있는 SVG를 마스크로 씀) → Task 3 Step 4 화면 사진(360px 폭)과 병합 전 사용자 휴대폰 확인
5. 다른 화면이 `icon-washer`·`icon-dryer`나 옛 파일을 부르는지 → Task 2 테스트가 옛 파일·CSS가 없음을 확인. 2026-11-27 `main` 기준 두 클래스는 `index.html` 타일에서만 쓴다

---

### Task 0: 설계·계획 커밋

**Files:**
- Create: `docs/superpowers/specs/2026-11-27-freeze-fixes-design.md`, `docs/superpowers/plans/2026-11-27-freeze-fixes-plan.md`(채팅 Claude가 `docs/Claude outputs/phase2/freeze-fixes/`에 둔 `spec.md`·`plan.md`를 그대로 복사, SHA-256은 지시 블록 값과 대조)

- [ ] **Step 1: 두 파일을 원문 그대로 넣고 커밋**

```bash
git switch main && git pull && git switch -c fix/phase2-freeze-fixes
git add docs/superpowers/specs/2026-11-27-freeze-fixes-design.md docs/superpowers/plans/2026-11-27-freeze-fixes-plan.md
git commit   # docs(docs): 동결 전 고칠 것 2개 설계·계획 추가
```

### Task 1: 이전 답 줄 숫자 = 근거 카드 수

**Files:**
- Modify: `public/app.js` `renderEntry`(지금 `const n = Array.isArray(entry.turn.citations) ? entry.turn.citations.length : 0;` 줄)
- Test: `tests/web/test_ui_flow.py`

**Interfaces:**
- Consumes: `groupCitations(citations) -> Array<{doc_type, page, title, quotes}>`(public/js/evidence.js, 이미 app.js에 import돼 있음. 배열이 아니거나 객체가 아닌 항목은 버림)

- [ ] **Step 1: 실패하는 테스트 쓰기(고침 1, 더함 2)**
  - 고침: `test_saved_conversation_renders_evidence_the_same_way`의 `name="이전 답 · 근거 5개"` → `name="이전 답 · 근거 3개"`, 줄 끝 주석 `# MIXED 인용 5개 = 카드 3개(12쪽·13쪽·가이드 1), D 의견 4(2026-11-27)`
  - 더함 1:

```python
def test_previous_answer_counts_evidence_cards_not_quotes(open_page):
    # D 의견 4(2026-11-27): 이전 답 줄 숫자 = 펼친 근거 카드 수. 같은 쪽 인용 2개는 카드 하나
    same_page = [CITE, {**CITE, "quote": "가짜 인용 둘(테스트)."}]
    page = open_page(ask=lambda body, route: fake(body, citations=same_page))
    open_chat(page, "washer-lg-fx25")
    for i in (1, 2):
        send(page, f"가짜 질문 {i}")
        wait_turns(page, i)
    first = page.locator(".turn").first
    fold = first.get_by_role("button", name="이전 답 · 근거 1개")
    expect(fold).to_have_attribute("aria-expanded", "false")
    fold.click()
    expect(first.locator(".evidence")).to_have_count(1)
    expect(first.locator(".evidence blockquote")).to_have_count(2)
```

  - 더함 2(Review Focus 1):

```python
def test_saved_broken_citation_not_counted_in_previous_answer(open_page):
    # 저장 대화에 객체가 아닌 근거가 섞여도 줄 숫자는 보이는 카드 수(evidence.js valid)
    conversation = _conversation(1, "washer-samsung-wd90h25")
    conversation["turns"] = [{"question_masked": f"가짜 질문 {i}", "rewritten_question": None, "answer": "가짜 답",
                              "found": True, "citations": [CITE, None, {**CITE, "quote": "가짜 인용 둘(테스트)."}],
                              "kind": "answer"} for i in (1, 2)]
    page = open_page(conversations=[conversation])
    open_chat(page, "washer-samsung-wd90h25", "c1")
    expect(page.get_by_role("button", name="이전 답 · 근거 1개")).to_be_visible()
    expect(page.locator(".turn").first.locator(".evidence")).to_have_count(1)
```

  - 저장 대화를 읽는 단계에서 `None` 항목이나 그 턴이 걸러져 화면까지 오지 않으면 더함 2는 빼고 그 사실을 보고한다(읽기 코드는 고치지 않는다)

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/web/test_ui_flow.py -k "renders_evidence_the_same_way or counts_evidence_cards or broken_citation" -v`
Expected: 3개 FAIL(지금은 줄이 인용 수 5·2·3을 보여 줌)

- [ ] **Step 3: 테스트 커밋**

`test(ui): 이전 답 근거 수를 카드 수로 세는 테스트 추가 (실패 확인)`

- [ ] **Step 4: `renderEntry`에서 `n`을 `groupCitations(entry.turn.citations).length`로 바꾼다**

주석은 `// 이전 답 줄 숫자 = 펼친 근거 카드 수(설명서 쪽·가이드 문서 묶음, D 의견 4, 2026-11-27)`. 그 밖의 줄은 바꾸지 않는다.

- [ ] **Step 5: 통과 확인**

Run: `pytest tests/web/test_ui_flow.py -v`
Expected: 전부 PASS("이전 답 · 근거 없음", "근거 2개", "근거 1개" 기존 테스트 포함)

- [ ] **Step 6: 구현 커밋**

`fix(ui): 이전 답 줄 근거 수를 근거 카드 수로 셈`

### Task 2: 세탁기·건조기 타일 아이콘을 MDI로

**Files:**
- Create: `public/icons/washing-machine.svg`, `public/icons/tumble-dryer.svg`, `public/icons/LICENSE-mdi.txt`
- Delete: `public/icons/wash-machine.svg`, `public/icons/wash-tumble-dry.svg`
- Modify: `public/styles.css`(`.icon-washer`·`.icon-dryer` 두 줄), `.gitattributes`, `public/icons/README.md`, `docs/design/디자인-가이드.md`(타일 항목), `docs/결정기록/024-디자인-체계.md`(결정 9 아래)
- Test: `tests/web/test_public_page.py`

- [ ] **Step 1: 실패하는 테스트 쓰기**

```python
def test_washer_dryer_tiles_use_mdi_icons_with_license():
    # 2026-11-27 사용자 결정(상호 테스트 D 의견 2): 세탁기·건조기 타일만 MDI 7.4.47 원본 그대로, 에어컨은 Tabler
    css, html = read("styles.css"), read("index.html")
    assert '.icon-washer { --icon: url("/icons/washing-machine.svg"); }' in css
    assert '.icon-dryer { --icon: url("/icons/tumble-dryer.svg"); }' in css
    assert '.icon-aircon { --icon: url("/icons/air-conditioning.svg"); }' in css
    assert 'class="icon icon-washer"' in html and 'class="icon icon-dryer"' in html
    digests = {"washing-machine.svg": "13714999ceb1fe12e18df07a4f69047e659fd8aaba82c1fbea8ba779cfe5f475",
               "tumble-dryer.svg": "32f34559c1170b8e076adf30f134feec4d012c4512b833388c5cac242fa81347",
               "LICENSE-mdi.txt": "f3bc8715bad84b26396bb42d2abd11f919cf58163be158eab79ecbaabf84cdf2"}
    for name, digest in digests.items():
        assert hashlib.sha256((PUBLIC / "icons" / name).read_bytes()).hexdigest() == digest, name
    assert "Pictogrammers Free License" in read("icons/LICENSE-mdi.txt")
    for old in ("wash-machine.svg", "wash-tumble-dry.svg"):
        assert not (PUBLIC / "icons" / old).exists() and old not in css, old
```

(파일 위에 `import hashlib`)

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/web/test_public_page.py::test_washer_dryer_tiles_use_mdi_icons_with_license -v`
Expected: FAIL(CSS가 아직 `wash-machine.svg`를 부름)

- [ ] **Step 3: 테스트 커밋**

`test(ui): 세탁기·건조기 타일 MDI 아이콘 테스트 추가 (실패 확인)`

- [ ] **Step 4: 파일 받기**

`npm pack @mdi/svg@7.4.47`로 받아 꾸러미 SHA-256이 Global Constraints 값과 같은지 본 뒤, 안의 `package/svg/washing-machine.svg`·`package/svg/tumble-dryer.svg`·`package/LICENSE`를 `public/icons/washing-machine.svg`·`tumble-dryer.svg`·`LICENSE-mdi.txt`로 복사한다. npm으로 못 받으면 unpkg(`https://unpkg.com/@mdi/svg@7.4.47/svg/washing-machine.svg` 등 같은 경로)에서 받는다. 어느 쪽이든 세 파일 SHA-256이 같아야 하고, 다르면 멈추고 보고한다. 받은 꾸러미·압축 해제 폴더는 저장소 밖에 둔다.

- [ ] **Step 5: 연결과 정리**
  - `public/styles.css`: `.icon-washer`는 `url("/icons/washing-machine.svg")`, `.icon-dryer`는 `url("/icons/tumble-dryer.svg")`
  - `public/icons/wash-machine.svg`·`wash-tumble-dry.svg` 삭제(`git rm`)
  - `.gitattributes` 끝에 더함:

```
# 2차 동결 전 고침: 받은 그대로 두고 SHA-256을 README에 적은 MDI 파일은 줄 끝을 LF로
public/icons/washing-machine.svg text eol=lf
public/icons/tumble-dryer.svg text eol=lf
public/icons/LICENSE-mdi.txt text eol=lf
```

- [ ] **Step 6: 통과 확인**

Run: `pytest tests/web/test_public_page.py -v`
Expected: 전부 PASS(`test_self_hosted_fonts_and_icons_with_licenses`의 "CSS가 부르는 파일이 모두 있다" 포함)

- [ ] **Step 7: 구현 커밋**

`fix(ui): 세탁기·건조기 타일 아이콘을 MDI로 바꿈`

- [ ] **Step 8: 기록(원문 그대로)**
  - `public/icons/README.md` 끝에 더함. `{받은 곳}`은 npm이면 ``npm `npm pack @mdi/svg@7.4.47`(꾸러미 SHA-256 `de92e5dc9ce46c392ab5c53aa7190b19f82b40cb48872a083f788c7e13e91fef`)``, unpkg면 ``unpkg `https://unpkg.com/@mdi/svg@7.4.47/` 아래 같은 경로``

```
- *(2026-11-27 덧붙임: 첫 줄의 Tabler `wash-machine.svg`(세탁기 타일)·`wash-tumble-dry.svg`(건조기 타일)는 지웠고 아래 MDI 두 파일로 바뀜)*
- MDI(Material Design Icons, Pictogrammers): `@mdi/svg@7.4.47`의 `svg/washing-machine.svg`(세탁기 타일)·`svg/tumble-dryer.svg`(건조기 타일)를 이름·내용 그대로 둠(2026-11-27, 고치지 않음). SHA-256 `washing-machine.svg` `13714999ceb1fe12e18df07a4f69047e659fd8aaba82c1fbea8ba779cfe5f475`(465바이트), `tumble-dryer.svg` `32f34559c1170b8e076adf30f134feec4d012c4512b833388c5cac242fa81347`(667바이트)
  - 받은 곳: {받은 곳}
  - 라이선스: 꾸러미 `LICENSE`(Pictogrammers Free License, 아이콘은 Apache 2.0)를 `LICENSE-mdi.txt`로 그대로 둠. SHA-256 `f3bc8715bad84b26396bb42d2abd11f919cf58163be158eab79ecbaabf84cdf2`(1,012바이트)
  - 이유: 2차 상호 테스트 D 의견 2(건조기 아이콘이 세탁기와 구분 안 됨). Tabler 그대로·직접 그린 시안을 본 뒤 사용자가 MDI의 세탁기·건조기 쌍으로 정함(2026-11-27). 아이콘 묶음 8개의 파일 목록 중 건조기 그림이 있는 것은 MDI 하나였다(채팅 Claude 확인)
  - 면을 채운 그림이라 선 그림인 Tabler 아이콘(에어컨·"더 추가 예정" 등)과 모양 방식이 다르다(알고 고름)
```

  - `docs/design/디자인-가이드.md` 타일 항목("3. **회색 네모 타일(카테고리):**" 줄) 끝, 기존 2026-11-25 덧붙임 뒤에 한 칸 띄우고 더함:

```
*(2026-11-27 덧붙임, 2차 동결 전 고침: 세탁기·건조기 타일 아이콘은 MDI `@mdi/svg` 7.4.47의 `washing-machine`·`tumble-dryer`(면을 채운 그림)로 바뀜. 상호 테스트 D 의견 2, 설계 `docs/superpowers/specs/2026-11-27-freeze-fixes-design.md`. 에어컨·"더 추가 예정"은 Tabler 그대로)*
```

  - `docs/결정기록/024-디자인-체계.md` 결정 9의 마지막 하위 줄("`dots.svg`는 다른 아이콘과 같은 …" 줄) 다음에 같은 들여쓰기로 더함:

```
   - (덧붙임 2026-11-27, 2차 동결 전 고침) 세탁기·건조기 타일 아이콘은 Tabler에서 MDI `@mdi/svg` 7.4.47의 `washing-machine`·`tumble-dryer`로 바뀌었다(상호 테스트 D 의견 2, 사용자 결정). 라이선스 원문은 `public/icons/LICENSE-mdi.txt`, 출처·SHA-256은 `public/icons/README.md`. 쓰지 않게 된 Tabler `wash-machine.svg`·`wash-tumble-dry.svg`와 CSS는 지웠다. 에어컨·"더 추가 예정"과 다른 화면의 아이콘은 Tabler 그대로다
```

- [ ] **Step 9: 기록 커밋**

`docs(docs): 세탁기·건조기 MDI 아이콘 출처·라이선스 기록`

### Task 3: 확인·PR·기록

**Files:**
- Modify: `docs/개발일지/2026-11-27.md`(끝에 절 더함), `docs/평가/phase2-mutual-test.md`(결과 D 2번·4번 끝)
- Create(git 밖): `docs/Claude outputs/phase2/freeze-fixes-category-pc.png`, `freeze-fixes-category-360.png`, `freeze-fixes-previous-answer-360.png`

- [ ] **Step 1: 전체 테스트**

Run: `pytest -v -m "not integration"`
Expected: 실패 0(개수를 보고)

- [ ] **Step 2: 개발일지 절 더하기(원문 그대로, `{…}`만 채움)**

```
# 2차 동결 전 고침 — 근거 N개 숫자, 세탁기·건조기 아이콘 (`fix/phase2-freeze-fixes`)

## 한 것
- 이전 답 줄 "이전 답 · 근거 N개"의 N을 인용 수에서 근거 카드 수(설명서 쪽·가이드 문서 묶음, `groupCitations`)로 바꿈(`public/app.js` renderEntry). 문구는 그대로
- 세탁기·건조기 타일 아이콘을 MDI `@mdi/svg` 7.4.47의 `washing-machine`·`tumble-dryer`(고치지 않음)로 바꿈. 라이선스 원문 `public/icons/LICENSE-mdi.txt`, 출처·SHA-256은 `public/icons/README.md`. 쓰지 않게 된 Tabler 두 파일과 CSS는 지움
- 설계 `docs/superpowers/specs/2026-11-27-freeze-fixes-design.md`, 계획 `docs/superpowers/plans/2026-11-27-freeze-fixes-plan.md`
- 테스트: {pytest -v -m "not integration" 결과}

## 결정한 것
- 사용자 결정(2026-11-27)
  - 근거 N개는 묶음 수로 센다
  - 건조기 아이콘: 시안 다섯 번(Tabler 그대로 2개, 직접 그린 6개, MDI 참고와 쓰는 범위)을 본 뒤 MDI 세탁기·건조기 쌍으로 정함. 에어컨은 바꾸지 않음(MDI 에어컨은 영어 "A/C" 글자)
- 채팅 Claude가 정한 것: 옛 Tabler 두 파일 지우기, 기록 위치, 한 PR

## AI 실수
- 채팅 Claude: 없음
- Claude Code: {있으면 "무엇 → 어떻게 고침, 피해" 형식, 없으면 없음}
```

- [ ] **Step 3: 커밋·push 전 점검·push·PR**

커밋 `docs(docs): 동결 전 고침 개발일지 추가` → CLAUDE.md push 전 점검(개수만) → push → PR(양식) 생성

- [ ] **Step 4: 화면 사진(Vercel 미리보기 주소)**

카테고리 화면을 PC 폭(1280)과 360px 폭으로, 질문 두 개를 한 뒤 첫 답의 이전 답 줄(펼친 상태)을 360px 폭으로 찍어 위 세 파일로 저장한다(deviceScaleFactor 2). 질문 API는 가짜 응답(같은 쪽 인용 2개)으로 가로채 AI를 부르지 않는다. 미리보기 주소가 막혀 있으면 로컬 서버로 찍고 그렇게 보고한다. 세탁기·건조기 아이콘이 보이는지, 이전 답 줄 숫자가 펼친 카드 수와 같은지 보고한다

- [ ] **Step 5: 상호 테스트 기록에 PR 번호 덧붙임(원문 그대로, `#번호`만 채움)**
  - D 2번 줄 끝에 ` 고친 PR: #번호(세탁기·건조기 타일 아이콘을 MDI로, 2026-11-27)`
  - D 4번 줄 끝(기존 "…고친 PR 번호는 고친 뒤 여기에 적는다)" 뒤)에 ` 고친 PR: #번호(이전 답 줄 숫자를 근거 카드 수로, 2026-11-27)`
  - 개발일지 절 제목 끝 `(`fix/phase2-freeze-fixes`)`를 `(`fix/phase2-freeze-fixes`, PR #번호)`로
  - 커밋 `docs(docs): 상호 테스트 기록에 동결 전 고침 PR 번호` → 점검 → push

- [ ] **Step 6: 보고하고 멈춤(병합은 채팅 Claude 대조 뒤)**

보고: 커밋 SHA 목록(테스트 커밋이 구현 커밋보다 앞), 받은 곳(npm/unpkg)과 세 파일 SHA-256, 전체 테스트 결과, 사진 세 장 위치와 본 것, PR 번호·미리보기 주소, push 전 점검 결과
