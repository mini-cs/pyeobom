# 근거 관련성 0.297 원인 조사 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이어지는 질문(질문 바꾸기 후)의 DeepEval 근거 관련성(Contextual Relevancy)이 0.297로 낮은 원인을 가설 5개로 나눠 확인한다. **이번 작업은 조사만 한다. 코드·프롬프트·설정은 고치지 않는다.**

**Architecture:** 이미 있는 결과(v1.5 TOP_K=5 실행의 결과 CSV, DeepEval 판정 기록)를 먼저 읽고(비용 0), 그다음 답변 AI 없이 **검색만** 다시 돌려 질문 형태별로 정답 조각 순위를 비교한다(임베딩 비용만). 마지막으로 사람이 조각 관련성을 직접 매겨 DeepEval 채점과 비교한다.

**Tech Stack:** Python, 기존 `app/retrieval/`(검색), `evaluation/`, `measure/`, pytest

**근거:** `docs/평가/v15-server.md`(이어지는 턴 CR 0.297, 30문항 0.501, 1번째 턴 0.516), 결정기록 028

> **정정(2026-11-09):** 계획 작성 시 DeepEval 기록에 조각별 판정이 있다고 잘못 가정함(채팅 Claude) → 다시 채점으로 해결. 계획 2에서 저장한 기록에는 점수와 이유 문장만 있었다. 사용자 결정으로 같은 답·같은 조각(v15-fu-ctx, 26턴)에 `ContextualRelevancyMetric`만 기준값과 같은 설정(DeepEval 4.3.3, `gpt-5-nano`, 추론 강도 기본값)으로 다시 돌려 조각별(문장별) 판정을 저장하고, H1·H4 판정에 쓴다. 새 평균은 0.297과 나란히 기록한다. 예산은 계획 3 몫에서 0.2달러를 옮겨 계획 2 장부 상한을 1.7달러로.

## Global Constraints

- **고치지 않는다.** 조사 결과는 리포트에 적고, 개선은 2차 후보로만 올린다.
- **가설별 판단 기준은 이 문서에 미리 적힌 그대로 쓴다.** 결과를 본 뒤 기준을 바꾸지 않는다.
- 답변 AI를 다시 부르지 않는다. DeepEval은 위 정정대로 근거 관련성만 한 번 다시 채점한다. AI 비용은 임베딩뿐(예상 1센트 미만). 장부는 `docs/평가/v15-server.md`의 계획 2 장부를 이어 쓰고 `check_budget`(상한 1.5달러 → 정정: 실행 때 상한은 1.8달러, 위 정정과 `v15-server.md` 장부 참고)을 통과한 뒤 실행한다.
- 실행 설정은 운영 기본값(TOP_K=5, vector, v2a 진단 규칙). 실행 전에 `.settings.json` 경고가 없는지 확인한다.
- 설명서 조각 본문이 들어간 파일은 `measure/out/`(저장소 밖)에만 둔다. 리포트에는 조각 번호·쪽·짧은 요약만.
- 사람이 쓴 질문(Task 2의 ②)은 **검색 결과를 보기 전에** 확정한다.
- 원인을 하나로 단정하지 않는다. 기준을 넘은 가설만 "지지됨"으로, 나머지는 "지지 안 됨" 또는 "판단 불가"로 적는다.

## 가설과 판단 기준 (실행 전에 확정)

| 가설 | 내용 | "지지됨" 기준 |
| --- | --- | --- |
| H1 좁은 질문 | 이어지는 질문은 좁게 물어 맞는 조각이 1개뿐이고 나머지는 원래 관련이 적다 | 이어지는 턴의 **관련 조각 수 중앙값이 1 이하**이고, 1번째 턴 중앙값보다 작다 |
| H2 덧붙은 말 | 바꾼 질문에 앞 대화 내용이 덧붙어 엉뚱한 조각이 끌려온다 | Task 2에서 ②(사람이 쓴 짧은 질문)가 ①(바꾼 질문)보다 **정답 조각 순위가 좋아진 턴이 4개 이상**, 나빠진 턴이 1개 이하 |
| H3 용어 바꿈 | 사용자 말("거름망")을 다른 용어("배수 필터")로 바꿔 설명서 용어와 어긋난다 | ①에서 사용자 용어가 다른 말로 바뀐 턴들 중 **절반 이상**에서 ②의 정답 조각 순위가 더 좋다 |
| H4 채점 쪽 문제 | DeepEval이 짧은 질문의 조각 관련성을 박하게 채점한다 | Task 3에서 사람과 DeepEval의 조각별 일치율이 **70% 미만**이거나, DeepEval이 "관련 없음"으로 본 조각을 사람이 "관련 있음"으로 본 경우가 그 반대보다 **2배 이상** |
| H5 검색 실패 | 정답 조각이 아예 5개 안에 없다 | 이어지는 턴의 **근거 적중률이 1번째 턴보다 10%p 이상 낮다** |

---

### Task 1: 이미 있는 자료로 확인 (H1, H5) — 비용 0

**Files:**
- Create: `measure/cr_investigation.py`(집계 함수), `docs/평가/v15-cr-investigation.md`
- Test: `tests/measure/test_cr_investigation.py`

**Interfaces:**
- Produces: `count_relevant_chunks(deepeval_record: dict) -> int` — DeepEval 근거 관련성 기록에서 조각마다 관련 여부를 정해 관련 조각 수를 돌려준다. DeepEval 4.3.3의 기록이 **문장 단위 판정**이면, 조각 안에 관련 문장이 하나라도 있으면 그 조각을 "관련 있음"으로 본다(이 규칙을 리포트에 명시)
- Produces: `hit_rate(rows: list[dict]) -> float` — 기대 근거가 인용 또는 검색 상위 5개에 있는 비율

- [ ] **Step 1:** DeepEval 기록(`measure/out/`)의 실제 형식을 확인하고, 문장 단위인지 조각 단위인지 리포트에 적는다
- [ ] **Step 2: Write the failing tests** — 가짜 기록(조각 3개 중 1개에만 관련 문장)으로 `count_relevant_chunks == 1`, 관련 문장이 없는 기록은 0 / `hit_rate`는 기대 근거가 5개 안에 있는 행만 센다
- [ ] **Step 3: Run** → FAIL
- [ ] **Step 4:** 구현
- [ ] **Step 5: Run** → PASS
- [ ] **Step 6:** v1.5 TOP_K=5 실행의 새 세트에서 턴별 관련 조각 수와 근거 적중 여부를 표로 만든다. 1번째 턴(13) / 이어지는 턴(18)으로 나눠 중앙값·평균·적중률을 적고, **H1·H5 판정**을 기준대로 적는다
- [ ] **Step 7: Commit** → PR → 병합 직전 멈춤

---

### Task 2: 검색만 다시 돌려 질문 형태 비교 (H2, H3) — 임베딩 비용만

**Files:**
- Create: `measure/cr_queries.csv`(②의 사람 질문), `measure/retrieval_probe.py`
- Test: `tests/measure/test_retrieval_probe.py`

**Interfaces:**
- Consumes: `app/retrieval/`의 검색 함수(운영과 같은 모델 필터·진단 규칙)
- Produces: `expected_rank(results: list, expected_refs: list[str], depth: int = 20) -> int | None` — 정답 조각이 상위 몇 위인지(20위 밖이면 None)

**비교할 질문 세 가지 (이어지는 턴 18개마다)**
- ① 실제로 바꾼 질문 (v1.5 TOP_K=5 실행 결과의 `rewritten_question`)
- ② 사람이 쓴 짧은 질문: **사용자가 쓴 말**을 그대로 살리고, 앞 대화에서 가리키는 대상만 최소한으로 보충한 한 문장. 설명서 용어로 바꾸지 않는다 (예: d03-2 사용자 "그 거름망은 어디에 있어요?" → ② "OE가 뜰 때 청소하는 거름망은 어디에 있어요?")
- ③ 원래 질문 (바꾸기 없이 사용자가 친 문장 그대로)

- [ ] **Step 1:** Claude Code가 ② 초안 18개를 `measure/cr_queries.csv`에 쓰고 **검색은 아직 하지 않는다**. 규칙: 사용자가 쓴 핵심 단어를 바꾸지 않음, 앞 대화에서 대상만 보충, 15단어 이내
- [ ] **Step 2: 사용자 확인** — ② 18개를 사용자가 확정한다(검색 결과를 보기 전). 확정 날짜를 파일 첫 줄에
- [ ] **Step 3: Write the failing tests** — `expected_rank`: 정답이 3위면 3, 20위 밖이면 None, 기대 근거가 여러 개면 가장 높은 순위
- [ ] **Step 4: Run** → FAIL → 구현 → PASS
- [ ] **Step 5:** 장부에 예상 비용(18턴 × 3질문 임베딩, 1센트 미만) 기록 → `check_budget` → 검색만 실행(상위 20개)
- [ ] **Step 6:** 턴별로 ①·②·③의 정답 조각 순위와 상위 5개 조각 번호를 표로. ①에서 사용자 용어가 바뀐 턴을 표시. **H2·H3 판정**을 기준대로 적는다
- [ ] **Step 7: Commit** → PR → 병합 직전 멈춤

---

### Task 3: 사람이 조각 관련성 매기기 (H4) — 비용 0

**Files:**
- Create: `measure/out/cr_human_labels.csv`(저장소 밖, 조각 본문 포함), `docs/평가/v15-cr-investigation.md`에 결과만

- [ ] **Step 1:** 이어지는 턴 중 10턴을 고른다. 고르는 규칙: 유형별로 고르게(가리키는 말·생략·주제 바꾸기·함정·개인정보), 턴 번호 순으로 앞에서부터. **DeepEval 점수를 보고 고르지 않는다**
- [ ] **Step 2:** 10턴 × 조각 5개 = 50개 조각을 "질문, 조각 본문(로컬 파일), 관련 있음/없음 칸" 형식으로 준비한다. **DeepEval 판정은 보이지 않게** 한다
- [ ] **Step 3: 사용자 확인** — 사용자가 50개 조각에 관련 있음/없음을 매긴다. 기준: "이 조각이 질문에 답하는 데 필요한 내용을 담고 있나"
- [ ] **Step 4:** 사람 판정과 DeepEval 판정을 조각별로 맞춰 일치율과 어긋남 방향(사람 O·DeepEval X / 사람 X·DeepEval O)을 표로. **H4 판정**을 기준대로 적는다
- [ ] **Step 5:** 리포트 마감: 가설 5개의 판정 표, 지지된 가설에 맞는 2차 후보(예: H2·H3 → 바꾸기 규칙 강화, H1 → 조각 수 줄이기·재순위 시험, H4 → 이 서비스에서 근거 관련성은 참고 지표로만), 판단 불가 항목과 이유
- [ ] **Step 6:** 결정기록 028에 한 줄 추가: "근거 관련성 0.297 원인 조사 결과: (지지된 가설 요약). 자세한 내용은 v15-cr-investigation.md"
- [ ] **Step 7: Commit** → PR → 병합 직전 멈춤
