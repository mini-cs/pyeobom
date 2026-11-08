# 평가 리포트 baseline-langfuse (2026-11-08)

- 실행: `python -m evaluation --label baseline-langfuse --prompt v1 --search vector`
- 문항: `evaluation/questions.csv` 30개 (2026-10-28 고정)

## 요약

| 정답률 | 근거 적중률 | 환각률 | 오류율 | 응답 시간 평균 | 최대 | 실패: 검색 | 실패: 답변 |
|---|---|---|---|---|---|---|---|
| 72.0% | 80.0% | 0.0% | 0.0% | 4886ms | 8043ms | 3 | 4 |

- 정답률·근거 적중률은 답 있는 문항, 환각률은 함정 문항, 오류율은 전체가 분모다.

## 문항별

| id | 유형 | 기대 | 결과 | 정답 | 근거 적중 | 환각 | 실패 | 기대 근거 | 실제 인용 | ms |
|---|---|---|---|---|---|---|---|---|---|---|
| q01 | usage | true | O | O | O |  |  | manual:42|manual:43 | manual:42|guide:guide-lg-drum-errors|manual:42 | 7026 |
| q02 | usage | true | O | O | O |  |  | manual:34 | manual:34|manual:34 | 4708 |
| q03 | usage | true | O | O | O |  |  | manual:16|manual:15 | manual:16 | 6110 |
| q04 | usage | true | O | O | O |  |  | manual:37|manual:36 | manual:37|manual:37 | 4652 |
| q05 | error_code | true | O | X | O |  | answer | manual:41|guide:guide-lg-drum-errors | guide:guide-lg-drum-errors|guide:guide-lg-drum-errors|guide:guide-lg-drum-errors | 5503 |
| q06 | error_code | true | O | X | O |  | answer | guide:guide-lg-drum-errors | guide:guide-lg-drum-errors|guide:guide-lg-drum-errors | 4926 |
| q07 | error_code | true | O | O | O |  |  | guide:guide-lg-drum-errors | guide:guide-lg-drum-errors|guide:guide-lg-drum-errors | 4678 |
| q08 | colloquial | true | O | X | O |  | answer | manual:58 | manual:58|manual:58 | 4728 |
| q09 | trap_none | false | X |  |  | X |  |  |  | 3847 |
| q10 | usage | true | O | O | O |  |  | manual:45 | manual:45 | 4133 |
| q11 | usage | true | O | O | O |  |  | manual:56|manual:57 | manual:56|manual:56|manual:56 | 8043 |
| q12 | usage | true | X | X | X |  | retrieval | manual:26 |  | 3592 |
| q13 | usage | true | O | O | O |  |  | manual:38 | manual:38 | 4322 |
| q14 | error_code | true | O | O | O |  |  | manual:55|manual:54|guide:guide-samsung-drum-5c | manual:55|manual:55|manual:50 | 4954 |
| q15 | error_code | true | O | O | O |  |  | guide:guide-samsung-drum-4c | guide:guide-samsung-drum-4c|manual:71|guide:guide-samsung-drum-4c | 5222 |
| q16 | error_code | true | X | X | X |  | answer | guide:guide-samsung-drum-hc |  | 7051 |
| q17 | colloquial | true | O | O | O |  |  | manual:75 | manual:75|manual:75|manual:75 | 5209 |
| q18 | trap_other_model | false | X |  |  | X |  |  |  | 3380 |
| q19 | usage | true | O | O | O |  |  | manual:44|manual:43 | manual:44|manual:44|manual:44 | 5631 |
| q20 | usage | true | X | X | X |  | retrieval | manual:26 |  | 3403 |
| q21 | usage | true | O | O | O |  |  | manual:18 | manual:18 | 4647 |
| q22 | usage | true | O | O | X |  |  | manual:42 | manual:51 | 4169 |
| q23 | error_code | true | O | O | O |  |  | guide:guide-lg-aircon-ch-errors | guide:guide-lg-aircon-ch-errors|guide:guide-lg-aircon-ch-errors | 4814 |
| q24 | error_code | true | O | O | O |  |  | manual:49|manual:34 | manual:34|manual:49 | 6368 |
| q25 | colloquial | true | O | X | X |  | retrieval | manual:50 | manual:51|manual:51 | 5081 |
| q26 | colloquial | true | O | O | O |  |  | manual:51 | manual:51|manual:51 | 4450 |
| q27 | colloquial | true | O | O | O |  |  | manual:47 | manual:47|manual:47 | 4923 |
| q28 | trap_none | false | X |  |  | X |  |  |  | 3532 |
| q29 | trap_none | false | X |  |  | X |  |  |  | 3984 |
| q30 | trap_other_model | false | X |  |  | X |  |  |  | 3481 |
