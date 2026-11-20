# 펴봄 임베딩 모델 바꾸기(v1.9) — 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 임베딩 모델을 `text-embedding-3-small`에서 `text-embedding-3-large`(1536차원)로 바꾸면 검색·답이 나아지는지 측정 전에 정한 기준(설계 6절)으로 판정하고, 채택되면 2차(11/25) 전에 운영에 반영한다.

**Architecture:** 운영 조각과 글·번호가 같은 실험 조각 한 벌(`emb_large`)을 `bundle_chunks`에 후보 모델로 다시 임베딩해 넣고, 측정 코드가 벌마다 질문 임베딩 모델을 따로 쓰게 한다. 운영 코드에는 차원 설정만 더하고(설정이 없으면 요청이 지금과 같음), 반영 때 환경 변수와 `chunks` 임베딩을 함께 바꾼다. 새 코드는 `measure/emb_large.py`(측정)·`measure/emb_rollout.py`(반영)·`measure/stage4.py`(4단계)에 모은다.

**Tech Stack:** Python 3.14, pytest, Neon Postgres + pgvector, OpenAI 임베딩(`dimensions` 매개변수)·답변(기존 코드), Vercel

**Spec:** `docs/superpowers/specs/2026-11-20-embedding-large-design.md` (사용자 승인 2026-11-20). 실행하는 사람은 설계와 이 계획을 함께 읽는다. 단계·판정 방식의 틀은 Fable 설계 6절·Fable 계획 Task 7·8과 v1.7 계획 Task 11을 그대로 쓴다.

## Global Constraints

- 채택 기준(설계 6절, 측정 전 확정, 결과를 본 뒤 바꾸지 않음): B-1 개발용 P 5위 안 운영 +3 이상(분모 20) 그리고 30문항 5위 안 1문항 넘게 안 떨어짐 / B-2 개발용 사람 판정 정답 +3 이상(분모 21)·환각 0·질문당 비용 1.5배 이하·응답 시간 +0.5초 이하·5C 3회 모두 `found` true / B-3 Fable 설계 6절 B-3과 같음(확인용 10%p는 실제 분모로 문장 수 올림)
- 후보: `text-embedding-3-large`, `dimensions=1536`, 조각·질문 모두. 코드 이름 `emb_large`(보고에만). 기록 문장에는 "임베딩 large", 실험 이름 "임베딩 모델 바꾸기", 노션 단계 "v1.9"
- 비교 기준점은 지금 운영 `chunks`(측정 코드의 `None` = production)
- 운영 동작은 Task 6 전까지 바뀌지 않는다. `OPENAI_EMBED_DIMENSIONS`가 없으면 임베딩 요청 인자는 지금과 같다(`model`·`input`만)
- OpenAI 장부 상한 1달러(`check_budget(rows, new, cap_usd=1.0)`), 운영 잔액 1달러 이상. large 단가는 글자당 `1.3e-7`달러(0.13달러/100만 토큰, 글자 = 토큰 가정). 멈출 때: `check_budget` 실패, 실제 비용이 그 행 예상의 2배 초과, 원인 모를 오류. 유료 실행 중 측정 코드를 고치지 않는다
- 확인용 세트는 `measure/out/emb-large/stage3-pass.json`(Task 4가 B-2 통과일 때만 씀)이 있을 때만 연다. 검토 서브에이전트 요청문에도 이 금지를 적는다
- 운영 `chunks`는 Task 6의 바꾸기·되돌리기(사용자 확인 뒤) 말고는 읽기만. `bundle_chunks`는 행 추가만, 지우기·표 구조 변경은 사용자 확인 뒤
- 운영 반영 때 질문 모델과 조각 모델이 섞인 시간 상한 15분, 넘으면 되돌림(설계 8절 3)
- 일정·멈춤(설계 7절): 1단계 11/22 밤, 3·4단계(준비 포함) 11/23 밤, 반영은 11/24 안에 백업·되돌리기 확인까지 끝낼 수 있을 때만. 반영이 밀리면 이 계획은 결론("채택 후보")까지
- 설명서 글·조각 글·질문 글은 리포트·출력에 넣지 않는다(수·위치·해시만). 백업과 원자료는 `measure/out/emb-large/`(git 밖)
- CLAUDE.md 규칙 그대로: 테스트 먼저 커밋, 커밋 메시지는 먼저 보여 주고 확인받은 뒤 커밋, push·PR·병합 직전 사용자 확인

## Review Focus

1. 반영 뒤 로컬 `.env`가 small 그대로라 다음 적재(2차 모델 추가)가 small로 임베딩됨 → 반영 Task에서 `.env`·`.env.example`·`run_config.PRODUCTION`을 함께 바꾸고, 다르면 `warn_if_different`가 알린다 (Task 1 `test_production_defaults_include_embedding`, Task 6 Step 7)
2. 차원 설정이 실수로 운영 small 요청에 붙어 벡터가 조용히 바뀜 → 설정이 없으면 요청에 `dimensions` 키가 없다 (Task 1 `test_request_has_no_dimensions_by_default`)
3. 같은 질문 글자를 두 벌이 공유하는 임베딩 캐시 때문에 후보 벌이 small 벡터로 검색됨 → 벌마다 다른 모델로 임베딩한다 (Task 2 `test_measure_sets_uses_embed_for_per_bundle`)
4. 후보 조각 임베딩 도중 API 오류로 일부만 들어간 한 벌로 측정 → 임베딩을 다 받은 뒤 한 트랜잭션으로 넣고, 실패하면 아무것도 넣지 않는다 (Task 2 `test_store_reembedded_inserts_nothing_when_embed_fails`)
5. 백업 뒤 `chunks`가 바뀌어(조각 추가 등) 바꾸기가 일부만 적용됨 → 바뀐 행 수가 기대와 다르면 트랜잭션 전체를 되돌린다 (Task 6 `test_swap_refuses_when_rowcount_differs`)

## 파일 구조

- Modify `app/core/config.py`(`openai_embed_dimensions`), `app/retrieval/embeddings.py`(모델·차원 지정), `evaluation/run_config.py`(운영 기본값에 임베딩), `.env.example`
- Create `measure/emb_large.py` — 후보 설정, 벌별 질문 임베딩, 후보 조각 저장·대조, 순위 구간, CLI `python -m measure.emb_large estimate|store|verify|measure`
- Modify `measure/v17_stage1.py`(`measure_sets`에 `embed_for`), `measure/search_eval.py`(`run_eval`에 `depth`), `measure/v17_answer.py`(`bundle_deps`가 질문 임베딩도 바꿈)
- Create `measure/stage4.py` — Fable 계획 Task 8 Interfaces 그대로(통과 파일 경로만 다름). Modify `measure/stage2.py`(확인용 열기 문)
- Create `measure/emb_rollout.py` — 백업·바꾸기·되돌리기, CLI `python -m measure.emb_rollout backup|swap|restore`
- Tests: `tests/retrieval/test_embeddings.py`, `tests/core/test_config.py`(있으면 덧붙임), `tests/evaluation/test_run_config.py`(있으면 덧붙임), `tests/measure/test_emb_large.py`, `tests/measure/test_stage4.py`, `tests/measure/test_emb_rollout.py`
- 문서: 설계, 이 계획, `docs/결정기록/035-임베딩-측정-전-결정.md`, `docs/결정기록/036-임베딩-결론.md`, `docs/평가/embedding-large.md`, 개발일지, `docs/AI-실수-기록.md`. git 밖: `measure/out/emb-large/`

## 브랜치

| 브랜치 | Task |
|---|---|
| `docs/embedding-large-plan` | Task 0 |
| `feat/embedding-large-code` | Task 1~2 (측정 전에 병합해 측정 코드를 고정. 병합 뒤 운영 `/api/health`) |
| `feat/embedding-large-measure` | Task 3~5, Task 7 |
| `feat/embedding-large-rollout` | Task 6 (채택됐을 때만) |

---

### Task 0: 설계·계획·측정 전 결정 커밋 (AI 비용 0)

**Files:** Create 설계·계획(프로젝트 지식에서 그대로 복사, 해시 대조), `docs/결정기록/035-임베딩-측정-전-결정.md`, `docs/평가/embedding-large.md`. Modify 개발일지

- [ ] **Step 1:** 설계와 이 계획을 저장소에 넣는다(사용자가 프로젝트 지식 파일을 전달, 해시를 보고).
- [ ] **Step 2:** 결정기록 035: 설계 10절 사용자 결정 4개(기준 숫자, 4단계 판정 방법, 섞이는 시간 상한 15분, 이름)와 채팅 Claude가 정한 4개(확인용 구성 031 그대로·031 뒤 응답 제외, 반영이 밀리면 결론까지, 장부 상한 1달러, 일정·멈춤), 방법 A를 고른 이유(설계 4절 요약). 날짜와 출처 절을 단다.
- [ ] **Step 3:** `docs/평가/embedding-large.md`: 맨 위 "정리"(빈칸), "판단 기준(측정 전 확정)"에 설계 6절 B-1·B-2·B-3·결론과 7절 멈춤 규칙, "장부(상한 1달러)" 표(설계 9절 예상 행).
- [ ] **Step 4:** 개발일지: PR #79 병합 커밋 `aaf31cb`, 이번 브랜치.
- [ ] **Step 5:** 커밋 → push·PR·병합(사용자 확인).

### Task 1: 임베딩 모델·차원 설정 (운영 코드, 동작은 그대로)

**Files:** Modify `app/core/config.py`, `app/retrieval/embeddings.py`, `evaluation/run_config.py`, `.env.example`. Test `tests/retrieval/test_embeddings.py`, `tests/core/`, `tests/evaluation/`

**Interfaces:**
- Produces: `Settings.openai_embed_dimensions: int | None` ← 환경 변수 `OPENAI_EMBED_DIMENSIONS`(빈 값·없음 → `None`)
- Produces: `embed_texts(texts: list[str], client=None, *, model: str | None = None, dimensions: int | None = None) -> list[list[float]]` — `None`이면 설정값. 최종 `dimensions`가 `None`이면 요청에 그 키를 넣지 않는다
- Produces: `embed_query(text: str, client=None, *, model: str | None = None, dimensions: int | None = None) -> list[float]`
- Produces: `run_config.PRODUCTION`에 `"openai_embed_model": "text-embedding-3-small"`, `"openai_embed_dimensions": None`(RECORDED에 중복 없이)

- [ ] **Step 1: 실패하는 테스트**

```python
def test_request_has_no_dimensions_by_default(fake_client, settings_small):
    embed_texts(["가"], client=fake_client)
    assert fake_client.calls == [{"model": "text-embedding-3-small", "input": ["가"]}]

def test_dimensions_and_model_override_are_sent(fake_client, settings_small):
    embed_query("가", client=fake_client, model="text-embedding-3-large", dimensions=1536)
    assert fake_client.calls == [{"model": "text-embedding-3-large", "input": ["가"], "dimensions": 1536}]

def test_settings_dimensions_from_env(monkeypatch):  # "" → None, "1536" → 1536 (get_settings 캐시 비우기)

def test_production_defaults_include_embedding(settings_large_1536):
    assert any(d.startswith("openai_embed_model=") for d in differences(settings_large_1536))
```

- [ ] **Step 2:** `.venv/Scripts/python -m pytest -q tests/retrieval tests/core tests/evaluation` → 새 테스트 FAIL 확인 → 테스트 커밋
- [ ] **Step 3:** 구현(위 Interfaces). `.env.example`에 `OPENAI_EMBED_DIMENSIONS=`(빈 값, 설명 한 줄)
- [ ] **Step 4:** `.venv/Scripts/python -m pytest -q -m "not integration"` 전부 PASS → 구현 커밋

### Task 2: 후보 조각 저장과 벌마다 질문 임베딩 (측정 코드, AI 비용 0)

**Files:** Create `measure/emb_large.py`, `tests/measure/test_emb_large.py`. Modify `measure/v17_stage1.py`, `measure/search_eval.py`, `measure/v17_answer.py`

**Interfaces:**
- Consumes: Task 1 `embed_texts`·`embed_query`의 `model`·`dimensions`; `measure.v17_bundle.BundleChunk`·`bundle_exists`
- Produces (`measure/emb_large.py`):
  - `EmbedSpec(model: str, dimensions: int | None)`(frozen dataclass), `CANDIDATE = EmbedSpec("text-embedding-3-large", 1536)`, `BUNDLE = "emb_large"`, `BUNDLE_EMBED: dict[str, EmbedSpec] = {BUNDLE: CANDIDATE}`, `PRICE_PER_CHAR = 1.3e-7`
  - `embed_for(bundle: str | None, base: Callable[[str], list[float]]) -> Callable[[str], list[float]]` — `BUNDLE_EMBED`에 있으면 그 설정의 `embed_query`(같은 설정이면 같은 함수 객체), 아니면 `base`
  - `production_chunks(conn) -> list[BundleChunk]` — 운영 `chunks` 전부(설명서+가이드), id 순, 읽기만
  - `store_reembedded(name: str, chunks: list[BundleChunk], spec: EmbedSpec, *, conn, embed=None) -> int` — 이미 있는 한 벌이면 멈춤. 본문을 그대로(덧붙임 없이) spec으로 모두 임베딩한 뒤 한 트랜잭션으로 같은 id·doc_id·page·content로 넣는다. 넣은 행 수
  - `text_mismatches(conn, name: str) -> list[int]` — 운영과 한 벌의 id 집합·doc_id·page·content가 다른 id(없으면 `[]`)
  - `rank_buckets(ranks: list[int | None]) -> dict[str, int]` — 키 `"1-5","6-10","11-20","21-30","31-50","51-100","100+"`(`None`은 `"100+"`)
- Produces: `measure_sets(cases, bundles, embed, fns, top_k=5, *, embed_for=None, depth=20)` — `embed_for(b, embed)`로 벌마다 질문 임베딩, 캐시는 (임베딩 함수, 질문 글자)마다. `run_eval(..., depth: int = DEPTH)`
- Produces: `bundle_deps(deps, bundle, models, get_conn)`가 `search`·`diagnostic`과 함께 `embed_query=embed_for(bundle, deps.embed_query)`로 바꾼다

- [ ] **Step 1: 실패하는 테스트** — `test_measure_sets_uses_embed_for_per_bundle`(가짜 embed 두 개: 운영 벌 검색은 small 벡터, `emb_large` 검색은 large 벡터를 받고 각 질문마다 한 번씩만 불림), `test_bundle_deps_swaps_embed_for_emb_large`, `test_bundle_deps_keeps_embed_for_other_bundles`, `test_store_reembedded_refuses_existing_bundle`, `test_store_reembedded_sends_spec_to_embed`(model `text-embedding-3-large`, dimensions 1536), `test_store_reembedded_inserts_nothing_when_embed_fails`, `test_rank_buckets_edges`(5→1-5, 6→6-10, 20→11-20, 21→21-30, 50→31-50, 100→51-100, 101·None→100+), `test_run_eval_depth_finds_rank_beyond_20`
- [ ] **Step 2:** 새 테스트 FAIL 확인 → 테스트 커밋
- [ ] **Step 3:** 구현. CLI `python -m measure.emb_large`: `estimate`(운영 조각 글자 수·예상 비용, DB 읽기만), `store`(장부 확인 뒤), `verify`(`text_mismatches == []`가 아니면 멈춤), `measure [--out 폴더]`(운영·`emb_large`를 한 실행 안에서 `measure_sets(..., embed_for=embed_for, depth=100)`, 결과 CSV·`summary.json`·`buckets.json`, 운영 벌 순위가 `measure/out/v17/fable-stage1/dev-production.csv`·`q30-production.csv`와 다르면 멈춤. 그 파일은 20위까지라 21위 이상은 "20위 밖"으로 맞춰 견줌). `guard_cases_path`는 그대로 쓴다
- [ ] **Step 4:** `pytest -q -m "not integration"` 전부 PASS → 구현 커밋 → PR·병합(사용자 확인) → 운영 `/api/health`
- (2026-11-20 덧붙임, 사용자 승인) 기존 통합 테스트 두 개의 벌 가정 처리: `tests/measure/test_v17_bundle.py`의 `test_guide_chunks_identical_to_production`은 `BUNDLE_EMBED`에 있는 벌(다시 임베딩한 벌)이면 `text_mismatches(conn, name) == []`로, `test_bundle_diag_ids_in_bundle`은 그 벌이면 "진단 조각 id ⊆ 그 벌의 id"만으로 확인한다(1,000,000 이상 조건은 이 벌에만 빼기). 나머지 벌은 지금 그대로. 테스트를 먼저 바꿔 커밋한다(Pre-flight에서 Claude Code가 찾음)

### Task 3: 0단계·1단계 (임베딩 비용)

- [ ] **Step 1:** 잔액(사용자 확인) → `python -m measure.emb_large estimate` → 장부에 0단계 행(글자 수 × `1.3e-7`)과 1단계 행(질문 45개, 두 모델) → `check_budget` 결과를 리포트에
- [ ] **Step 2:** `store` → `verify`(어긋난 id 0개) → 넣은 행 수(설명서 297 + 가이드 35 = 332)와 실제 비용
- [ ] **Step 3:** `python -m measure.emb_large measure --out emb-stage1` → 운영 1~20위 대조 결과(불일치 0)
- [ ] **Step 4:** `measure.fable_split.b1_pass(summary, "emb_large")` → 리포트 "1단계": 5위 안 표(개발용·30문항), 두 벌 순위 구간, 순위가 바뀐 문장(id·순위만). 2026-11-20 사전 확인과 대조
- [ ] **Step 5:** B-1 실패면 미채택으로 적고 Task 7로. 통과면 Task 4. 커밋(메시지 먼저)

### Task 4: 3단계 (답변까지, 개발용 21문장)

- [ ] **Step 1:** 장부(21문장 × 2벌 × 2회 + 5C 3회) → `check_budget`
- [ ] **Step 2:** `python -m measure.stage2 evaluation/paraphrase_dev.csv --methods m0 emb_large --label emb-s3-r1`, 같은 명령 `--label emb-s3-r2`. 5C: `measure/out/v17/stage3/5c.csv`를 `measure/out/emb-large/5c.csv`로 복사해 `--methods emb_large --label emb-s3-5c` → `found` 3회 모두 true인지 자동으로 센다
- [ ] **Step 3:** `python -m measure.stage2 <r1 CSV> <r2 CSV> --blind --label emb-s3` → 대응표 해시를 판정 전에 커밋. 결과 CSV는 판정이 끝날 때까지 커밋하지 않는다
- [ ] **Step 4 (멈춤, 사용자 판정):** 채팅 Claude가 v1.7·Fable과 같은 클릭 판정 화면("덧붙임" 칸 포함)을 만든다. 사용자가 전부 판정
- [ ] **Step 5:** 대응표 공개 → ⑰ → B-2: 정답 +3 이상·환각 0, `summarize_methods`의 `cost_per_q_usd` 비율 1.5 이하(질문 임베딩 비용은 글자 수 × 단가로 두 벌 모두 계산해 함께 적음), `latency_avg_ms` 차이 500 이하, 5C 3/3. 경계 판정을 뒤집었을 때 결론이 바뀌는지 적는다
- [ ] **Step 6:** 032 다시 볼 조건: 두 벌 답 중 "설명서에 없는 코드에 다른 코드의 해결 절차를 붙인" 환각이 있으면 따로 적고 사용자에게 알린다(채택 판정과 별개)
- [ ] **Step 7:** B-2 통과면 `measure/out/emb-large/stage3-pass.json`(날짜·판정 요약·대응표 해시)을 쓰고 Task 5. 실패면 미채택, Task 7

### Task 5: 4단계 (확인용 세트, 3단계를 통과했을 때만)

**Files:** Create `measure/stage4.py`, `tests/measure/test_stage4.py`. Modify `measure/stage2.py`, `measure/emb_large.py`

**Interfaces:**
- Fable 계획 Task 8 Interfaces 그대로: `old_chunk_refs_to_pages`, `load_backup_pages`, `run_followups_same_run`, `stage2.py` `--open-test-set`. 다른 점: 통과 파일은 `measure/out/emb-large/stage3-pass.json`
- `python -m measure.emb_large measure --out emb-stage4 --test-set <합친 확인용 파일>` — 같은 통과 파일이 있을 때만 확인용 검색(운영·후보 5위 안)

- [ ] **Step 1:** 테스트 먼저: `test_old_manual_chunk_ref_becomes_page`, `test_guide_and_page_refs_unchanged`, `test_stage2_refuses_test_set_without_pass_file`, `test_emb_large_measure_refuses_test_set_without_pass_file`, `test_followups_same_run_alternates_methods` → 커밋 → 구현 → 커밋. (Step 1은 3단계 판정을 기다리는 동안 해도 된다. 확인용 파일은 열지 않는다)
- [ ] **Step 2:** 확인용 세트 준비: v1.7 계획 Task 11 "갈래 가" Step 1~3 그대로. 새 응답은 031 구성(새 응답자 3명의 확인용 10카드 문장, 2026-11-13까지 받은 것)만, 그 뒤 응답은 넣지 않고 수만 적는다. 카드와 다른 것을 묻는 문장은 채팅 Claude 원문 확인 → 사용자 확정 → 지난 20문장 해시 확인 → 합친 파일과 새 해시 커밋. 기대 근거에 `old_chunk_refs_to_pages`를 쓰고 바꾼 수를 리포트에
- [ ] **Step 3:** 장부 → 확인용 검색(`emb_large measure --test-set`) → 한 실행 안에서 운영·후보 각 2회: 확인용·30문항은 `stage2 --methods m0 emb_large`(확인용은 `--open-test-set`), 이어지는 질문은 `run_followups_same_run(["m0", "emb_large"], ...)`
- [ ] **Step 4 (멈춤, 판정):** 확인용 답은 `stage2 --blind` 판정지 → 사용자가 전부(채팅 Claude 클릭 화면). 회귀(30문항·이어지는 질문)는 `measure.v17_blind4`와 같은 방식의 판정지 → ⑳: "찾지 못함"은 규칙, 세 AI 일치는 AI 판정, 갈림·경계·환각 후보 + 일치 중 무작위 30개는 사용자(채팅 Claude가 덧붙임 규칙을 넣은 세 AI 요청문과 합치기를 만든다). 대응표 해시는 판정 전에 커밋
- [ ] **Step 5:** B-3 → 결론(설계 6절). 채택이고 11/23 밤 안이면 Task 6, 아니면 "채택 후보"로 Task 7

### Task 6: 운영 반영 (채택됐을 때만, 11/24)

**Files:** Create `measure/emb_rollout.py`, `tests/measure/test_emb_rollout.py`. Modify `.env`(로컬, 커밋 안 함), `.env.example`, `evaluation/run_config.py`, `docs/결정기록/015-최종-설정.md`(덧붙임)

**Interfaces:**
- Consumes: Task 2 `text_mismatches`, `CANDIDATE`
- Produces: `backup_embeddings(conn, path: Path) -> dict`(JSONL 한 줄에 id·doc_id·본문 SHA-256·임베딩, 파일이 이미 있으면 멈춤, `{"rows", "sha256"}`), `load_backup(path: Path) -> dict[int, list[float]]`, `vectors_from_bundle(conn, name: str) -> dict[int, list[float]]`(`text_mismatches`가 비어 있을 때만), `swap_embeddings(conn, vectors: dict[int, list[float]], *, expect_rows: int) -> int`(한 트랜잭션, 바뀐 행 수가 `expect_rows`와 다르면 전체 되돌리고 멈춤)

- [ ] **Step 1:** 테스트 먼저: `test_backup_refuses_existing_file`, `test_backup_roundtrip`, `test_vectors_from_bundle_refuses_text_mismatch`, `test_swap_refuses_when_rowcount_differs` → 커밋 → 구현 → 커밋
- [ ] **Step 2:** 미리보기가 운영 DB를 같이 쓰는지: `vercel env ls`로 `DATABASE_URL`의 적용 환경만 확인(값은 보지 않음) → 보고
- [ ] **Step 3:** `vectors_from_bundle(conn, "emb_large")`(글이 같으면 다시 임베딩하지 않아 비용 0. 다르면 장부 행 뒤 다시 임베딩) → `python -m measure.emb_rollout backup` → 행 수 332·해시, 백업 한 행을 읽어 운영과 대조
- [ ] **Step 4 (사용자):** 채팅 Claude 가이드대로 Vercel 운영 환경 변수 `OPENAI_EMBED_MODEL=text-embedding-3-large`, `OPENAI_EMBED_DIMENSIONS=1536`을 저장(다시 배포는 아직)
- [ ] **Step 5:** 사용자 확인 뒤 운영 다시 배포 → 배포가 운영에 올라간 시각 기록 → 곧바로 `python -m measure.emb_rollout swap`(332행) → 끝난 시각 기록. 섞인 시간이 15분을 넘으면 Step 8
- [ ] **Step 6:** `/api/health`, 5C 질문 1회(장부 먼저)
- [ ] **Step 7:** 로컬 `.env`를 같은 값으로, `run_config.PRODUCTION`을 large·1536으로, `.env.example` 설명, 결정기록 015에 최종 설정 바뀜 덧붙임 → `warn_if_different`가 아무것도 알리지 않는지 확인
- [ ] **Step 8:** 장부 → `python -m evaluation --label emb-rollout-r1`·`-r2` → 사용자가 전부 판정(⑰, 합격선 24/30 이상·환각 0, v1.7 9단계와 같음). 미달·오류·섞인 시간 초과면 되돌리기: (사용자) 환경 변수 되돌림 → 다시 배포가 올라가는 순간 `restore`(백업) → `/api/health` → 보고. DB 작업은 사용자 확인 뒤

### Task 7: 결론 기록

- [ ] **Step 1:** 리포트 "정리"(결과·비용·한계·다음 후보), 결정기록 036(결론, 채택/미채택/채택 후보/미완료와 근거), 개발일지, AI 실수 기록(누가 했는지 구분)
- [ ] **Step 2:** 최종 검토 서브에이전트(requesting-code-review, 확인용 세트 파일 읽기 금지를 요청문에) → 지적 목록을 고치기 전에 보고(측정·판정에 닿는 지적은 사용자 결정)
- [ ] **Step 3:** 커밋 → push·PR·병합(사용자 확인). 노션(v1.9 타임라인·도구 비교 모음)과 인수인계 노트는 채팅 Claude
