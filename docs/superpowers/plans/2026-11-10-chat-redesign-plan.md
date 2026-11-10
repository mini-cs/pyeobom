# v1.5 화면 개편(계획 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 1차 검색형 화면을 랜딩 → 카테고리 → 모델 → 채팅 흐름의 채팅형 화면으로 바꾼다. 대화는 브라우저에만 저장한다. 화면이 앞 대화(`history`)를 보내 이어지는 질문을 운영에서 켠다. 채택 조건 4개로 판단한다.

**Architecture:** 서버는 계획 2에서 끝났고, 작은 수정과 브랜드 안내 구분 값만 더한다. 화면은 `public/`의 정적 파일(HTML·CSS·JS, 빌드 없음)이다. 저장·앞 대화 규칙은 따로 시험할 수 있는 작은 JS 모듈로 나누고, 화면 흐름은 Playwright로 시험한다. 화면 개편은 **브랜치 하나·PR 하나**로 묶어 중간 상태가 운영에 나가지 않게 한다(사용자 결정, CLAUDE.md 규칙의 예외).

**Tech Stack:** Python 3.14·FastAPI(서버), 바닐라 JS ES 모듈·CSS(화면), Node v24 내장 테스트(`node --test`, 의존성 없음), Playwright(Python) 1.64.1·axe-core·Lighthouse·Locust·Promptfoo·Langfuse(측정)

**Spec:** `docs/superpowers/specs/2026-11-08-chat-redesign-design.md` 2~5·7~12절 · **시안:** `docs/design/시안-2026-11-08.html`(4·5번이 최종 스타일과 글자 체계) · **넘겨받은 것:** `docs/평가/v15-server.md` "계획 3으로 넘기는 것" · **결정기록:** 023·027·028·029 · **측정 절차:** `docs/평가/평가-규칙.md`

## 사용자 결정 (2026-11-10 채팅, 측정 전)

1. 이어지는 질문 평가에는 계획 2 세트(13대화·31턴)를 **다시 쓴다.** 방법을 고르는 용도가 아니라 회귀 확인용이다. 이 세트를 보고 프롬프트·화면·서버를 조정하지 않는다.
2. 시간 조건 비교 대상은 **같은 실행 안의 새 세트 1번째 턴(13개)**이다. 30문항 대비 값은 참고로만 적는다.
3. **DeepEval은 생략한다.** 설계 8절 "같은 방법으로 다시 잰다"의 명시적 예외다. 이유: 계획 3은 검색·답변 경로를 바꾸지 않는다(바뀌는 것은 답 자르기·이메일 가리기뿐).
4. **화면 지표를 채택 조건으로 넣는다**(아래 조건 4).
5. 회귀 기준점은 설계 정의 그대로다(1차 v2a 27/30 대비). 지금 main(26/30)으로 바꾸지 않는다.
6. 바꾸기 시간 제한은 **5초로 확정**한다(계획 2 채택 측정 `v15-k5`·`v15-fu-k5`의 `.settings.json`이 `rewrite_timeout_s: 5.0`, 차이 없음). OpenAI 클라이언트 재사용 측정은 계획 3 범위 밖이다(같이 바꾸면 조건 3에 두 변화가 섞임).
7. 계획 3 끝에 가벼운 사용자 테스트 2~3명 + 강사님 시연을 한다(11/10 사용자 결정, 저장소에는 이 계획이 첫 기록).
8. 장부는 `docs/평가/v15-ui.md`에 새로 만들고, 상한은 1.7달러다. 운영용 OpenAI 잔액은 최소 1달러를 남긴다.
9. 바꾼 질문 표시 문구는 **"'○○'로 찾았어요"**(설계 2절)로 한다. 설계 1절·11절의 "이렇게 이해했어요"는 결정기록 021에서 같은 줄을 가리키는 옛 이름으로 적는다.
10. **화면 개편(Task 3~8)은 PR 하나**로 묶는다. CLAUDE.md "기능 하나 = 브랜치 하나 = PR 하나"의 명시적 예외이고, 이유(main 병합 = 운영 배포라 반쯤 만든 화면이 나가지 않게)를 이 계획과 PR 본문, 결정기록 021에 남긴다.
11. **평가 도구를 화면 규칙에 맞춘다.** 이어지는 질문 평가 도구는 오류 턴을 앞 대화에서 빼고, 앞 답 1,000자 자르기는 서버 처리 코드에 넣어 평가에도 반영되게 한다. 측정 정의를 제품 동작과 같게 하는 수정이다(평가 세트에 맞춘 조정이 아님).
12. 보조 회색은 **`#6B6B6B` 하나**로 한다. 비교 초안(`docs/design/디자인-비교-2026-11-10.html` 2절)의 B안이다. 흰 바탕 5.33:1, 회색 카드 4.76:1로 WCAG AA를 통과한다. 설계·시안의 `#7A7A7A`(4.29:1·3.83:1)는 AA에 못 미쳐 바꾼다. 결정기록 024에 적는다.

## 채팅 Claude가 정한 기본값 (계획 PR 전에 사용자가 확인)

1. **앞 대화에 넣는 턴:** 찾지 못함·브랜드 안내 턴은 넣고, 오류 턴은 뺀다(저장도 하지 않음). 평가 도구도 같게 바꾼다(사용자 결정 11).
2. **바꾼 질문 숨김:** 바꾼 질문이 가린 질문과 같으면(앞뒤 공백 제거, 연속 공백 하나로 바꾼 뒤 비교) "로 찾았어요" 줄을 숨긴다.
3. **화면 이동:** 처음 열면 주소의 `#` 부분과 상관없이 항상 랜딩을 보여 준다(설계 "방문할 때마다 첫 화면"). 그 뒤로는 `#` 주소로 이동해 브라우저 뒤로 가기를 지원한다.
4. **대화가 생기는 때:** 첫 질문에 오류가 아닌 응답이 왔을 때 만든다. 빈 대화는 서랍에 남지 않는다.
5. **대화 제목**은 첫 가린 질문의 앞 30자, **카테고리 화면의 최근 대화 카드**는 3개다.
6. **글꼴:** Pretendard 공식 배포물의 웹 글꼴을 저장소에 두고(자체 호스팅) LICENSE를 함께 둔다. 직접 잘라 쓰지 않는다. 글꼴 순서는 Pretendard가 먼저다(시안 5번의 `-apple-system` 먼저 순서는 따르지 않음).
7. **JS 테스트:** Node 내장 `node --test`를 쓴다(새 의존성 없음).
8. **Playwright 화면 테스트(`ui` 표시)**는 마무리 명령 `pytest -m "not integration"`에 함께 돈다(AI 비용 없음). 전체 `ui` 테스트가 60초를 넘으면 멈추고 묻는다.
9. **1차 화면 파일**은 PR C에서 지운다. 1차 화면은 v1.0 태그, 시연 영상, `docs/design/screens/` 캡처로 남아 있다(1차 고유 배포 주소는 배포 보호로 잠겨 있음, 11/8 노션 기록).
10. **가린 판정지는 쓰지 않는다.** 비교할 방법이 하나뿐이라 가릴 이름이 없다(평가 규칙의 가린 판정지는 방법 비교용).
11. **시안과 설계가 다를 때는 설계를 따른다.** 시안 4·5번과 대조한 결과는 아래와 같이 정한다.
    - 이전 답: 답 본문과 근거를 함께 "이전 답 · 근거 N개" 한 줄로 접고, 누르면 펼친다(설계 2절 문장, 시안 5번)
    - 입력창 아래 "앞 대화를 기억해요 · 모델을 바꾸면 새 대화": 넣는다(설계 2절, 시안 3번)
    - 근거 카드: 쪽·제목·인용·링크(설계 2절). 링크 문구는 1차 그대로
    - 채팅 시작 화면 입력창 왼쪽 ← 버튼(시안 4번 ③): 넣지 않는다(설계에 없음, 뒤로 가기는 브라우저와 ☰)
    - 카테고리 점 표시: 넣는다(설계 2절)
    - 면 회색 `#F2F2F2`, 굵기 400/600/700, 크기 28/17/16/14/12(13)px(설계 3절)
    - 시안에 없는 화면(모델 선택, 서랍, 찾지 못함·브랜드 안내·오류 상태)은 설계 2절과 같은 부품으로 만든다

## 채택 조건 (측정 전 확정, 측정 후 변경 금지)

이 계획을 커밋하는 PR 0이 측정 전 기록이다. 못 맞추면 미채택이나 이유를 남긴 명시적 예외로 처리한다(사용자 결정).

1. **회귀 30문항(앞 대화 없음):** 사람 판정. 1차 v2a 27/30에서 2개 넘게 떨어지지 않아야 한다(25/30 이상). 환각 0. **채택 판정은 Task 8 실행(`v15-ui`)으로 한다.** Task 1 실행(`v15-ui-server`)은 같은 기준으로 PR A 병합 여부만 정한다.
2. **이어지는 질문(계획 2 세트):** 바꾸기 정확도와 정답률이 각각 80% 이상이고 환각 0. 분모와 판정 방법은 `docs/평가/v15-server.md`의 계획 2 정의를 그대로 옮겨 적는다. 앞 대화는 화면과 같은 규칙으로 만든다(사용자 결정 11).
3. **시간:** 같은 실행 안에서 새 세트 1번째 턴(13개) 평균 대비 2~3번째 턴(18개) 평균 증가가 1.5초 이내. Langfuse 로컬, 운영 설정. 규칙으로 막힌 응답은 평균에서 뺀다(평가 규칙).
4. **화면(미리보기):**
   - axe: 아래 상태 모두에서 위반(violations) 0. 확인 필요(incomplete)는 목록으로 남기고 사람이 확인한다.
     - 대상 상태: 랜딩(대화 없음·있음), 카테고리, 모델(세탁기·에어컨), 채팅(빈 화면·찾는 중·답·이어지는 답과 접힌 이전 답·찾지 못함·브랜드 안내·오류·저장 실패 안내), 서랍(열림), 전체 삭제 확인
   - Lighthouse: 랜딩, 모바일 설정, 3회 중앙값. CLS 0.1 이하, LCP 2.5초 이하(Core Web Vitals "좋음" 기준. 리포트에 web.dev 원문 출처를 적는다)
   - 설계 7절 화면 확인 5개를 사람이 확인해 통과: 360px, 키보드만, 동작 줄이기, 시크릿 모드, 대화 삭제·전체 삭제

**사람 판정 이어받기:** 바뀐 문항만 새로 판정하고, 나머지는 바로 앞 사람 판정을 이어받는다. Task 1은 `v15-code`를, Task 8은 `v15-ui-server`를 이어받는다.

## 브랜치와 PR

| PR | 브랜치 | 담는 것 | 운영 동작 |
| --- | --- | --- | --- |
| 0 | `docs/plan3-chat-redesign` | 이 계획, AI 실수 기록, 11/10 개발일지(PR #50 줄, 오늘 사용자 결정) | 바뀌지 않음 |
| A | `fix/v15-ui-server` | Task 1 | 바뀜(이메일 가리기, 응답 `reason`) |
| B | `docs/v15-design-guide` | Task 2 | 바뀌지 않음 |
| C | `feat/v15-chat-ui` | Task 3~8(사용자 결정 10) | 바뀜(새 화면, 이어지는 질문 켜짐) |
| D | `docs/v15-ui-records` | Task 9 | 바뀌지 않음 |

- 브랜치는 한 번에 하나만 쓴다. 이전 PR을 병합한 뒤 최신 main에서 다음 브랜치를 만든다.
- 모든 PR은 push·PR 생성·병합 **직전에 멈추고** 사용자 확인을 받는다(CLAUDE.md).

## Global Constraints

- `history`가 없는 요청은 지금 운영과 같게 동작한다. 기존 단위 테스트 370개가 모두 통과해야 한다(화면 파일에 묶인 테스트는 Task 3·4·5에서 새 화면에 맞게 고침).
- 답변 AI에는 앞 대화를 넘기지 않는다(`test_answer_ai_never_receives_history_text` 유지).
- 브라우저에는 **서버가 돌려준 가린 질문만** 저장한다. 서버에는 대화를 저장하지 않고, 질문 원문을 서버 기록에 남기지 않는다.
- 앞 대화는 최근 3턴의 가린 질문과 답 본문만 보낸다. 근거 원문은 보내지 않는다.
- 화면 코드는 디자인 가이드의 토큰만 쓴다(CLAUDE.md). 새 값이 필요하면 가이드에 먼저 추가한다.
- 360px 먼저. 입력창 16px 이상, 누르는 요소 44px 이상, 색 대비 WCAG AA, 모든 조작을 키보드로 할 수 있어야 한다. "동작 줄이기"에서는 움직임을 끈다.
- 저장 한도는 대화 20개, 대화당 질문 30개다. 넘치면 오래된 것부터 지운다.
- 개인정보 시험 값은 누가 봐도 가짜인 값만 쓴다(010-1234-5678, test@example.com, 가나다로 123).
- AI 비용은 장부에 먼저 적고 `check_budget`을 통과한 뒤 실행한다(통합 테스트 포함). 상한 1.7달러, 운영 잔액 최소 1달러.
- 측정은 운영 설정으로 하고 `.settings.json`을 남긴다. 미리보기 우회 값은 측정 직전에 사용자가 만들고 측정 후 지운다.
- 확인용 세트는 열지 않는다. 계획에 없는 판정 규칙이 필요하면 집계 전에 멈추고 묻는다.
- 코드가 바뀌는 Task는 **테스트 커밋 → 구현 커밋** 두 번으로 나눈다(CLAUDE.md).
- Vercel 동작(정적 파일 경로, Content-Type)은 미리보기에서 확인하고, 모르는 동작은 공식 문서로 확인한다(CLAUDE.md).

## Review Focus

1. **개인정보가 든 원래 질문이 브라우저 저장소에 남음**(오류 응답 포함) → Task 5에서 저장소 전체 문자열에 가짜 번호가 없는지 검사
2. **저장 실패나 깨진 저장 데이터 때문에 화면이 멈춤**(시크릿 모드, 공간 부족, 다른 버전) → Task 3의 `loadConversations`·`saveConversation` 테스트, Task 5의 저장 실패 화면 테스트
3. **다른 모델이나 다른 대화의 앞 대화가 요청에 섞임**(모델 바꾸기, 서랍에서 지난 대화 열기) → Task 6의 요청 본문 검사
4. **탭 두 개에서 쓰면 한쪽 대화가 사라짐** → Task 3의 저장 직전 다시 읽기 테스트
5. **앞 대화 답을 자르다가 개인정보 조각이 덜 가려진 채 AI로 감** → Task 1의 "가리기 먼저, 자르기 나중" 테스트

---

### Task 0: 계획 PR (PR 0, 문서만)

- [ ] **Step 1:** 이 계획, 디자인 비교 초안(`docs/design/디자인-비교-2026-11-10.html`: 1절 글꼴, 2절 보조 회색. Pretendard 1.3.9 공식 부분 집합을 파일 안에 넣었고, 머리 주석에 저작권 고지와 OFL 원문이 있음), 커밋하지 않고 둔 AI 실수 기록(개발일지 2줄, `docs/AI-실수-기록.md` 2줄), 11/10 개발일지의 PR #50 줄을 담는다. 11/10 개발일지 사용자 결정 절에 위 "사용자 결정" 1~12 중 아직 없는 것을 덧붙인다.
- [ ] **Step 2:** `docs/Claude outputs/` 폴더는 담지 않는다. 채팅에서 받은 파일을 옮겨 둔 임시 폴더다.
- [ ] **Step 3: Commit** → push·PR 직전 멈춤 → 사용자 확인 후 PR → 병합 직전 멈춤

---

### Task 1: 서버 수정과 브랜드 안내 구분, 평가 도구 맞추기 (PR A, 운영 동작 변경)

**Files:**
- Modify: `app/input_guard/pii.py`(이메일), `app/ask/routes.py:28`(앞 대화 답 길이), `app/ask/service.py`(`mask_history` 다음 답 자르기, 막힌 응답의 `reason`), `app/answer/rewrite.py`(실패 시연 때 건너뛰기), `evaluation/followups.py`(오류 턴 빼기)
- Modify: `docs/결정기록/023-질문-바꾸기.md`(시간 제한 5초 확정, 덧붙이기)
- Test: 기존 개인정보 테스트 파일, `tests/ask/test_ask_history.py`, `tests/core/test_brand_guard.py`, 평가 도구 테스트

**Interfaces:**
- Produces: 응답 `reason: "other_brand" | null`. `guard_message`가 막은 응답(브랜드 이름 규칙, 다른 브랜드 에러 코드 규칙 **둘 다**)에만 `"other_brand"`가 들어간다. Task 5가 이 값을 쓴다.
- 참고: `mask_pii(text) -> (str, bool)` 쌍을 돌려준다.

- [ ] **Step 0: 답 길이 상한 정하기.** 1,000자 거절을 없애면 요청 본문의 앞 대화 답에 상한이 없어진다. 답변 AI의 출력 토큰 제한으로 서버 답의 최대 글자 수를 계산해 보고한다. 상한 값은 사용자가 정한다(제안: 4,000자. 넘으면 `INVALID_REQUEST`, 그 아래는 받아서 1,000자로 자름).
- [ ] **Step 1: 실패하는 테스트 작성**
  - 이메일(가리는 범위는 지금 정규식 그대로 찾고, 끝부분만 돌려준다)
    - `mask_pii("test@example.com으로 보내 주세요")[0] == "[이메일]으로 보내 주세요"`
    - `mask_pii("메일은 a.b-c@mail.co.kr로 주세요")[0] == "메일은 [이메일]로 주세요"`
    - `mask_pii("TEST@EXAMPLE.COM")[0]`에 `@`가 없음
    - 한글 도메인: `mask_pii("test@예시.한국으로")[0] == "[이메일]으로"`, `mask_pii("test@예시.한국")[0] == "[이메일]"`
    - 위 경우 모두 `mask_pii(...)[1] is True`
    - 기존 개인정보 테스트(오탐 허용 사례)는 모두 그대로 통과(결정기록 015 "미탐보다 오탐 허용")
  - 앞 대화 답
    - 1,500자 → 거절하지 않음. 바꾸기 AI에 들어간 답은 1,000자 이하
    - 990번째 글자 근처에 `test@example.com` → 바꾸기 AI 입력에 `test@`가 없음(가리기 먼저, 자르기 나중)
    - Step 0에서 정한 상한을 넘는 답 → `INVALID_REQUEST`
    - 자르기는 `answer_question` 안에서 일어남(평가 도구는 HTTP를 거치지 않고 `answer_question`을 부름, `evaluation/__main__.py:56-62`)
  - 새 질문 501자, 앞 대화 질문 501자 → 지금처럼 `INVALID_REQUEST`
  - 실패 시연(FORCE_FAIL)이 켜진 상태 + `history` → 바꾸기 모의 객체 호출 0회, 지금과 같은 실패 응답
  - `reason`: 브랜드 이름 규칙으로 막힘 → `"other_brand"`. 다른 브랜드 에러 코드 규칙으로 막힘(기존 `test_brand_guard` 사례) → `"other_brand"`. 일반 찾지 못함 → `null`
  - 평가 도구: 2번째 턴이 오류인 대화 → 3번째 턴의 `history`에 2번째 턴이 없음
- [ ] **Step 2: Run** `pytest -m "not integration"` → 새 테스트 FAIL → **Commit(테스트)**
- [ ] **Step 3: 구현.**
  - 이메일은 찾은 끝부분에서 두 경우만 돌려준다: (1) 영문으로 끝나는 마지막 덩어리 뒤에 붙은 한글 (2) 마지막 덩어리가 한글이면 끝의 조사(긴 것부터: 으로, 에서, 에게, 까지, 부터, 이랑, 한테, 로, 에, 은, 는, 이, 가, 을, 를, 도, 와, 과, 의, 만, 랑, 께). 가리는 범위는 이 두 경우에만 줄어든다.
  - `routes.py`는 1,000자 거절을 Step 0 상한으로 바꾸고, 자르기는 `service.py`의 `mask_history` 다음에 둔다.
- [ ] **Step 4: Run** `pytest -m "not integration"` → 전체 PASS → **Commit(구현)**
- [ ] **Step 5:** 023에 "바꾸기 시간 제한 5초 확정(2026-11-10 사용자 결정, 계획 2 채택 측정 설정과 같음)"을 덧붙인다.
- [ ] **Step 6:** 장부(`docs/평가/v15-ui.md` 새로 만듦)에 30문항 예상 비용을 적고 `check_budget` → `python -m evaluation --label v15-ui-server`. 바뀐 문항만 사용자가 사람 판정하고, 나머지는 `v15-code` 판정을 이어받는다. 조건 1 기준(25/30 이상, 환각 0)으로 PR A 병합 여부를 정한다.
- [ ] **Step 7:** push·PR 직전 멈춤 → PR → 미리보기에서 가짜 이메일이 든 질문 1개를 확인한다(한글 본문은 UTF-8 파일로 보냄) → 병합 직전 멈춤

---

### Task 2: 디자인 가이드 개정과 결정기록 024 (PR B, 문서만)

**Files:**
- Modify: `docs/design/디자인-가이드.md`(v1.5 판으로 다시 씀, 머리에 날짜와 1차 판과 바뀐 점)
- Create: `docs/결정기록/024-디자인-체계.md`

- [ ] **Step 1:** 설계 3절 값으로 토큰을 다시 정한다.
  - 색: 바탕 `#FFFFFF`, 본문 `#111111`, 보조 글자 `#6B6B6B`(사용자 결정 12), 면 `#F2F2F2`, 테두리 `#DADADA`. 포인트 색은 없음
  - 오류·개인정보 안내 색은 대비를 계산해 정한다
  - 글꼴: Pretendard, 대체 글꼴은 기기 기본 한글 글꼴
  - 크기: 28/17/16/14/12(13)px, 굵기 400/600/700, 줄 간격 1.5~1.6
  - 부품: 검은 알약 버튼, 회색 알약 입력창, 회색 네모 타일, 회색 추천 카드
  - 1차 토큰 중 쓰지 않게 되는 것(청록 등)은 지운다고 적는다
- [ ] **Step 2:** 가이드에 **글자색·바탕색 쌍마다 대비 값**을 표로 적는다(계산 스크립트 출력 그대로). 4.5:1(큰 글자는 3:1) 미만인 쌍이 있으면 고친다.
- [ ] **Step 3:** 레퍼런스 표를 고친다. 채팅 말풍선·아래 고정 입력창은 이번에 가져온다. 1차 "가로 스크롤 쓰지 않음" 규칙은 "카테고리 타일·추천 카드만 옆으로 넘김, 화살표 키 지원, 점 표시"로 바꾼다. 움직임 절에 동작 줄이기 규칙을 넣는다. 시안 경로를 적는다.
- [ ] **Step 4: 라이선스 확인.** 확인하지 못한 항목은 "확인하지 못함"으로 적는다.
  - Pretendard(https://github.com/orioncactus/pretendard, 쓸 버전의 LICENSE 원문): 라이선스 이름, 예약 글꼴 이름 조항, 자체 호스팅 시 LICENSE를 함께 두는 조건
    - 채팅 Claude가 npm `pretendard@1.3.9`에서 확인한 것(쓸 버전으로 다시 확인): `package.json` license `OFL-1.1`. `dist/LICENSE.txt` 첫 줄 "with Reserved Font Name Pretendard"(예약 이름이 있어서 직접 잘라 쓰면 이름을 바꿔야 함 → 공식 파일만 씀)
    - 공식 웹 글꼴: `woff2-subset`(3,728글리프, 굵기마다 약 267~271KB), `woff2-dynamic-subset`(828개 파일, 합계 약 12MB, 쓰는 글자 범위만 내려받음), 전체 `woff2`(굵기마다 약 766~791KB)
    - 정할 것: 부분 집합에 없는 드문 한글이 설명서 답에 나오면 그 글자만 기본 글꼴로 보인다. 설명서 원문 글자가 부분 집합 안에 드는지 세어 보고 `woff2-subset`과 동적 부분 집합 중 하나를 고른다. Lighthouse 조건(LCP)과 함께 본다
  - 시안이 쓴 Tabler Icons: 라이선스와, 아이콘 SVG를 저장소에 둘 때의 조건
- [ ] **Step 5:** 결정기록 024에 사실(설계 값, 대비 계산, 라이선스), 결정(보조 회색, 기본값 6), 앞으로(구현 후 axe로 대비 재확인)를 적는다.
- [ ] **Step 6: Commit** → push·PR 직전 멈춤 → PR → 병합 직전 멈춤(문서만이라 운영 영향 없음)

---

### Task 3: 저장·앞 대화 규칙 모듈 (PR C 시작)

**Files:**
- Create: `public/js/store.js`, `public/js/history.js`
- Modify: `pytest.ini`(`markers`에 `ui` 등록), `tests/web/test_public_page.py:38`(innerHTML 금지 검사를 `public/` 아래 모든 `.js`로 넓힘)
- Test: `tests/web/js/store.test.mjs`, `tests/web/js/history.test.mjs`

**Interfaces:**
- Produces (`store.js`):
  - `STORE_KEY = "pyeobom.conversations"`, `STORE_VERSION = 1`, `LIMITS = { conversations: 20, turns: 30 }`
  - 저장 모양: `{ version: 1, conversations: Conversation[] }`
  - `Conversation = { id, model_id, title, created_at, updated_at, turns: Turn[] }`. 시각은 ISO 문자열
  - `Turn = { question_masked, rewritten_question, answer, found, citations, kind }`, `kind`는 `"answer" | "not_found" | "other_brand"`
  - `loadConversations(storage) -> Conversation[]`: 예외를 던지지 않는다. `updated_at` 최신순
  - `saveConversation(storage, conversation) -> boolean`: 저장 직전에 다시 읽고 `id`로 넣거나 바꾼 뒤 한도를 적용해 쓴다. 어떤 예외든 `false`
  - `deleteConversation(storage, id) -> boolean`, `deleteAllConversations(storage) -> boolean`
  - `toStoredTurn(response) -> Turn | null`: 오류 응답이면 `null`. 위 6개 항목만 담는다. 원래 질문 항목은 만들지 않는다. `reason == "other_brand"`이면 `kind = "other_brand"`
  - `makeTitle(questionMasked) -> string`: 앞 30자
- Produces (`history.js`):
  - `buildHistory(turns) -> {question, answer}[]`: 마지막 3턴, 순서 유지, `question = question_masked`, `answer = answer`
  - `shouldShowRewritten(questionMasked, rewritten) -> boolean`

- [ ] **Step 1: Node 모듈 확인.** Node v24의 `node --test`가 `package.json` 없이 `public/js/*.js`(ES 모듈 문법)를 불러오는지 작은 시험 파일로 확인한다. 안 되면 멈추고 보고한다(선택지: `.mjs` 확장자, `type: module` 설정).
- [ ] **Step 2: 실패하는 테스트 작성**(가짜 `storage` 객체를 넘김)
  - 불러오기: 빈 저장소 → `[]`. `"{"` → `[]`. `{version: 99}` → `[]`. `getItem`이 예외 → `[]`
  - 저장: `setItem`이 예외 → `false`, 예외가 밖으로 나오지 않음
  - 21번째 대화 저장 → 20개, `updated_at`이 가장 오래된 것이 빠짐. 31번째 턴 → 30개, 가장 오래된 턴이 빠짐
  - 탭 두 개: 대화 A를 저장한 뒤, A를 모르는 상태에서 대화 B를 저장 → A·B 모두 남음
  - `toStoredTurn`: 오류 응답 → `null`. 결과 키가 정확히 6개이고 `question` 키가 없음. `reason: "other_brand"` → `kind == "other_brand"`
  - `buildHistory`: 5턴 → 마지막 3턴. 각 항목의 키는 `question`·`answer`뿐이고 `citations`는 없음
  - `shouldShowRewritten`: `null` → `false`. `"  IE  에러 "`와 `"IE 에러"` → `false`. 다른 문장 → `true`
  - innerHTML 금지 검사가 `public/js/*.js`도 봄
- [ ] **Step 3: Run** `node --test tests/web/js/` → FAIL → **Commit(테스트)**
- [ ] **Step 4:** 구현
- [ ] **Step 5: Run** `node --test tests/web/js/` + `pytest -m "not integration"` → PASS → **Commit(구현)**

---

### Task 4: 화면 뼈대·랜딩·카테고리·모델, 글꼴과 아이콘

**Files:**
- Modify: `public/index.html`, `public/styles.css`, `public/app.js`(화면 전환 담당으로 다시 씀), `models.json`(`product_url` 추가)
- Create: `public/fonts/`(Pretendard 웹 글꼴 + LICENSE), 쓰는 아이콘 SVG(Task 2 Step 4의 라이선스 조건대로)
- 이미 있음: `public/images/models/<model_id>.svg` 3장(파일 이름 = 모델 ID, PR #50). 카테고리는 기존 `appliance` 값(`washer`/`aircon`)을 쓴다
- Test: `tests/web/test_ui_flow.py`(`ui` 표시, 로컬 정적 서버, `/api/ask`는 가로챔), `tests/web/test_public_page.py:33`(토큰 검사를 새 토큰으로)

**Interfaces:**
- 주소: `#category`, `#model/<appliance>`, `#chat/<model_id>`(새 대화), `#chat/<model_id>/<conversation_id>`
- Consumes: `loadConversations`(최근 대화 카드)

- [ ] **Step 1: AI 그림 안내 검토(사용자 결정).** 화면 아래에 "모델 그림은 AI로 그린 일러스트예요" 안내를 넣을지 사용자와 정한다. SVG의 C2PA 출처 정보는 지우지 않는다(11/10 사용자 결정).
- [ ] **Step 2: 공식 제품 주소.** `models.json`의 `official_url`은 설명서 내려받기 페이지다. 모델 카드의 "공식 사이트에서 제품 보기"에는 사용자가 공식 사이트에서 확인한 제품 주소만 `product_url`로 넣는다. 받기 전에는 멈추고 요청한다.
- [ ] **Step 3: Playwright 확인.** 크로미움이 설치돼 있지 않으면 `python -m playwright install chromium`으로 설치한다.
- [ ] **Step 4: 실패하는 테스트 작성**
  - `#chat/...` 주소로 처음 열어도 랜딩이 보임
  - 시작하기 → 카테고리 → 세탁기 → 모델 카드 2장, 에어컨 → 1장. 카드마다 그림이 `public/images/models/<model_id>.svg`
  - 뒤로 가기: 모델 → 카테고리 → 랜딩
  - 화면마다 보이는 h1이 정확히 1개이고, `aria-hidden` 안에 있지 않음. 화면을 바꾸면 포커스가 그 화면의 h1로 감
  - 카테고리 타일에서 오른쪽 화살표 → 다음 타일로 포커스. "곧 추가" 타일은 `aria-disabled="true"`. 점 표시가 있음
  - 저장된 대화가 있으면 랜딩에 카드 1개, 카테고리에 카드 최대 3개
  - `test_public_page.py`: 새 색·글꼴·크기 토큰이 가이드 값과 같음
- [ ] **Step 5: Run** `pytest -m ui tests/web/test_ui_flow.py` → FAIL → **Commit(테스트)**
- [ ] **Step 6: 구현.** 배치와 문구는 시안 4·5번과 설계 2절을 따르고, 둘이 다르면 기본값 11대로 한다(랜딩 제목, 설명 3줄, 시작하기, 비영리·저작권 안내, 모델명 찾는 법은 1차 문구 재사용). 글꼴은 `font-display: swap`을 쓰고, 대체 글꼴로 넘어갈 때 줄이 크게 밀리지 않게 한다.
- [ ] **Step 7: Run** `pytest -m "not integration"`(ui 포함) + `node --test tests/web/js/` → PASS → **Commit(구현)**

---

### Task 5: 채팅 화면

**Files:**
- Modify: `public/app.js`, `public/styles.css`, `public/index.html`
- Create: `public/js/examples.js`(1차 `public/app.js:5`의 `const EXAMPLES = {...}`를 옮김)
- Test: `tests/web/test_ui_flow.py`, `tests/web/test_public_page.py:49-51`(모델당 예시 2개 검사를 `examples.js`로), `tests/core/test_brand_guard.py:56,128`(예시 질문 읽는 경로를 `examples.js`로)

**Interfaces:**
- Consumes: `buildHistory`, `shouldShowRewritten`, `toStoredTurn`, `saveConversation`, `makeTitle`(Task 3), 응답 `reason`(Task 1)
- 요청: `POST /api/ask {model_id, question, history?}`. `history`가 비면 보내지 않는다

- [ ] **Step 1: 실패하는 테스트 작성**(`/api/ask`는 가짜 JSON으로 응답)
  - 개인정보: "제 번호는 010-1234-5678이에요 IE 에러" 전송 → 가짜 응답의 `question_masked`가 말풍선에 보임. 저장소 전체 문자열에 `010-1234-5678`이 없음. 504 오류 응답일 때도 없음
  - 두 번째 질문의 요청 본문 `history` 길이 1, `history[0].question`은 첫 `question_masked`. 다섯 번째 질문 → 3개
  - 오류 턴 다음 질문 → `history`에 오류 턴이 없음. 오류 카드의 다시 시도 → 같은 질문·같은 `history`로 다시 보냄
  - 바꾼 질문이 같으면 "로 찾았어요" 줄이 없고, 다르면 "'<바꾼 질문>'로 찾았어요"가 보임
  - `reason: "other_brand"` → 브랜드 안내 상태(찾지 못함 상태와 구분되는 요소). 문구와 링크는 서버 응답 그대로
  - 최근 답만 본문과 근거가 펼쳐짐. 이전 답은 본문과 근거가 함께 "이전 답 · 근거 N개" 버튼(`aria-expanded="false"`) 한 줄로 접히고, 누르면 펼쳐짐
  - 연타 방지: 응답을 기다리는 중 Enter 두 번 → 요청 1번
  - 저장 실패(`setItem`이 예외를 던지게 주입) → "이 대화는 저장되지 않아요"가 대화당 1번 보이고, 답은 정상 표시
  - 첫 질문에 오류가 오면 대화가 저장되지 않음
  - `examples.js`: 모델마다 예시 2개(1차 검사 이어받음), 예시 질문 전부가 각자의 모델에서 브랜드 규칙에 걸리지 않음
- [ ] **Step 2: Run** → FAIL → **Commit(테스트)**
- [ ] **Step 3: 구현.** 설계 2절 ④와 기본값 11을 따른다.
  - 위쪽 막대(☰, 모델 이름, 새 대화), 대화 없을 때 추천 카드, 아래 고정 입력창
  - 입력창 아래 안내 "앞 대화를 기억해요 · 모델을 바꾸면 새 대화"
  - 1차 상태 유지: 찾는 중, 찾지 못함 + 공식 고객센터, 오류 카드 + 다시 시도, 개인정보 안내, 500자 표시
  - 기다리는 동안 말풍선은 입력한 문장을 보여 주고, 응답이 오면 가린 질문으로 바꾼다. 저장은 가린 질문만 한다
- [ ] **Step 4: Run** 전체(`pytest -m "not integration"`, `node --test`) → PASS → **Commit(구현)**

---

### Task 6: 지난 대화 서랍과 삭제

**Files:**
- Modify: `public/app.js`, `public/styles.css`, `public/index.html`
- Test: `tests/web/test_ui_flow.py`

**Interfaces:**
- Consumes: `loadConversations`, `deleteConversation`, `deleteAllConversations`(Task 3)

- [ ] **Step 1: 실패하는 테스트 작성**
  - 모델 A 채팅 중 서랍에서 모델 B 대화를 열고 질문 → 요청 `model_id`가 B이고, `history`는 B 대화의 마지막 턴들
  - 대화 카드: 제목(가린 첫 질문), 모델 이름, 날짜
  - 대화 삭제 → 목록과 저장소에서 사라짐
  - 전체 삭제: 확인 단계에서 취소하면 그대로, 확인하면 비워짐(브라우저 기본 `confirm` 창 대신 화면 안의 확인 단계)
  - 서랍을 연 뒤 Esc → 닫히고 포커스가 ☰로 돌아감
  - 안내 "대화는 이 기기에만 저장돼요. 공용 기기라면 다 쓴 뒤 지워 주세요."가 보임
- [ ] **Step 2: Run** → FAIL → **Commit(테스트)**
- [ ] **Step 3:** 구현(어느 화면에서든 ☰로 열림, 서랍 안에 "새 대화")
- [ ] **Step 4: Run** 전체 → PASS → **Commit(구현)**

---

### Task 7: 1차 화면 정리와 로컬 접근성 검사

**Files:**
- Modify/Delete: 1차 전용 코드(소개 영역 접기와 `aria-hidden`, `#examples`의 role 없는 `aria-label`, 쓰지 않는 CSS 토큰)
- Modify: `measure/`의 axe 스크립트(조건 4의 상태 목록으로 바꿈)
- Test: `tests/web/test_ui_flow.py`

- [ ] **Step 1: 실패하는 테스트 작성**
  - 동작 줄이기를 흉내 내면 서랍·타일·이전 답 펼침의 `transition-duration`이 `0s`
  - 답이 도착해도 아래쪽 안내 영역의 위치가 바뀌지 않음(1차 CLS 0.080의 원인이었던 footer 이동)
- [ ] **Step 2: Run** → FAIL → **Commit(테스트)**
- [ ] **Step 3:** 정리와 구현 → **Commit(구현)**
- [ ] **Step 4:** axe 스크립트를 **로컬 정적 서버**에서 조건 4의 상태 목록 전부에 돌린다. 이 서버에는 `/api/ask`가 없으니 AI 비용이 들 수 없다. 위반이 있으면 고친다(테스트 → 구현 커밋). 채택 판단용 측정은 Task 8에서 미리보기로 한다.
- [ ] **Step 5: Run** 전체 → PASS
- [ ] **Step 5-1:** 로컬 Lighthouse로 개발 확인(채택 측정 아님). LCP·CLS가 조건(LCP 2.5초, CLS 0.1)에 가까우면 Task 8 전에 멈추고 보고한다. (결정기록 024: 글꼴은 `woff2-subset`)
- [ ] **Step 6:** push·PR 직전 멈춤 → PR C 열기(본문에 사용자 결정 10의 예외와 이유) → 미리보기에서 확인
  - `/js/*.js`, `/fonts/*`, 아이콘·모델 SVG가 200이고 Content-Type이 맞는지(JS 모듈은 JavaScript 형식이어야 불러와짐)
  - 병합하지 않음

---

### Task 8: 측정과 채택 판단 (PR C 미리보기)

**Files:**
- Modify: `docs/평가/v15-ui.md`(리포트 + 장부)

- [ ] **Step 1:** 리포트 맨 위에 채택 조건 4개, axe 상태 목록, Lighthouse 대상, 사람 판정 이어받기 규칙을 이 계획 그대로 옮겨 적고 커밋한다(계획 PR 0이 측정 전 기록이고, 리포트는 그 복사).
- [ ] **Step 2:** 측정마다 장부에 예상 비용을 적고 `check_budget`을 통과시킨다. DeepEval은 넣지 않는다.
- [ ] **Step 3: 앞 대화 만드는 방법 확인.** 평가 도구(`--followups`)가 화면 규칙과 같은지 다시 확인한다(같은 실행에서 받은 실제 앞 답, 가린 질문 + 답 본문, 최근 3턴, 오류 턴 제외, 답 1,000자 자르기는 서버에서). 다르면 **멈추고 보고한다.**
- [ ] **Step 4: 실행**(운영 설정, Langfuse 로컬)
  - `python -m evaluation --label v15-ui`
  - `python -m evaluation --followups --label v15-ui-fu`
- [ ] **Step 5: 사용자 사람 판정**
  - 30문항: 바뀐 문항만 판정하고 나머지는 `v15-ui-server` 판정을 이어받는다
  - 세트: `human_rewrite_ok`·`human_verdict`
- [ ] **Step 6: 미리보기 측정**(우회 값은 사용자가 측정 직전에 만들고 측정 후 지움)
  - Lighthouse: 랜딩, 모바일, 3회
    - 참고 측정(조건 아님): 랜딩에는 모델 그림이 없으므로 모델 화면도 3회 잰다. SVG 3장 크기(C2PA 포함)와 함께 적는다
  - axe: 상태 목록 전부. `/api/ask`는 가로챈다
    - 가로채기 확인: 가로채기 함수가 응답한 수 = 화면이 보낸 `/api/ask` 수. 측정 시간대 미리보기 함수 기록에 `/api/ask` 호출 0건
  - Locust: 깨운 뒤 동시 5명 × 1분, `history` 없음 / 1개 각각
  - Promptfoo: 계획 2 사례 6개(앞 대화에 숨긴 지시 2개 포함)
- [ ] **Step 7: 사용자 화면 확인 5개.** 리포트의 체크리스트에 결과를 적는다.
  - 포커스 링이 흰 바탕과 회색 면 위에서 잘 보이는지(결정기록 024, 입력창 A안 예외)
- [ ] **Step 8:** 조건별 판정표를 만든다.
  - 참고 기록: 30문항 대비 시간, 바꾸기 성공률과 실패 사유, Promptfoo·Locust 결과
  - 실제 비용 합계와 OpenAI 사용량 화면 대조(사용자 확인)
  - 못 맞춘 조건은 미채택 또는 명시적 예외로, 사용자가 정한다
- [ ] **Step 9: Commit** → push 직전 멈춤 → 병합 직전 멈춤 → 사용자가 PR C를 병합(= 운영에서 이어지는 질문이 켜짐)

---

### Task 9: 병합 후 점검과 기록 (PR D)

**Files:**
- Create: `docs/결정기록/021-채팅형-개편.md`, `022-대화-브라우저-저장.md`, `025-제품-그림.md`
- Modify: README(화면 흐름, API의 `history`·`reason`), 개발일지, `docs/AI-실수-기록.md`

- [ ] **Step 1:** 운영 배포 Ready를 확인한다. 장부에 적은 뒤 운영에서 질문 1개 + 이어지는 질문 1개를 확인한다.
- [ ] **Step 2:** 결정기록을 쓴다.
  - 021: 007 검색형·012 소개 영역을 이어받아 바꾼 이유, 화면 개편을 PR 하나로 묶은 예외(사용자 결정 10), "이렇게 이해했어요" → "'○○'로 찾았어요"(사용자 결정 9)
  - 022: 가린 질문만 저장, 한도, 버전, 오류 턴 제외, 앞 대화에 넣는 턴
  - 025: 일러스트로 통일한 이유, 설계 4절 조사 결과, C2PA 출처 정보 유지(11/10 사용자 결정)
- [ ] **Step 3:** v1.0 태그가 있는지 확인한다. 1차 고유 배포 주소는 배포 보호로 잠겨 있어 시연 영상과 캡처로 남겼다(11/8 노션). 리포트에는 이 사실만 적는다.
- [ ] **Step 4:** 계획 전체 최종 검토(executing-plans의 새 검토자 단계). 지적 사항은 고치거나 이유를 남긴다.
- [ ] **Step 5: Commit** → push·PR 직전 멈춤 → PR → 병합 직전 멈춤. 진행 기록 폴더 정리

---

### Task 10: 가벼운 사용자 테스트와 강사님 시연

- [ ] **Step 1:** 테스트 전에 채팅에서 관찰 항목, 성공 기준, 기록 방법(개인정보 없이)을 사용자와 정한다. 정하기 전에는 진행하지 않는다.
  - 출발점(11/9 노션): 1인 20~30분. 답과 근거를 믿을 수 있나, 이어서 묻는 게 자연스럽나, 어디서 막히나
  - 출발점 추가(결정기록 024): 입력창을 바로 찾는지
- [ ] **Step 2:** 장부에 예상 비용을 적고 2~3명 테스트 + 강사님 시연을 진행한 뒤, 결과를 리포트에 적는다.
- [ ] **Step 3:** 고칠 점은 "나중에" 목록에 넣는다. 이번 계획에서 바로 고치지 않는다(조건을 다시 재야 하므로).
