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

- 다시 채점해도 0.297→0.289, 0.516→0.502로 거의 같음 → DeepEval 근거 관련성 채점은 반복해도 안정적. 단, 사람과 판단이 같은지(H4)는 Task 3에서 확인.
- H1이 지지되지 않음(관련 조각 중앙값 3) → 관련 조각은 들어오지만, 그 안에 질문과 무관한 문장 비율이 높아 점수가 낮음. 원인은 H2·H3·H4로 이어서 확인.
- 사실만 적음: 이어지는 턴은 관련 조각 수 중앙값이 3인데 근거 관련성은 0.289다. 점수가 문장 단위라 관련 조각 안의 무관한 문장도 분모에 들어간다. 원인은 Task 2·3에서 계속 본다.

## Task 2: 검색만 다시 돌려 질문 형태 비교 (H2, H3)

- 질문: `measure/cr_queries.csv`(2026-11-09 사용자 확정). ① 실제로 바꾼 질문(`v15-fu-ctx`), ② 사람이 쓴 짧은 질문(사용자 말 유지, 대상만 보충), ③ 원래 질문. d02-2·d02-3의 ②는 보충할 대상이 없어 ③과 같음
- 방법: ①②③ 모두 운영과 같은 개인정보 가리기 → 임베딩 → 모델 필터 벡터 검색 상위 20개(`python -m measure.retrieval_probe`, 설정 차이 없음, 답변 AI 없음). 순위는 기대 근거가 처음 나오는 위치(20위 밖은 "20위 밖", 어떤 순위보다 나쁨)
- 집계 제외: d09-2(운영에서는 다른 브랜드 규칙으로 검색 전에 막힘) → H2 분모 17. 함정(d07-2·d12-2)은 기대 근거가 없어 "같음"으로 셈

| 턴 | 유형 | 기대 근거 | ① 바꾼 질문 순위 | ② 사람 질문 순위 | ③ 원래 질문 순위 | ② vs ① | 용어 교체(H3) | ① 상위 5개 | ② 상위 5개 |
|---|---|---|---|---|---|---|---|---|---|
| d01-2 | pronoun | manual:42 | 1 | 1 | 7 | 같음 |  | manual:42·manual:40·manual:20·manual:6·manual:42 | manual:42·manual:40·manual:20·manual:6·manual:42 |
| d01-3 | ellipsis | manual:43 | 1 | 1 | 6 | 같음 |  | manual:43·manual:42·manual:6·manual:40·manual:26 | manual:43·manual:26·manual:42·manual:6·manual:6 |
| d02-2 | ellipsis | manual:34 | 5 | 10 | 10 | ② 나쁨 |  | manual:17·manual:58·manual:17·manual:43·manual:34 | manual:58·manual:8·guide:guide-lg-drum-errors·manual:52·manual:24 |
| d02-3 | ellipsis | manual:34 | 1 | 1 | 1 | 같음 |  | manual:34·manual:36·manual:37·manual:37·manual:34 | manual:34·manual:36·manual:37·manual:37·manual:34 |
| d03-2 | pronoun | manual:41 | 6 | 1 | 1 | ② 좋음 | 거름망 → 배수 필터 | guide:guide-lg-drum-errors·manual:6·guide:guide-lg-drum-errors·manual:42·guide:guide-lg-drum-errors | manual:41·manual:23·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors·manual:42 |
| d04-2 | topic_switch | manual:58 | 2 | 2 | 2 | 같음 |  | manual:15·manual:58·manual:6·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | manual:15·manual:58·manual:6·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors |
| d05-2 | pii | guide:guide-lg-drum-errors | 2 | 1 | 1 | ② 좋음 |  | manual:56·guide:guide-lg-drum-errors·manual:44·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors | guide:guide-lg-drum-errors·manual:56·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors·guide:guide-lg-drum-errors |
| d06-2 | ellipsis | manual:38 | 1 | 1 | 9 | 같음 |  | manual:38·manual:36·manual:40·manual:43·manual:42 | manual:38·manual:44·manual:77·manual:36·manual:40 |
| d06-3 | ellipsis | manual:38 | 1 | 1 | 20위 밖 | 같음 |  | manual:38·manual:42·manual:44·manual:40·manual:35 | manual:38·manual:40·guide:guide-samsung-drum-lc·manual:60·manual:57 |
| d07-2 | trap | - | - | - | - | 기대 근거 없음(함정) |  | manual:56·manual:57·manual:58·manual:54·manual:55 | manual:56·manual:58·manual:9·manual:57·manual:55 |
| d08-2 | pronoun | manual:75 | 7 | 1 | 13 | ② 좋음 |  | manual:9·manual:7·manual:50·manual:43·manual:71 | manual:75·manual:50·manual:72·manual:54·manual:70 |
| d09-2 | trap | - | - | - | - | 기대 근거 없음(함정) (집계 제외) |  | guide:guide-samsung-drum-5c·manual:18·guide:guide-samsung-drum-4c·manual:48·guide:guide-samsung-drum-lc | guide:guide-samsung-drum-5c·manual:18·guide:guide-samsung-drum-4c·manual:48·manual:23 |
| d10-2 | pronoun | manual:43 | 3 | 4 | 20위 밖 | ② 나쁨 |  | manual:44·manual:13·manual:43·manual:44·manual:8 | manual:44·manual:13·manual:44·manual:43·manual:8 |
| d10-3 | ellipsis | manual:44 | 20위 밖 | 2 | 20위 밖 | ② 좋음 |  | manual:14·manual:57·manual:50·manual:51·manual:41 | manual:13·manual:44·manual:1·manual:44·manual:43 |
| d11-2 | topic_switch | manual:47 | 1 | 1 | 1 | 같음 |  | manual:47·manual:47·manual:25·manual:51·guide:guide-lg-aircon-ch-errors | manual:47·manual:47·manual:25·manual:51·guide:guide-lg-aircon-ch-errors |
| d12-2 | trap | - | - | - | - | 기대 근거 없음(함정) | 안쪽 습기를 말리는 기능 → AI 건조 기능 | manual:42·manual:43·manual:21·manual:24·manual:13 | manual:15·manual:46·manual:50·manual:51·manual:45 |
| d12-3 | pronoun | manual:42 | 1 | 20 | 14 | ② 나쁨 | 안쪽 습기를 말리는 기능 → AI 건조 기능 | manual:42·manual:13·manual:43·manual:21·manual:24 | manual:51·manual:21·manual:41·manual:20·manual:2 |
| d13-2 | pii | manual:5·manual:14 | 2 | 4 | 2 | ② 나쁨 |  | manual:57·manual:14·manual:50·manual:51·manual:52 | manual:1·manual:13·manual:57·manual:14·manual:50 |

| 비교 (17턴) | ② 좋음 | ② 나쁨 | 같음 |
|---|---|---|---|
| ②(사람 질문) vs ①(바꾼 질문) | 4 (d03-2, d05-2, d08-2, d10-3) | 4 (d02-2, d10-2, d12-3, d13-2) | 9 |

### 판정 (기준은 계획 문서 그대로)

| 가설 | 기준 | 결과 | 판정 |
|---|---|---|---|
| H2 덧붙은 말 | ②가 ①보다 순위가 좋아진 턴 4개 이상, 나빠진 턴 1개 이하 | 좋아짐 4, 나빠짐 4 | **지지 안 됨** |
| H3 용어 바꿈 | 용어가 교체된 3턴(d03-2·d12-2·d12-3) 중 2개 이상에서 ②가 더 좋음 | 1개(d03-2). d12-2는 함정이라 기대 근거가 없어 비교 불가, d12-3은 ②가 나쁨 | **지지 안 됨** |

- 용어 교체를 나눠 보면(사용자 요청):
  - **d03-2(설명서와 어긋난 용어로 교체):** 사용자 "거름망" → ① "배수 필터". ① 6위, ② 1위 — 교체가 정답 순위를 낮췄다(사람 판정 오답 d03-2와 같은 경우).
  - **d12(설명서 용어로 교체):** 사용자 "안쪽 습기를 말리는 기능" → ① "AI 건조 기능". d12-3에서 ① 1위, ② 20위 — 교체가 정답 순위를 높였다. d12-2는 함정이라 순위 비교 없음.
- **H3 해석:** d03-2(설명서와 어긋난 용어로 교체 → 순위 하락), d12-3(설명서 용어로 교체 → 20위에서 1위). 사용자 말과 설명서 용어가 다를 때, 설명서 용어로 옮기면 검색이 좋아지고 어긋난 용어면 나빠짐. 사례 2개라 결론 아님, 검색 개선 계획(표현이 다른 질문)의 가설로 넘김.

**탐색적 관찰(사전 기준 없음): ①(바꾼 질문) vs ③(원래 질문), 17턴**

| ①이 좋음 | 같음 | ①이 나쁨 |
|---|---|---|
| 8 | 7 | 2 |

## Task 3: 사람이 조각 관련성 매기기 (H4)

- 고른 10턴(DeepEval 점수를 보지 않고 계획 규칙대로): d01-2·d01-3·d04-2·d05-2·d03-2·d02-2·d11-2·d10-2·d02-3·d12-3. DeepEval이 채점한 이어지는 턴 13개 안에서 유형 순서(가리키는 말·생략·주제 바꾸기·함정·개인정보)를 돌아가며 턴 번호 순으로 고름. **함정 턴은 DeepEval 판정이 없어 0개**(진행 기록 Ruling)
- 질문: DeepEval이 채점할 때 받은 질문(①, 바꾼 질문). 조각: 같은 실행(`v15-fu-ctx`)의 검색 상위 5개
- 사람 판정: 사용자가 DeepEval 판정을 가린 파일(`measure/out/cr_human_labels.csv`, 저장소 밖)에서 50개 조각에 O/X를 매김(빈칸·? 0개). 기준: "이 조각이 질문에 답하는 데 필요한 내용을 담고 있나"
- DeepEval 쪽 조각 판정: Task 1 규칙 그대로(조각 안에 yes 문장이 하나라도 있으면 O). 판정 목록의 순서가 조각 순서와 맞는지 문장·조각 본문 겹침으로 50개 모두 확인

| 사람 \ DeepEval | DeepEval O | DeepEval X | 합 |
|---|---|---|---|
| 사람 O | 17 | **0** | 17 |
| 사람 X | **8** | 25 | 33 |
| 합 | 25 | 25 | 50 |

- 일치율 **84.0%**(42/50). 어긋남 방향: 사람 O·DeepEval X **0개**, 사람 X·DeepEval O **8개**

| 턴 | 사람 O | DeepEval O | 일치 | 사람 X·DeepEval O |
|---|---|---|---|---|
| d01-2 | 1 | 1 | 5/5 | 0 |
| d01-3 | 1 | 4 | 2/5 | 3 |
| d04-2 | 4 | 4 | 5/5 | 0 |
| d05-2 | 1 | 3 | 3/5 | 2 |
| d03-2 | 3 | 3 | 5/5 | 0 |
| d02-2 | 1 | 2 | 4/5 | 1 |
| d11-2 | 2 | 2 | 5/5 | 0 |
| d10-2 | 2 | 2 | 5/5 | 0 |
| d02-3 | 1 | 1 | 5/5 | 0 |
| d12-3 | 1 | 3 | 3/5 | 2 |

어긋난 8개(사람 X·DeepEval O). "yes 문장"은 그 조각에서 DeepEval이 yes로 본 문장 수/전체 문장 수

| 번호 | 턴 | 조각 | 근거 | yes 문장 |
|---|---|---|---|---|
| L07 | d01-3 | 2 | manual:42 | 14/14 |
| L08 | d01-3 | 3 | manual:6 | 4/15 |
| L09 | d01-3 | 4 | manual:40 | 15/15 |
| L16 | d05-2 | 1 | manual:56 | 1/18 |
| L20 | d05-2 | 5 | guide:guide-lg-drum-errors | 20/20 |
| L27 | d02-2 | 2 | manual:58 | 6/6 |
| L48 | d12-3 | 3 | manual:43 | 4/19 |
| L49 | d12-3 | 4 | manual:21 | 1/17 |

### 판정 (기준은 계획 문서 그대로)

| 가설 | 기준 | 결과 | 판정 |
|---|---|---|---|
| H4 채점 쪽 문제 | 조각별 일치율 70% 미만, 또는 사람 O·DeepEval X가 그 반대의 2배 이상 | 일치율 84.0%, 사람 O·DeepEval X 0개 vs 반대 8개 | **지지 안 됨** |

- 사실만 적음: 조각 단위로는 DeepEval이 사람보다 "관련 있음"을 더 많이 줬다(박하게 채점한 조각은 0개). 어긋난 8개 중 4개는 DeepEval이 그 조각의 문장 대부분(14/14, 15/15, 20/20, 6/6)을 yes로 봤다. 왜 그렇게 봤는지는 확인하지 못함.

## 마감 (Task 3 Step 5)

### 가설 5개 판정

| 가설 | 기준 | 결과 | 판정 |
|---|---|---|---|
| H1 좁은 질문 | 이어지는 턴 관련 조각 수 중앙값 ≤ 1이고 1번째 턴보다 작음 | 중앙값 3(1번째 턴 4) | 지지 안 됨 |
| H2 덧붙은 말 | ②가 ①보다 좋아진 턴 ≥ 4, 나빠진 턴 ≤ 1 | 좋아짐 4, 나빠짐 4 (17턴) | 지지 안 됨 |
| H3 용어 바꿈 | 용어가 교체된 턴 중 절반 이상(3개 중 2개)에서 ②가 더 좋음 | 1개(d03-2) | 지지 안 됨 |
| H4 채점 쪽 문제 | 일치율 < 70%, 또는 사람 O·DeepEval X ≥ 반대의 2배 | 84.0%, 0개 vs 8개 | 지지 안 됨 |
| H5 검색 실패 | 이어지는 턴 근거 적중률이 1번째 턴보다 10%p 이상 낮음 | 80.0% vs 84.6% | 지지 안 됨 |

- **결론: 지지된 가설이 없다. 이어지는 턴 근거 관련성 0.297(다시 채점 0.289)의 원인은 이 조사로 특정하지 못했다.**

### 2차 후보

- 계획 규칙상 지지된 가설에 맞는 2차 후보는 **없음**.
- 기준과 별개로 이미 넘긴 것(결론 아님): H3 해석(설명서 용어로 옮기면 검색이 좋아지고 어긋난 용어면 나빠짐, 사례 2개) → 검색 개선 계획(표현이 다른 질문)의 가설. d03-2 v2 규칙 준수 강화는 계획 2 때부터 개발일지 "나중에"에 있음.

### 판단 불가·범위 밖 항목과 이유

| 항목 | 이유 |
|---|---|
| 함정 턴(d07-2·d09-2·d12-2)의 H1·H4 | DeepEval이 함정·찾지 못함 턴을 채점하지 않아 조각별 판정이 없음 |
| 찾지 못함 턴(d08-2·d13-2)의 관련 조각 수(H1) | 같은 이유 |
| d13-1(1번째 턴)의 관련 조각 수(H1) | 다시 채점이 비용 상한에서 멈춰 미채점. H1의 1번째 턴 중앙값은 12턴 기준 |
| d09-2(H2) | 운영에서는 다른 브랜드 규칙으로 검색 전에 막혀 집계 제외(분모 17) |
| d12-2(H3) | 함정이라 기대 근거가 없어 순위 비교 불가. H3은 비교 가능한 2턴뿐 |
| 문장 단위 점수와 사람 판단의 차이 | H4는 계획대로 **조각 단위**로 비교했다. DeepEval 점수는 문장 단위(전체 문장 중 yes 비율)라, 관련 조각 안의 문장별 yes 비율이 사람 판단과 맞는지는 이 조사에서 보지 않았다 |
| H4 표본 | 10턴·50조각, 사람 1명. 함정·찾지 못함 유형 없음 |
