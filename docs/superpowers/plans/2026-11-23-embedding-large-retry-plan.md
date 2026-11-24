# 펴봄 v1.97 임베딩 large 다시 해 보기 — 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 11/24 안에 확인용 세트와 회귀 세트(30문항·이어지는 질문)로 임베딩 large를 운영(small)과 비교해, 시간 선을 정한 뒤 판정하고 "채택 후보" 또는 "미채택"으로 결론 낸다(운영 반영 없음).

**Architecture:** 새 측정 모듈 `measure/emb_retry.py` 하나에 4단계 열기 확인, 옛 조각 번호 → 쪽 바꾸기, 이어지는 질문 같은 실행 비교, 시간만 내는 집계, B-3 계산을 모은다. 답 만들기는 기존 `measure.stage2`(같은 실행 안 비교)를 쓴다. 판정지는 기존 `stage2 --blind`(확인용)와 `measure.v17_blind4.build_sheet`(회귀)를 쓴다.

**Tech Stack:** Python 3.14, pytest, psycopg 3, OpenAI(gpt-6-luna, text-embedding-3-small·large), Neon Postgres + pgvector

**Spec:** `docs/superpowers/specs/2026-11-23-embedding-large-retry-design.md`(승인 2026-11-23 밤, SHA-256 `8aa006d4…`)

## Global Constraints

- 모델·강도: Opus · high(CLAUDE.md). 테스트 먼저, 바로 통과하는 테스트는 돌연변이로 확인
- 브랜치: `docs/emb-retry-preview`(커밋 `1fcc9b8` 위에 이어서). PR은 마지막에 하나. push는 Task 0 끝, Task 4 끝, Task 6 끝 세 번만(push마다 Vercel 미리보기 배포가 늘어남)
- 확인용 세트를 열기 전에 4단계 코드·테스트·검토가 끝나야 한다(설계 6절 준비)
- **시간 선을 커밋하기 전에 시간 밖 결과(찾은 수·5위 안·답 글·판정지)를 보지도 보고하지도 않는다**(설계 5-2의 2, 7절 멈춤 3)
- 설명서 글·조각 글·답 글은 리포트·보고·채팅에 넣지 않는다
- 운영 DB는 읽기만. `bundle_chunks`·`chunks`·환경 변수·운영 배포를 바꾸지 않는다
- AI를 부르기 전에 장부(리포트 `docs/평가/embedding-large-retry.md`, 상한 1달러)에 행을 적고 `check_budget` 통과. 운영용 OpenAI 잔액 1달러 이상
- 결과를 보고 다시 돌리지 않는다. 오류로 멈추면 원인을 보고하고 사용자가 정한다
- 멈춤 시각: 확인용 준비를 11/24 13:00까지 시작하지 못하면 확인용 세트를 열지 않고 "미완료"(설계 7절 1). 판정이 11/24 24:00까지 끝나지 않으면 멈춤(7절 2)
- 결정기록 번호: 041(측정 전), 042(결론)

## Review Focus

1. 시간 밖 결과가 시간 선보다 먼저 새는 것: 실행 화면 출력, `stage2` 끝 요약 출력, 시간 집계에 찾은 수가 섞이는 것 → Task 1 `test_time_summary_has_no_found_or_hit_keys`, Task 3은 실행 출력을 로그 파일로 돌림
2. 열기 파일 없이, 또는 저장소 기록에 없는 커밋 해시가 적힌 열기 파일로 확인용 세트를 읽는 것 → Task 1 `test_require_open_file_*` 세 개
3. 옛 조각 번호 바꾸기에서 가이드 번호(298~335)·`manual:`·`guide:`를 건드리거나, 백업에 없는 번호를 조용히 넘기는 것 → Task 1 `test_old_chunk_refs_*`
4. 오류·규칙으로 막힌 행이 시간·비용 평균에 들어가는 것, 세트 평균의 평균으로 합치는 것 → Task 1 `test_time_summary_excludes_errors_and_blocked`, `test_time_summary_pools_all_rows_not_set_means`
5. 이어지는 질문에서 후보 대화가 운영 답을 앞 대화로 받는 것, 대화마다 방법 순서가 안 바뀌는 것 → Task 1 `test_followups_history_stays_within_method`, `test_followups_same_run_alternates_methods`

---

### Task 0: 설계·계획·측정 전 결정 커밋 (AI 비용 0)

**Files:**
- Create: `docs/superpowers/specs/2026-11-23-embedding-large-retry-design.md`(`docs/Claude outputs/`에서 복사, 해시 `8aa006d4…` 확인), `docs/superpowers/plans/2026-11-23-embedding-large-retry-plan.md`(같은 폴더에서 복사, 해시는 채팅 Claude가 알려 준 값과 대조), `docs/결정기록/041-임베딩-large-다시-측정-전-결정.md`
- Modify: `docs/평가/embedding-large-retry.md`(다섯째 줄 정정 메모), `docs/개발일지/2026-11-24.md`(새로), `docs/AI-실수-기록.md`

- [ ] **Step 1:** 두 파일을 복사하고 해시를 확인한다. 줄 끝은 LF(.gitattributes)
- [ ] **Step 2:** 결정기록 041을 쓴다. 내용은 설계 5절(5-1 사용자 결정 4개, 5-2 제안 2개, 5-3 정한 것 4개), 6절 B-3과 판정 방법, 7절 멈춤 규칙, 명시적 예외 두 개(시간 선 — 4단계 시간을 보고 사람 판정 전에 정함, ⑳). 끝에 빈 절 "덧붙임: 시간 선(4단계 시간을 본 뒤·판정 전)"을 두고 Task 4에서 채운다
- [ ] **Step 3:** 리포트 다섯째 줄 뒤에 정정 메모: "(정정 2026-11-24: 선은 4단계 시간을 본 뒤 사람 판정 전에 정한다 — 아래 측정 전 결정 3. 채팅 Claude가 두 번째 지시에서 이 줄을 고치라고 하지 않음)". 원래 줄은 지우지 않는다
- [ ] **Step 4:** 개발일지 2026-11-24 첫 절(한 것·결정한 것·AI 실수). AI 실수 한 줄: "채팅 Claude: 미리 재기 리포트 다섯째 줄을 측정 전 결정 3에 맞게 고치라는 지시를 빠뜨림 → Task 0에서 정정 메모". AI-실수-기록에 같은 줄(링크는 그 개발일지 절)
- [ ] **Step 5:** 커밋 → `git push -u origin docs/emb-retry-preview`(사용자 확인 뒤). 041 커밋 해시를 보고한다

### Task 1: 4단계 코드 (AI 비용 0)

**Files:**
- Create: `measure/emb_retry.py`, `tests/measure/test_emb_retry.py`
- Modify: `measure/stage2.py`(`result_row`의 `card`, `--open-test-set`), `tests/measure/test_stage2.py`

**Interfaces:**
- Consumes: `measure.stage2.method_order(methods, i)`, `stage2.cost_usd(inp, outp)`, `stage2.parse_result_row(r)`, `measure.v17_answer.bundle_deps(deps, bundle, models, get_conn)`, `evaluation.followups.load_followups(path)`, `measure.v17_stage1.measure_sets(...)`, `measure.emb_large.embed_for`·`write_outputs`, `measure.v17_blind4.build_sheet(q30, fu, rng, label)`
- Produces (`measure/emb_retry.py`):
  - `OUT = ROOT/"measure"/"out"/"emb-retry"`, `OPEN_FILE = OUT/"stage4-open.json"`, `BACKUP_SHA256 = "ba8433aa9fce8ea6d5c5b1e1004801215c745c9074ad5e9c0a790d373e85bbcb"`
  - `write_open_file(commit: str, path: Path = OPEN_FILE) -> Path` — 파일이 있으면 멈춤. 내용 `{"decision_record": "041", "commit": commit, "written_at": ISO 시각}`
  - `require_open_file(path: Path = OPEN_FILE, *, repo: Path = ROOT) -> dict` — 파일이 없거나, `commit`이 저장소에 없거나, HEAD의 조상이 아니면 `SystemExit`
  - `load_backup_pages(path: Path = ROOT/"measure"/"out"/"v17-rollout-backup"/"chunks-manual.jsonl", sha256: str = BACKUP_SHA256) -> dict[int, tuple[str, int]]` — 옛 번호 → (doc_id, 쪽). 해시가 다르면 멈춤
  - `old_chunk_refs_to_pages(refs: str, backup: dict[int, tuple[str, int]]) -> tuple[str, int]` — `|`로 이은 기대 근거에서 `chunk:<n>`(1 ≤ n ≤ 297)을 `manual:<쪽>`으로 바꾼 글과 바꾼 수. 298~335·`manual:`·`guide:`는 그대로. 바꾼 뒤 겹치면 처음 것만. 백업에 없는 번호는 `SystemExit`
  - `build_test_set(sealed: Path, new_rows: list[dict], split_json: Path, backup: dict, out: Path) -> dict` — 봉인 파일 해시가 `split_json["test_sha256"]`과 다르면 멈춤. 봉인 20행 + 새 행을 합치고 기대 근거에 `old_chunk_refs_to_pages`를 써서 `out`에 쓴다. `out`이 있으면 멈춤. `{"rows", "sha256", "converted_rows"}`
  - `run_followups_same_run(methods: list[str], label: str, *, client_for: Callable[[str], Callable], rows: list[dict]) -> list[dict]` — 대화 i마다 `method_order(methods, i)` 순서로, 방법마다 대화 전체를 그 방법의 client로 돈다(앞 대화는 그 방법의 답만). 행 열은 `FU_COLUMNS`
  - `FU_COLUMNS = ["dialog_id", "turn", "type", "model_id", "method", "question", "expected_ref", "expected_found", "found", "answer", "cited_refs", "retrieved_refs", "retrieved_chunk_ids", "rewritten_question", "rewrite_ms", "latency_ms", "llm_ms", "input_tokens", "output_tokens", "cost_usd", "rule_blocked", "error", "human_verdict"]`(토큰·비용은 답변 + 질문 바꾸기 합)
  - `time_summary(rows_by_set: dict[str, list[dict]], base: str = "m0", cand: str = "emb_large") -> dict` — 세트별(`test`·`q30`·`fu`)과 `pooled`(모든 행을 합친 평균), 회차별(`r1`·`r2`)과 `all`. 값은 `n`, `base_ms`, `cand_ms`, `diff_ms`, `base_non_llm_ms`, `cand_non_llm_ms`, `diff_non_llm_ms`. 오류·규칙으로 막힌 행·시간 빈 행은 뺀다. 찾은 수·적중은 넣지 않는다
  - `cost_summary(rows_by_set, base="m0", cand="emb_large") -> dict` — `pooled`와 세트별 `ratio`(후보 질문당 비용 ÷ 운영), 오류 행이 있으면 `ratio_without_errors`
  - `split_by_method(rows_by_run: dict[str, list[dict]]) -> dict[str, list[dict]]` — 같은 실행 CSV(방법 열)를 `"<회차 이름>-<방법>"` 키로 나눈다(`build_sheet` 입력용)
  - `rule17(verdicts: list[str]) -> str` — 모든 회차 "정답"(경계 포함)이면 "정답", 한 회차라도 "환각"이면 "환각", 그 밖은 "오답"
  - `b3(test_hit5: dict, test17: dict, q30_17: dict, fu17: dict, cost: dict, time: dict, line: dict) -> dict` — 설계 6절 B-3 여섯 줄 각각 `{"ok": bool, "detail": ...}`과 `"all_ok"`. 10%p는 `math.ceil(0.10 * 분모)` 문장
  - `b3`의 `test_hit5`는 `OUT/"stage4-search"/"summary.json"`의 `["test"]`(`{"production": {"hit5", "denominator"}, "emb_large": {...}}`), `line`은 `{"total_ms": 숫자, "non_llm_ms": 숫자 또는 None}`
  - CLI: `python -m measure.emb_retry open <commit>` | `search-test --test-set <path>` | `followups --label <label>` | `time-summary <r1·r2 결과 CSV들>` | `blind-regression --label <label> --date <날짜>`. `time-summary`는 파일 이름 `emb-retry-<세트>-r<n>-<날짜>.csv`에서 세트(`test`·`q30`·`fu`)와 회차를 읽어 행에 `run`을 붙인다. 이름이 맞지 않으면 멈춤

- [ ] **Step 1: 실패하는 테스트를 쓴다** (`tests/measure/test_emb_retry.py`, `tests/measure/test_stage2.py`)

```python
def test_require_open_file_missing_stops(tmp_path): ...            # SystemExit
def test_require_open_file_unknown_commit_stops(tmp_path): ...     # 저장소에 없는 40자 해시 → SystemExit
def test_require_open_file_accepts_ancestor_commit(tmp_path): ...  # tmp git 저장소: 커밋 A 뒤 B, 파일에 A → 통과
def test_write_open_file_refuses_existing(tmp_path): ...
def test_old_chunk_refs_page_conversion():
    backup = {12: ("manual-lg-fx25", 41), 13: ("manual-lg-fx25", 41)}
    assert old_chunk_refs_to_pages("chunk:12|chunk:13|manual:41", backup) == ("manual:41", 2)
def test_old_chunk_refs_keeps_guides_and_pages():
    assert old_chunk_refs_to_pages("chunk:300|guide:guide-lg-drum-errors|manual:7", {}) == ("chunk:300|guide:guide-lg-drum-errors|manual:7", 0)
def test_old_chunk_refs_unknown_id_stops(): ...                    # chunk:5, 백업 {} → SystemExit
def test_load_backup_pages_hash_mismatch_stops(tmp_path): ...
def test_build_test_set_sealed_hash_mismatch_stops(tmp_path): ...
def test_build_test_set_refuses_existing_out(tmp_path): ...
def test_followups_same_run_alternates_methods(): ...              # 대화 0: m0→emb_large, 대화 1: emb_large→m0 (가짜 client가 부른 순서 기록)
def test_followups_history_stays_within_method(): ...             # emb_large 2턴의 history 답 = emb_large 1턴 답
def test_followups_cost_includes_rewrite_tokens(): ...            # 답변 100/10 + 바꾸기 50/5 → input 150, output 15, cost_usd = stage2.cost_usd(150, 15)
def test_time_summary_has_no_found_or_hit_keys(): ...             # 결과 dict를 json으로 바꾼 글에 "found"·"hit" 없음
def test_time_summary_excludes_errors_and_blocked(): ...
def test_time_summary_pools_all_rows_not_set_means():
    # test 세트 1행(m0 1000, cand 2000), q30 3행(m0 1000, cand 1000) → pooled diff_ms == 250.0 (세트 평균의 평균이면 500)
def test_time_summary_non_llm_is_latency_minus_llm(): ...
def test_cost_summary_ratio_without_errors(): ...
def test_split_by_method_keys(): ...                              # {"emb-retry-q30-r1-2026-11-24": [...]} → "...-r1-2026-11-24-m0", "...-emb_large"
def test_rule17():
    assert rule17(["정답", "정답(경계)"]) == "정답"; assert rule17(["정답", "환각"]) == "환각"; assert rule17(["정답", "오답"]) == "오답"
def test_b3_10pp_rounds_up(): ...                                 # 분모 46 → 필요 +5, +4면 실패
def test_b3_time_line_both_parts(): ...                           # line {"total_ms": 1500, "non_llm_ms": 500}: non_llm 600이면 실패
def test_stage2_result_row_without_card_column(): ...             # questions.csv 행(card 없음) → card ""
def test_stage2_refuses_test_set_without_flag(tmp_path): ...
def test_stage2_refuses_test_set_without_open_file(tmp_path): ...
```

- [ ] **Step 2:** `pytest tests/measure/test_emb_retry.py tests/measure/test_stage2.py -v` → 새 테스트가 실패하는지 본다. 테스트만 커밋
- [ ] **Step 3: 구현** — `measure/emb_retry.py`(위 Interfaces). `stage2.result_row`는 `case.get("card", "")`. `stage2.main`: 파일 이름에 `test`가 있으면 `--open-test-set`과 `require_open_file()`가 모두 있을 때만 진행(없으면 지금 문구로 멈춤). `run_followups_same_run`의 client는 `answer_question(..., debug=True, history=...)`를 부르고, 바꾸기 토큰은 `deps.rewrite`를 감싸 `r.usage`를 더한다. `search-test`는 `measure_sets({"test": cases}, [None, "emb_large"], ...)`로 재고 `write_outputs`로 `OUT/"stage4-search"`에 쓰며, 화면에는 파일 경로만 찍는다
- [ ] **Step 4:** 같은 pytest → 모두 통과. 전체 `pytest -q` 통과 수를 보고(지금 803)
- [ ] **Step 5:** 구현 커밋 → `superpowers:requesting-code-review`로 새 검토자 한 번(확인용 세트 파일을 읽지 말라고 요청문에 적는다). 지적은 고치기 전에 보고, 측정·판정에 닿는 지적은 사용자 결정

### Task 2: 확인용 세트 준비 (AI 비용 0, 11/24 13:00 전에 시작)

**Files:**
- Create: `evaluation/paraphrase_test_v197.csv`(합친 확인용, 커밋), git 밖 `measure/out/emb-retry/confirm-review.md`

- [ ] **Step 1 (사용자):** 폼 응답 CSV를 내려받아 이름·연락처 칸을 지운 채 git 밖 경로에 둔다(채팅 Claude가 단계별 가이드). 13:00을 넘겼으면 여기서 멈추고 "미완료"
- [ ] **Step 2:** `python -m measure.emb_retry open <041 커밋 해시>` → 열기 파일
- [ ] **Step 3:** 새 응답자 3명의 확인용 10카드 문장을 정리한다(검색 개선 계획 Task 1 Step 1 규칙: 중복 제거, 동의 안 한 응답 제외, 개인정보는 가짜 값으로 바꾸거나 제외). 2026-11-13 뒤 응답은 넣지 않고 수만 적는다. 카드의 11/10 기대 근거를 붙인다. id는 `n<카드>-<순번>`
- [ ] **Step 4 (멈춤):** 카드와 다른 것을 묻는 문장 후보를 `confirm-review.md`에 적는다 → 채팅 Claude 원문 확인(답 없음 → 함정, 다른 쪽에 답 → 제외 후보) → 사용자 확정
- [ ] **Step 5:** `build_test_set(...)` → 봉인 해시 확인, 합친 행 수·해시·바꾼 행 수를 보고 → 커밋

### Task 3: 실행과 시간 보고 (AI 비용 약 0.2달러)

**Files:**
- 결과(커밋은 Task 6에서): `evaluation/results/emb-retry-{test,q30}-r{1,2}-<날짜>.csv`, `evaluation/results/emb-retry-fu-r{1,2}-<날짜>.csv`. 로그(git 밖): `measure/out/emb-retry/logs/`

- [ ] **Step 1:** 장부 행 "4단계: (확인용 N + 30 + 31턴) × 2벌 × 2회, 예상 약 0.2" → `check_budget` 통과
- [ ] **Step 2:** 아래 명령을 차례로 돌린다. 모든 명령의 출력은 로그 파일로만 보낸다(`> measure/out/emb-retry/logs/<라벨>.log 2>&1`). 확인하는 것은 종료 코드와 결과 파일이 생겼는지뿐이다
  - `python -m measure.emb_retry search-test --test-set evaluation/paraphrase_test_v197.csv`
  - `python -m measure.stage2 evaluation/paraphrase_test_v197.csv --methods m0 emb_large --label emb-retry-test-r1 --open-test-set`
  - `python -m measure.stage2 evaluation/questions.csv --methods m0 emb_large --label emb-retry-q30-r1`
  - `python -m measure.emb_retry followups --label emb-retry-fu-r1`
  - 같은 세 개를 `-r2`로
- [ ] **Step 3:** `python -m measure.emb_retry time-summary <결과 CSV 6개>` → `time_summary`만 출력. 오류·막힌 행 수와 함께 사용자에게 보고하고 **멈춘다**. 찾은 수·5위 안·비용·답은 보고하지 않는다
- 실행 중이나 보고 중에 시간 밖 결과가 화면·보고에 보였으면 그 자리에서 멈추고 무엇이 보였는지 보고한다(설계 7절 멈춤 3, 사용자가 이어갈지 정함)

### Task 4: 시간 선 커밋 (AI 비용 0)

- [ ] **Step 1 (사용자):** 선을 정한다. 모양은 "전체만" 또는 "전체 + 답변 AI 밖"(설계 5-3의 3)
- [ ] **Step 2:** 결정기록 041 "덧붙임: 시간 선"에 숫자·모양·결정 시각을 적고, 리포트 측정 전 결정 3 아래에도 같은 줄을 적는다 → 커밋 → push(사용자 확인 뒤)
- [ ] **Step 3:** 이제 연다: `cost_summary`, 확인용 검색 요약(`OUT/stage4-search/summary.json`), 사람 판정 대상 수. 숫자만 보고. 질문 임베딩 비용은 비교에서 빼고 글자 수 × 단가(small 2e-8, large 1.3e-7 글자당)로 따로 적는다(설계 5-3의 2)

### Task 5: 판정과 B-3 (AI 비용 0, 11/24 24:00까지)

- [ ] **Step 1:** 확인용: `python -m measure.stage2 <test r1> <test r2> --blind --label emb-retry-test` → 대응표 해시를 판정 전에 커밋
- [ ] **Step 2:** 회귀: `python -m measure.emb_retry blind-regression --label emb-retry --date <날짜>`(`split_by_method`로 나눈 뒤 `v17_blind4.build_sheet`) → 판정지·대응표는 git 밖, 대응표 해시를 판정 전에 커밋
- [ ] **Step 3 (멈춤):** 채팅 Claude가 확인용 클릭 판정 화면과 회귀 ⑳용 세 AI 요청문(덧붙임 판정 규칙 033 포함)·합치기 화면을 만든다. 사용자가 확인용 답 전부와 ⑳의 사용자 몫(갈림·경계·환각 후보 + 일치 중 무작위 30개)을 판정. "찾지 못함"은 규칙(함정이면 정답, 아니면 오답)
- [ ] **Step 4:** 대응표 공개 → `rule17`로 세트별 집계 → `b3(...)` → 결과 표. 경계 판정을 뒤집으면 결론이 바뀌는지 적는다
- [ ] **Step 5:** 결정기록 032 다시 볼 조건: 두 벌 답에 "설명서에 없는 코드에 다른 코드의 해결 절차를 붙인" 환각이 있으면 따로 적고 사용자에게 알린다(채택 판정과 별개)
- [ ] 24:00까지 끝나지 않으면 여기서 멈추고 끝낸 단계까지 기록한다(결론 "미완료", 남은 판정은 12/2부터)

### Task 6: 결론 기록과 PR

**Files:**
- Create: `docs/결정기록/042-임베딩-large-다시-결론.md`
- Modify: 리포트(맨 위 "정리": 결론·기준별 결과·비용·한계 — 설계 10절 전부와 실행 중 생긴 것), 개발일지 2026-11-24, AI-실수-기록, `evaluation/results/`(판정이 끝난 결과 CSV·대응표)

- [ ] **Step 1:** 결정기록 042(채택 후보 / 미채택 / 미완료와 근거), 리포트 "정리"
- [ ] **Step 2:** `superpowers:requesting-code-review`로 최종 검토(확인용 세트 파일 읽기 금지를 요청문에) → 지적을 고치기 전에 보고
- [ ] **Step 3:** 커밋 → push → PR 하나(사용자 확인) → 병합(사용자 확인). 병합 해시를 보고(2차 Task 2 개발일지에 적을 값)
- 채팅 Claude: 노션 단계 칸 "v1.97", v1.97 페이지, 도구 비교 모음, 인수인계 노트
