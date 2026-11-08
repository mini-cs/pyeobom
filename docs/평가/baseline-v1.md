# 1차 기준값 (Baseline v1)

개편(v1.5) 전에 1차 펴봄을 도구 6개로 잰 기록이다. 개편 후 같은 방법으로 다시 재서 비교한다. 설계: `docs/superpowers/specs/2026-11-08-chat-redesign-design.md` 8절, 계획: `docs/superpowers/plans/2026-11-08-baseline-v1-measurement.md`.

## 기준점

| 항목 | 값 |
|---|---|
| git 태그 | `v1.0` → `95f5251` (PR #20 병합, 1차 마지막 `main` 커밋) |
| 1차 운영 배포 고유 주소 | https://pyeobom-oue4aabnu-mini-0fbe.vercel.app (2026-11-02 배포, Ready) |
| 운영 주소 | https://pyeobom.vercel.app (개편을 반영하기 전까지 1차와 같음) |

- **고유 주소 공개 여부(2026-11-08 확인):** 로그인 없이 열면 302로 Vercel 로그인 화면으로 넘어간다. Vercel 배포 보호가 운영 도메인 말고 배포별 주소에도 걸려 있어서다. 포트폴리오에서 1차 화면을 보여 주려면 보호 설정을 바꾸거나 다른 방법이 필요하다. 설정은 바꾸지 않았다(사용자 결정).
- **1차 화면을 남기는 방법(C안, 2026-11-08 결정):** 배포 보호는 그대로 둔다. **1차 화면은 시연 영상·캡처·v1.0 태그로 남긴다.** 시연 영상 링크는 README, 캡처는 `docs/design/screens/`에 있다.

## 요약

(Task 8에서 작성: 도구 6개 × 핵심 숫자 1~2개, 비용 장부 합계)

## Lighthouse (화면 속도)

- **환경:** 2026-11-08 05:25 UTC, 대상 `https://pyeobom.vercel.app/`(운영 첫 화면), 실행 위치 로컬(Windows, 헤드리스 Chrome 156), Lighthouse 13.6.0
- **방법:** `bash measure/run_lighthouse.sh` — 모바일 기본 설정(`formFactor: mobile`, 느린 네트워크·CPU 4배 감속 흉내 `simulate`)으로 3회 실행하고 `measure/lighthouse.py`의 `summarize_runs`로 중앙값을 낸다. 보고서 원본은 `measure/out/`(저장소에 넣지 않음)
  - 질문으로 서버를 미리 깨우지 않았다. 첫 화면은 CDN이 주는 정적 파일이라 함수 대기(쉬었다가 첫 질문 약 7.7초)와 상관이 없다.
- **결과 (중앙값, 3회):**

| 성능 점수 | LCP | CLS | TBT | FCP |
|---|---|---|---|---|
| **0.99** | 762ms | 0.080 | 0ms | 762ms |

| 회차 | 성능 | LCP | CLS | TBT | FCP |
|---|---|---|---|---|---|
| 1 | 0.98 | 1,238ms | 0.080 | 0ms | 1,238ms |
| 2 | 0.99 | 762ms | 0.080 | 0ms | 762ms |
| 3 | 0.99 | 755ms | 0.080 | 12ms | 755ms |

- **해석:**
  - 1차 첫 화면은 HTML과 같은 주소의 `styles.css`·`app.js`만 불러온다(웹 글꼴·이미지·외부 스크립트 없음). 그래서 빠르다.
  - 1회차만 LCP가 느렸다(원인은 확인하지 않음). 이렇게 한 번씩 튀는 값 때문에 중앙값을 쓴다.
  - CLS 0.080은 모두 아래쪽 안내 문구(`body > footer.footer`)가 움직인 값이다(Lighthouse `layout-shifts` 항목). 원인은 조사하지 않고 **계획 3에서 확인**한다.
  - 개편 후 비교할 점: Pretendard 글꼴과 일러스트가 들어가면 LCP·CLS가 나빠질 수 있다(설계 11절 위험).

## axe-core (접근성)

- **환경:** 2026-11-08, 대상 `https://pyeobom.vercel.app`(운영), 실행 위치 로컬(Windows, 설치된 Chrome, 폭 360×740), axe-core 4.14.0, Playwright(Python) 1.64.1
- **방법:** `.venv/Scripts/python -m measure.a11y` (먼저 `measure/`에서 `npm install`)
  - `/api/models`는 실제 API, `/api/ask`는 Playwright로 가로채 고정 응답(`measure/fixtures/`, 근거 1개·가짜 인용)을 돌려준다. **AI를 부르지 않는다.**
  - 오류 상태는 504 `AI_TIMEOUT` 본문을 돌려준다. 상태마다 결과 카드가 나온 뒤 `axe.run()`을 실행했다. 원본 결과는 `measure/out/axe-<상태>.json`(저장소에 넣지 않음)
- **결과:**

| 상태 | 위반 수 | critical | serious | moderate | minor | 위반 규칙 | 확인 필요(incomplete) |
|---|---|---|---|---|---|---|---|
| 빈 화면 | **0** | 0 | 0 | 0 | 0 | — | `aria-prohibited-attr` |
| 답 | **1** | 0 | 0 | 1 | 0 | `page-has-heading-one` | `aria-prohibited-attr` |
| 찾지 못함 | **1** | 0 | 0 | 1 | 0 | `page-has-heading-one` | `aria-prohibited-attr` |
| 오류 | **1** | 0 | 0 | 1 | 0 | `page-has-heading-one` | `aria-prohibited-attr` |

- **해석:**
  - `page-has-heading-one`: 질문을 보내면 소개 영역이 접히면서 `aria-hidden="true"`가 붙는다(`public/app.js`의 `collapse`). 그래서 화면의 유일한 h1("세탁기·에어컨, 설명서 대신 물어보세요")이 보조 기술에서 사라진다. 빈 화면에서는 위반이 없다.
  - `aria-prohibited-attr`(확인 필요): 예시 질문 영역 `div#examples`에 역할(role) 없이 `aria-label`이 붙어 있다. axe가 자동으로 판정하지 못한 항목이라 위반 수에는 들어가지 않는다.
  - 두 가지 모두 이번에는 고치지 않는다(이번 계획은 측정만). **계획 3에서 수정, 개편 후 재측정.**

## Langfuse (단계별 시간·토큰·비용)

- **환경:**
- **방법:** 로컬에서만 추적을 켜고 1차 30문항 1회 실행
  - 추적 코드: `app/core/observability.py` (Langfuse Python SDK v5). `LANGFUSE_PUBLIC_KEY`·`LANGFUSE_SECRET_KEY`가 없으면 아무것도 하지 않는다. Vercel 환경 변수에는 넣지 않는다.
  - **보내는 것:** 단계별 시간(`ask` 안에 `embed`, `search`(그 안에 `db_connect`), `llm`), 토큰 수(`llm`의 `usage_details`), 가린 질문(`question_masked`), 모델 이름.
  - **보내지 않는 것:** 프롬프트, 설명서 조각, 인용, 답 본문. OpenAI 자동 기록(래퍼·자동 계측)은 쓰지 않고, `should_export_span=is_langfuse_span`으로 이 코드가 만든 기록만 내보낸다. 넣을 수 있는 속성도 목록으로 제한한다(`tests/core/test_observability.py`로 고정).
- **결과:**
- **해석:**

## DeepEval (AI 채점, 보조 지표)

- **환경:**
- **방법:** 답이 있는 문항만, 지표 3개(Faithfulness, Answer Relevancy, Contextual Relevancy). 사람 판정과 나란히 적음
- **결과:**
- **해석:**

## Locust (동시 요청 응답 시간, 미리보기만)

- **환경:**
- **방법:** 미리보기 주소, 동시 5명, 1분
- **결과:**
- **해석:**

## Promptfoo (방어 시험, 미리보기만)

- **환경:**
- **방법:** 고정 사례 4개 + 레드팀 생성 공격(개수 제한)
- **결과:**
- **해석:**

## 비용 장부

상한은 **합계 2달러**다(OpenAI 선불 5달러 중 일부, 나머지는 운영용). AI 측정마다 실행 전에 예상 비용을 적고 `measure/budget.py`의 `check_budget`으로 누적이 상한 이하인지 확인한 뒤 실행한다. 실제 비용은 실행 뒤에 적는다.

| 항목 | 예상 비용 (USD) | 실제 비용 (USD) | 누적 예상 (USD) | 확인 |
|---|---|---|---|---|
| axe 첫 실행(가로채기 함수 오류, 2026-11-08) | — | 확인하지 못함, 최대 1센트 미만 | 0.01 | 사후 기록. 가로채기 안에서 오류가 나 `/api/ask`가 실제 서버로 나갔는지 확인하지 못함. 나갔다면 질문 1개(약 0.035센트) |
| Task 4 미리보기 확인 질문 1개 | 0.001 | | 0.011 | `check_budget` 통과 |
| PR #24 병합 전 통합 테스트(`pytest -m integration`, 임베딩 약 15회·답변 AI 없음) | 0.001 | 0.001 미만(18 passed, 1 xfailed) | 0.012 | `check_budget` 통과 |

## 도구별 스킬 후보 (2026-11-08, 찾기만 함)

`npx skills find <검색어>`로 찾았다(skills CLI, skills.sh 목록). 설치 기준은 공식 출처이거나 설치 수 1천 이상이고, SKILL.md를 읽은 뒤 사용자 확인을 받아 설치한다. **아직 아무것도 설치하지 않았다.**

| 도구 | 기준을 만족하는 후보 (출처, 설치 수) | 기준 미달 상위 후보 |
|---|---|---|
| Lighthouse | 없음 | `jeremylongshore/tons-of-skills-marketplace@performance-lighthouse-runner` (598), `onnokh/lighthouse@lighthouse` (517) |
| axe-core + Playwright | `currents-dev/playwright-best-practices-skill@playwright-best-practices` (비공식, 103.6K, Playwright 일반) | `pedronauck/skills@a11y-testing` (355), `enderpuentes/ai-agent-skills@axe-playwright` (2) |
| Langfuse | `langfuse/skills@langfuse` (공식, 20.8K) | `langfuse/skills@langfuse-observability` (공식, 213) |
| DeepEval | `confident-ai/deepeval@deepeval` (공식, 2.9K) | `confident-ai/deepeval@deepeval-tracing` (공식, 89) |
| Locust | 없음 | `jeremylongshore/tons-of-skills-marketplace@locust-test-creator` (60) |
| Promptfoo | `promptfoo/promptfoo@promptfoo-evals` (공식, 385), `@promptfoo-redteam-setup` (공식, 87), `@promptfoo-redteam-run` (공식, 84), `daymade/claude-code-skills@promptfoo-evaluation` (비공식, 1.6K) | — |

## 스킬 검토 결과 (2026-11-08)

위 후보 중 공식 출처 5개의 SKILL.md(와 딸린 참고 문서)를 읽고, CLAUDE.md 규칙(비밀 값 출력 금지, 확인 없는 외부 전송·패키지 설치 금지 등)과 부딪치는지 확인했다. 설치는 Claude Code 사용자 폴더(`~/.claude/skills`)에만 했고 저장소에는 넣지 않았다.

| 스킬 | 결정 | 이유 |
|---|---|---|
| `promptfoo/promptfoo@promptfoo-evals` | **설치** | 결과 공유를 기본으로 끄고(`--no-share`), 키는 `{{env.VAR}}`로만 쓰며, 키가 있고 안전할 때만 실행하라고 한다 |
| `langfuse/skills@langfuse` | 보류 | **확인 없는 외부 명령 허용**: 스킬이 켜지면 `npx langfuse-cli …`(npm 패키지를 받아 실행)와 `curl *langfuse.com/*`를 권한 확인 없이 허용한다. Langfuse가 없어도 모든 AI 작업에 쓰라고 해서 프롬프트 작업에도 끼어든다 |
| `confident-ai/deepeval@deepeval` | 보류 | **프롬프트 자동 수정·재평가**: 횟수를 정하지 않으면 기본 5회 반복하며 앱 코드(프롬프트·검색)를 고치고 평가를 다시 돌린다. AI 비용이 들고 "측정만" 하는 이번 계획과 맞지 않는다 |
| `promptfoo/promptfoo@promptfoo-redteam-setup`, `@promptfoo-redteam-run` | 보류 | **공격 생성을 외부 서버로 보냄**: 공격 생성·채점에 `--remote`(Promptfoo 서버)를 쓰라고 한다. 로컬에 OpenAI 키가 있어도 같아서 앱 설명·설정이 밖으로 나간다 |

- 그래서 Langfuse·DeepEval은 각 도구의 공식 문서만 보고 계획대로 진행한다. Promptfoo 레드팀은 `--remote` 없이 우리 OpenAI 키로 로컬 생성만 쓰고, 로컬 생성이 안 되는 플러그인은 빼서 Promptfoo 절에 목록으로 적는다.

## 한계

- **자동 접근성 검사는 일부만 잡는다.** axe-core는 규칙으로 판정할 수 있는 것만 찾는다. 키보드만으로 조작, 화면 낭독기로 읽는 순서, 실기기 동작은 사람이 확인해야 한다.
- 측정마다 날짜, 대상 주소, 실행 위치(로컬/미리보기), 도구 버전을 각 절의 "환경"에 적는다.
- DeepEval·Promptfoo 점수는 보조 지표다. 정답률의 최종 기준은 1차 사람 판정(`docs/평가/2026-11-01-v2a.md`)이다.
