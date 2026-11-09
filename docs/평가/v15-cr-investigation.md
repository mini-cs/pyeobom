# 근거 관련성 0.297 원인 조사 (v1.5 이어지는 질문)

> 계획: `docs/superpowers/plans/2026-11-09-cr-investigation.md` · 근거: `docs/평가/v15-server.md`, 결정기록 028
> **조사만 한다. 코드·프롬프트·설정은 고치지 않는다.** 가설별 판단 기준은 계획 문서 표 그대로 쓴다.

## Task 1: 이미 있는 자료 + 근거 관련성 다시 채점 (H1, H5)

### DeepEval 기록 형식 (Step 1)

- 계획 2에서 저장한 DeepEval 기록(`measure/out/deepeval-v15-fu-ctx-*.json`)에는 **점수와 이유 문장만** 있고 조각별 판정이 없었다(계획 작성 시 잘못 가정, 채팅 Claude → 사용자 결정으로 다시 채점).
- DeepEval 4.3.3의 근거 관련성 판정은 **문장 단위**다: 조각(`retrieval_context`)마다 여러 문장(statement)을 뽑아 yes/no를 매기고, 점수는 전체 문장 중 yes의 비율이다.
- 이 조사의 규칙: **조각 안에 관련(yes) 문장이 하나라도 있으면 그 조각을 "관련 있음"으로 본다**(`count_relevant_chunks`).

### 근거 관련성 다시 채점 (사용자 결정)

- 같은 답·같은 조각(`v15-fu-ctx`, TOP_K=5, `.settings.json` 차이 없음)에 `ContextualRelevancyMetric`만 다시 돌려 조각별 문장 판정을 저장(`measure/out/`, 저장소 밖). 설정은 기준값과 같음: DeepEval 4.3.3, `gpt-5-nano`, 추론 강도 기본값
- 26문항 중 **25문항 채점**: 실행 중 비용이 상한(남은 0.304달러)을 넘어 멈춤(사용자 지시: 그때까지 채점한 범위로만 판정). **미채점 1문항: d13-1(1번째 턴)**
- 비용: 1문항 시험 0.0117 + 24문항 0.3153 = 0.327달러

| 대상 | 기존(계획 2) | 새로 채점 | 같은 턴의 기존 평균 |
|---|---|---|---|
| 이어지는 턴 | 0.297 (13턴) | **0.289** (13턴) | 0.297 |
| 1번째 턴 | 0.516 (13턴) | **0.502** (12턴, d13-1 미채점) | 0.483 |

### 턴별 표 (Step 6)

- 적중: 기대 근거가 인용 또는 검색 상위 5개에 있음(`hit_rate`). 새 세트 결과 CSV에는 검색 순위 열이 없어, 저장된 조각 본문을 DB 조각과 맞춰(조회만) 근거 표기를 복원했다(복원 실패 0).
- 관련 조각 수·근거 관련성은 DeepEval이 채점한 턴만(찾지 못함·함정·d13-1은 "-").

| 턴 | 유형 | 기대 근거 | 인용 | 검색 상위 5개 | 적중 | 관련 조각 수 | 근거 관련성(새) |
|---|---|---|---|---|---|---|---|
| d01-1 | base | manual:42·manual:43 | manual:42·manual:42·guide:guide-lg-drum-errors | manual:42·guide:guide-lg-drum-errors·manual:6·guide:guide-lg-drum-errors·manual:40 | O | 4 | 0.92 |
| d01-2 | pronoun | manual:42 | manual:42 | manual:42·manual:40·manual:20·manual:6·manual:42 | O | 1 | 0.08 |
| d01-3 | ellipsis | manual:43 | manual:43 | manual:43·manual:42·manual:6·manual:40·manual:26 | O | 4 | 0.56 |
| d02-1 | base | manual:34 | manual:34·manual:33 | manual:17·manual:34·manual:17·manual:32·manual:33 | O | 4 | 0.25 |
| d02-2 | ellipsis | manual:34 | manual:34·manual:34 | manual:17·manual:58·manual:17·manual:43·manual:34 | O | 2 | 0.25 |
| d02-3 | ellipsis | manual:34 | manual:34·manual:34 | manual:34·manual:36·manual:37·manual:37·manual:34 | O | 1 | 0.14 |
| d03-1 | base | manual:41·guide:guide-lg-drum-errors | guide:guide-lg-drum-errors·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | guide:guide-lg-drum-errors·manual:6·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | O | 4 | 0.54 |
| d03-2 | pronoun | manual:41 | guide:guide-lg-drum-errors | guide:guide-lg-drum-errors·manual:6·guide:guide-lg-drum-errors·manual:42·guide:guide-lg-drum-errors | X | 3 | 0.46 |
| d04-1 | base | manual:37·manual:36 | manual:37·manual:37 | manual:37·guide:guide-lg-drum-errors·manual:37·manual:36·manual:39 | O | 3 | 0.51 |
| d04-2 | topic_switch | manual:58 | manual:58·manual:58 | manual:15·manual:58·manual:6·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | O | 4 | 0.32 |
| d05-1 | base | guide:guide-lg-drum-errors | guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | guide:guide-lg-drum-errors·manual:44·manual:56·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | O | 5 | 0.47 |
| d05-2 | pii | guide:guide-lg-drum-errors | guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | manual:56·guide:guide-lg-drum-errors·manual:44·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | O | 3 | 0.36 |
| d06-1 | base | manual:38 | manual:38 | manual:38·manual:44·manual:42·manual:40·manual:37 | O | 4 | 0.70 |
| d06-2 | ellipsis | manual:38 | manual:38 | manual:38·manual:36·manual:40·manual:43·manual:42 | O | 3 | 0.11 |
| d06-3 | ellipsis | manual:38 | manual:38 | manual:38·manual:42·manual:44·manual:40·manual:35 | O | 4 | 0.54 |
| d07-1 | base | manual:56·manual:57 | manual:56·manual:56 | manual:56·manual:9·manual:54·manual:58·manual:57 | O | 5 | 0.57 |
| d07-2 | trap | - | - | manual:56·manual:57·manual:58·manual:54·manual:55 | - | - | - |
| d08-1 | base | manual:75 | manual:75·manual:75 | manual:75·manual:72·manual:73·manual:17·guide:guide-samsung-drum-hc | O | 2 | 0.33 |
| d08-2 | pronoun | manual:75 | - | manual:9·manual:7·manual:50·manual:43·manual:71 | X | - | - |
| d09-1 | base | manual:55·manual:54·guide:guide-samsung-drum-5c | manual:55·manual:55·manual:7 | manual:50·manual:7·guide:guide-samsung-drum-oc·manual:55·manual:9 | O | 5 | 0.53 |
| d09-2 | trap | - | - | - | - | - | - |
| d10-1 | base | manual:44·manual:43 | manual:44·manual:44·manual:44 | manual:13·manual:44·manual:44·manual:43·manual:8 | O | 5 | 0.92 |
| d10-2 | pronoun | manual:43 | manual:43·manual:44 | manual:44·manual:13·manual:43·manual:44·manual:8 | O | 2 | 0.40 |
| d10-3 | ellipsis | manual:44 | manual:14 | manual:14·manual:57·manual:50·manual:51·manual:41 | X | 2 | 0.04 |
| d11-1 | base | manual:18 | manual:18 | manual:18·manual:51·manual:50·manual:7·manual:33 | O | 3 | 0.20 |
| d11-2 | topic_switch | manual:47 | manual:47·manual:47 | manual:47·manual:47·manual:25·manual:51·guide:guide-lg-aircon-ch-errors | O | 2 | 0.39 |
| d12-1 | base | manual:42 | manual:51 | manual:13·manual:25·manual:51·manual:51·manual:25 | X | 1 | 0.08 |
| d12-2 | trap | - | - | manual:42·manual:43·manual:21·manual:24·manual:13 | - | - | - |
| d12-3 | pronoun | manual:42 | manual:42 | manual:42·manual:13·manual:43·manual:21·manual:24 | O | 3 | 0.10 |
| d13-1 | base | manual:50 | manual:51·manual:51·manual:51 | manual:51·guide:guide-lg-aircon-ch-errors·manual:13·manual:31·manual:25 | X | - | - |
| d13-2 | pii | manual:5·manual:14 | - | manual:57·manual:14·manual:50·manual:51·manual:52 | O | - | - |

| 구분 | 턴 | 관련 조각 수 채점 턴 | 관련 조각 수 중앙값 | 평균 | 근거 관련성 평균(새) | 근거 적중률 |
|---|---|---|---|---|---|---|
| 1번째 턴 | 13 | 12 | **4** | 3.75 | 0.502 | 84.6% (11/13) |
| 이어지는 턴 | 18 | 13 | **3** | 2.62 | 0.289 | 80.0% (12/15, 함정 3개는 기대 근거 없음) |

### 판정 (기준은 계획 문서 그대로)

| 가설 | 기준 | 결과 | 판정 |
|---|---|---|---|
| H1 좁은 질문 | 이어지는 턴 관련 조각 수 중앙값 ≤ 1이고 1번째 턴 중앙값보다 작음 | 중앙값 3(1번째 턴 4) | **지지 안 됨** |
| H5 검색 실패 | 이어지는 턴 근거 적중률이 1번째 턴보다 10%p 이상 낮음 | 80.0% vs 84.6%(4.6%p 낮음) | **지지 안 됨** |

- 사실만 적음: 이어지는 턴은 관련 조각 수 중앙값이 3인데 근거 관련성은 0.289다. 점수가 문장 단위라 관련 조각 안의 무관한 문장도 분모에 들어간다. 원인은 Task 2·3에서 계속 본다.
