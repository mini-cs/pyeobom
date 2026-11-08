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
  - CLS 0.080은 모두 아래쪽 안내 문구(`body > footer.footer`)가 움직인 값이다(Lighthouse `layout-shifts` 항목). 원인은 이번에 따로 조사하지 않았다.
  - 개편 후 비교할 점: Pretendard 글꼴과 일러스트가 들어가면 LCP·CLS가 나빠질 수 있다(설계 11절 위험).

## axe-core (접근성)

- **환경:**
- **방법:** 1차 화면 상태 4개(빈 화면, 답, 찾지 못함, 오류). `/api/ask`는 고정 응답으로 가로채 AI를 부르지 않음
- **결과:**
- **해석:**

## Langfuse (단계별 시간·토큰·비용)

- **환경:**
- **방법:** 로컬에서만 추적을 켜고 1차 30문항 1회 실행
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
| (아직 없음) | | | 0 | |

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

## 한계

- 측정마다 날짜, 대상 주소, 실행 위치(로컬/미리보기), 도구 버전을 각 절의 "환경"에 적는다.
- DeepEval·Promptfoo 점수는 보조 지표다. 정답률의 최종 기준은 1차 사람 판정(`docs/평가/2026-11-01-v2a.md`)이다.
