# 펴봄 조각 설명 붙이기(v1.95) — 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 조각마다 AI가 쓴 짧은 설명을 본문 앞에 붙여 임베딩하면(검색용으로만) 검색·답이 나아지는지 측정 전에 정한 기준(설계 6절)으로 판정하고, 채택되면 11/24에 운영에 반영한다.

**Architecture:** 설명 쓰기와 "설명 붙여 임베딩"을 적재 코드(`ingest/describe.py`)에 넣고, 기본값은 꺼짐(지금 운영과 같은 입력)으로 둔다. 측정 코드는 같은 함수로 332개 조각의 설명을 한 번 써서 git 밖 파일에 남기고, 그 설명으로 실험 조각 한 벌(`ctx_small`, 운영과 번호·본문 같음)을 small로 다시 임베딩해 v1.9 도구로 잰다. 반영은 그 벌의 임베딩을 운영 `chunks`에 한 트랜잭션으로 옮기는 것뿐이다(환경 변수·다시 배포 없음).

**Tech Stack:** Python 3.14, pytest, Neon Postgres + pgvector, OpenAI Responses API(json_schema)·임베딩, Vercel

**계획 확인:** 사용자 2026-11-20(요청문 고정, 자동 검사 멈춤 규칙, 실행 방식 Native = executing-plans 뒤 최종 검토 한 번)

**Spec:** `docs/superpowers/specs/2026-11-20-chunk-context-design.md` (사용자 승인 2026-11-20, 7절 4·8절 7 고침 포함, SHA-256 `9f949cff…`). 실행하는 사람은 설계와 이 계획을 함께 읽는다. 단계·판정·반영의 틀은 v1.9 계획 `docs/superpowers/plans/2026-11-20-embedding-large-plan.md`를 그대로 쓰고, 다른 점만 여기에 적는다.

## Global Constraints

- 채택 기준(설계 6절, 측정 전 확정, 결과를 본 뒤 바꾸지 않음): B-1 개발용 P 5위 안 운영 +3 이상(분모 20) 그리고 30문항 5위 안 1문항 넘게 안 떨어짐 / B-2 개발용 사람 판정 정답 +3 이상(분모 21)·환각 0·질문당 비용 1.5배 이하(두 회차 합친 평균)·응답 시간(아래)·5C 3회 모두 `found` true / B-3 v1.9 설계 6절 B-3과 같고 응답 시간만 아래 세는 법
- 응답 시간(사용자 결정 2026-11-20): 같은 문장·같은 회차에 두 벌 모두 `found`가 true인 쌍만, `latency_ms` 차이(후보 − 운영) 평균 +500ms 이하, 두 회차 쌍을 합쳐 평균. 쌍 10개 미만이면 두 회차 합친 전체 답 평균 차이로 판정. 전체 평균 차이는 기록용으로 늘 함께 적음. 규칙으로 막힌 답(`rule_blocked`)은 뺀다
- 여러 회차 숫자는 두 회차를 합쳐 센다: 정답은 ⑰, 비용·시간은 두 회차 합친 평균
- 후보: 임베딩 입력 = 설명 + `"\n"` + 원문 본문, `text-embedding-3-small`, `dimensions` 없음. 질문 임베딩은 운영 그대로. 코드 이름 `ctx_small`(보고에만). 기록에는 "조각 설명", 실험 이름 "조각 설명 붙이기", 노션 단계 "v1.95"
- 설명 쓰기: `gpt-6-luna`, 추론 `low`, 요청문은 아래 "설명 요청문" 원문 그대로(파일 `ingest/prompts/chunk_context_v1.txt`), 한국어 1~2문장 150자 이하. 한 번만 쓴다: 다시 부르는 것은 API 오류·형식 오류(빈 설명, 150자 초과, JSON 아님)가 난 그 조각만 1회. 그래도 빠진 조각이 있으면 멈추고 보고
- 설명 모델은 답변 모델과 따로 둔다: 설정 `CHUNK_CONTEXT_MODEL`(비면 꺼짐), `CHUNK_CONTEXT_REASONING_EFFORT`(기본 `low`). `run_config.PRODUCTION`에 반영 전 `""`·`"low"`, 반영 뒤 `"gpt-6-luna"`·`"low"`
- 설명 파일: `data/chunk_context/descriptions.jsonl`(git 밖, `.gitignore`에 추가). 한 번 쓴 설명은 다시 쓰지 않고 측정·반영·이후 적재가 모두 이 파일을 쓴다. 리포트에는 수·길이·해시만
- 운영 동작은 Task 6 전까지 바뀌지 않는다. 설명 설정이 비어 있으면 적재 임베딩 입력은 지금과 글자까지 같다
- 화면 인용·답변 AI가 받는 글·인용 검사에는 설명이 들어가지 않는다(`bundle_chunks.content`·`chunks.content`는 원문)
- 장부 상한 1달러(`check_budget(rows, new, cap_usd=1.0)`), 운영 잔액 1달러 이상. 단가: 답변·설명 모델 입력 0.10·출력 0.50달러/100만 토큰(`measure.stage2.PRICE_IN/OUT`), small 임베딩 글자당 `2e-8`. 글자 = 토큰 가정. 멈출 때: `check_budget` 실패, 실제 비용이 그 행 예상의 2배 초과, 원인 모를 오류. 유료 실행 중 측정 코드를 고치지 않는다
- 확인용 세트는 `measure/out/chunk-context/stage3-pass.json`(Task 4가 B-2 통과일 때만 씀)이 있을 때만 연다. 검토 서브에이전트 요청문에도 이 금지를 적는다
- 운영 `chunks`는 Task 6의 바꾸기·되돌리기(사용자 확인 뒤) 말고는 읽기만. `bundle_chunks`는 행 추가만, 지우기·표 구조 변경은 사용자 확인 뒤
- 일정·멈춤(설계 7절): 1단계 11/22 밤, 3·4단계 11/23 밤, 반영은 11/24 안에 백업·되돌리기 확인까지 끝낼 수 있을 때만. 밀리면 이 계획은 결론("채택 후보")까지
- 설명서 글·조각 글·질문 글·설명 글은 리포트·출력에 넣지 않는다. 원자료·표본·백업은 `measure/out/chunk-context/`(git 밖)
- CLAUDE.md 규칙 그대로: 테스트 먼저 커밋, 커밋 메시지는 먼저 보여 주고 확인받은 뒤 커밋, push·PR·병합 직전 사용자 확인

## 설명 요청문 (사용자 확인·고정 2026-11-20, 파일에 글자 그대로)

`{doc_label}` = 문서 제목 + `" — "` + 그 문서 모델들의 `display_name`을 `" · "`로 이음. `{scope}` = 설명서면 `설명서 한 쪽의 글 전체`, 가이드면 `해결 가이드 글 전체`. `{source}` = 그 조각이 잘려 나온 글(설명서는 적재와 같은 쪽 글, 가이드는 적재와 같은 가이드 글 전체). `{chunk}` = 조각 본문. 채우기는 `str.replace`(본문에 중괄호가 있어도 안전).

```text
다음은 가전제품 문서의 글과 그 글에서 잘라 낸 조각입니다.

[문서] {doc_label}
[글의 범위] {scope}

<글>
{source}
</글>

<조각>
{chunk}
</조각>

이 조각을 검색에서 더 잘 찾을 수 있도록, 조각이 위 문서에서 어떤 기능·문제·상황·절차를 다루는지 짧은 맥락을 써 주세요.
- 한국어 1~2문장, 150자 이하로 씁니다.
- 위 글과 조각에 있는 내용만 씁니다. 글에 없는 숫자, 절차, 버튼·기능·코스 이름, 에러 코드를 만들지 않습니다.
- 제품 종류와 문서 이름을 짧게 넣습니다. 쪽 번호는 쓰지 않습니다.
- 조각의 내용을 그대로 옮기지 말고, 무엇을 다루는 부분인지 맥락만 씁니다.
- 맥락 문장만 답합니다.
```

출력 형식: strict json_schema 이름 `chunk_context`, `{"description": string}` 하나. `max_output_tokens=1000`(추론 토큰 포함, 쓴 만큼만 과금). 받은 글은 공백을 한 칸으로 모은 뒤 검사한다. 근거: Anthropic "Contextual Retrieval" 요청문의 틀(글 + 조각 + "검색을 위해 조각의 맥락을 짧게")을 따르고, 원문에 없는 말 금지·길이·쪽 번호 빼기는 설계 5절 4를 옮겼다. 평가 문장·정답 쪽·못 찾은 쪽·특정 쪽 예시는 넣지 않았다.

## Review Focus

1. 설정이 꺼진 운영 적재가 몰래 설명을 붙이거나 AI를 부름 → 꺼져 있으면 임베딩 입력이 본문 그대로이고 설명 함수를 부르지 않는다 (Task 1 `test_ingest_texts_unchanged_when_context_off`)
2. 설명이 저장 본문에 섞여 화면 인용·답변 AI·인용 검사에 들어감 → 임베딩만 설명 붙인 입력, 저장 본문은 원문 (Task 2 `test_store_reembedded_embeds_inputs_but_stores_content`)
3. 반영 뒤 문서를 다시 적재하면 설명을 새로 써서 측정한 임베딩과 달라짐 → 같은 문서·쪽·본문 해시·모델·추론·요청문 해시의 설명이 있으면 다시 쓰지 않고, 반영 전 "새로 쓸 것 0개" 확인 (Task 1 `test_describe_all_reuses_stored_without_calling`, Task 6 Step 4)
4. 로컬 원본 파일과 운영 DB 조각이 달라 엉뚱한 쪽 글로 설명을 씀 → 문서마다 다시 자른 조각이 운영 조각(id 순)과 글자까지 같을 때만 진행 (Task 2 `test_production_items_refuses_text_mismatch`)
5. 결과 CSV의 `"True"`/`"False"`·빈 시간 글자 때문에 시간 쌍을 잘못 셈 → 글자 값을 읽어 같은 회차·같은 문장만 짝짓는다 (Task 2 `test_paired_latency_reads_csv_strings`)

## 파일 구조

- Create `ingest/describe.py` — 설명 요청·검사·저장·재사용, 임베딩 입력 만들기. Create `ingest/prompts/chunk_context_v1.txt`
- Modify `ingest/load.py`(`chunks_with_sources`), `ingest/__main__.py`(설정이 켜졌을 때만 설명 붙임), `app/core/config.py`, `evaluation/run_config.py`, `.env.example`, `.gitignore`
- Create `measure/chunk_context.py` — 운영 조각과 원본 짝짓기, 비용 어림, 설명 쓰기·표본, 실험 벌 저장·대조·측정, 시간 쌍. CLI `python -m measure.chunk_context estimate|describe|sample|store|verify|measure|latency|check-ingest`
- Modify `measure/emb_large.py`(`store_reembedded`의 `inputs`, `measure`의 `bundle`, Task 5에서 `test_set`), `measure/v17_bundle.py`(`SAME_TEXT_BUNDLES`), `measure/stage2.py`(`RULE_033`, `paired_latency`, Task 5에서 `--open-test-set`), `measure/v17_blind4.py`(머리말에 `RULE_033`)
- Create (Task 5) `measure/stage4.py`, (Task 6) `measure/emb_rollout.py`
- Tests: `tests/ingest/test_describe.py`, `tests/core/test_config.py`, `tests/evaluation/test_run_config.py`, `tests/measure/test_chunk_context.py`, `tests/measure/test_emb_large.py`, `tests/measure/test_v17_bundle.py`, `tests/measure/test_stage2.py`, `tests/measure/test_stage4.py`, `tests/measure/test_emb_rollout.py`
- 문서: 설계, 이 계획, `docs/결정기록/037-조각-설명-측정-전-결정.md`, `038-조각-설명-결론.md`, `docs/평가/chunk-context.md`, 개발일지, `docs/AI-실수-기록.md`

## 브랜치

| 브랜치 | Task |
|---|---|
| `docs/chunk-context-plan` | Task 0 |
| `feat/chunk-context-code` | Task 1~2 (측정 전에 병합해 측정 코드를 고정. 병합 뒤 운영 `/api/health`) |
| `feat/chunk-context-measure` | Task 3~5, Task 7 |
| `feat/chunk-context-rollout` | Task 6 (채택됐을 때만) |

---

### Task 0: 설계·계획·측정 전 결정 커밋 (AI 비용 0)

- [ ] **Step 1:** 설계와 이 계획을 저장소에 넣는다(사용자가 전달한 파일, 해시 보고). 이번에 쓸 스킬: executing-plans
- [ ] **Step 2:** 설명 요청문을 측정 전에 고정한다: 위 "설명 요청문"의 코드 블록 안 글을 그대로 `ingest/prompts/chunk_context_v1.txt`에 넣고(끝 줄바꿈 하나, LF, 783바이트) SHA-256을 보고. 기대값 `b8285a9ad40e0de93991e341da2f444cf5672cc1d52627f254214414afe67563`(채팅 Claude가 이 계획의 코드 블록으로 계산), 다르면 멈추고 보고
- [ ] **Step 3:** 결정기록 037: 설계 10절 사용자 결정 7개와 채팅 Claude가 정한 8개, 방법 A를 고른 이유(설계 4절 요약), "조각에 글을 덧붙이지 않는다" 원칙을 "검색용으로만 붙여도 된다"로 바꾼 것, 이 계획에서 정한 것(사용자 결정 2026-11-20: 요청문 고정과 그 SHA-256, 자동 검사에 걸린 조각도 표본과 같은 멈춤 규칙. 채팅 Claude가 정함: 설명 파일의 찾는 키에 조각 번호를 넣지 않는 이유, 표본 시드 20261121). 날짜와 출처 절을 단다
- [ ] **Step 4:** `docs/평가/chunk-context.md`: 맨 위 "정리"(빈칸), "판단 기준(측정 전 확정)"에 설계 6절 전부와 7절 멈춤 규칙, "장부(상한 1달러)" 표(설계 9절 예상 행)
- [ ] **Step 5:** 개발일지: PR #82 병합 `4774d91`, PR #83(2차 설계) 병합 `33cff85`, 이번 브랜치. AI 실수(채팅 Claude, 2026-11-20): 그 전 판 인수인계 노트(v1.9 끝 판, 2차 설계 "승인 보류")만 보고 저장소를 확인하지 않은 채 설계 7절 4에 "2차 설계 승인이 우선"을 넣음 → 실제로는 같은 날 다른 대화에서 승인되어 PR #83으로 병합됨. 계획을 쓰며 저장소를 읽다 발견, 사용자 결정으로 고침(설계 8절 7)
- [ ] **Step 6:** 커밋 → push·PR·병합(사용자 확인)

### Task 1: 설명 쓰기와 적재 연결 (운영 코드, 기본 꺼짐)

**Files:** Create `ingest/describe.py`, `tests/ingest/test_describe.py`. Modify `ingest/load.py`, `ingest/__main__.py`, `app/core/config.py`, `evaluation/run_config.py`, `.env.example`, `.gitignore`

**Interfaces:**
- Produces (`ingest/load.py`): `chunks_with_sources(doc: dict) -> tuple[list[tuple[int | None, str, str]], int]` — (쪽 또는 None, 조각 본문, 그 조각이 잘려 나온 글)과 뺀 문단 수. 설명서의 글 = `strip_page_marker(clean_text(쪽 글), 쪽)[0]`, 가이드의 글 = `drop_out_of_scope` 뒤 글. `build_chunks`는 이것에서 앞 둘만 돌려준다(출력은 지금과 같음)
- Produces (`app/core/config.py`): `Settings.chunk_context_model: str = ""` ← `CHUNK_CONTEXT_MODEL`, `Settings.chunk_context_reasoning_effort: str = "low"` ← `CHUNK_CONTEXT_REASONING_EFFORT`
- Produces (`evaluation/run_config.py`): `PRODUCTION`에 `"chunk_context_model": ""`, `"chunk_context_reasoning_effort": "low"`
- Produces (`ingest/describe.py`):
  - `ContextSpec(model: str, effort: str)`(frozen dataclass), `CANDIDATE_CONTEXT = ContextSpec("gpt-6-luna", "low")`, `MAX_DESC_LEN = 150`, `MAX_OUTPUT_TOKENS = 1000`, `PROMPT_PATH`, `DESC_PATH = ROOT/"data"/"chunk_context"/"descriptions.jsonl"`
  - `ContextItem(doc_id: str, doc_type: str, page: int | None, content: str, source: str, doc_label: str, chunk_id: int | None = None)`(frozen dataclass). `chunk_id`는 기록에만 남기고 찾는 키에는 넣지 않는다(다시 적재하면 번호가 바뀜. 설계 5절 4의 "조각 번호"를 이렇게 남김, 채팅 Claude가 정함)
  - `doc_label(doc: dict, models: dict[str, dict]) -> str`, `context_items(doc: dict, models: dict[str, dict]) -> list[ContextItem]`
  - `prompt_sha256() -> str`(파일 글을 `\r\n`→`\n`으로 맞춘 뒤), `build_prompt(item: ContextItem) -> str`
  - `clean_description(output_text: str) -> str | None` — JSON의 `description`을 공백 한 칸으로 모은 값. JSON 아님·빈 값·150자 초과면 None
  - `describe_chunk(item: ContextItem, spec: ContextSpec, client) -> tuple[str | None, dict]` — `client.responses.create(model=spec.model, input=[{"role": "user", "content": build_prompt(item)}], max_output_tokens=MAX_OUTPUT_TOKENS, reasoning={"effort": spec.effort}, text={"format": CONTEXT_FORMAT})` 1회. dict = `{"input_tokens", "output_tokens", "error"}`(API 오류면 None과 오류 이름)
  - `record_key(item: ContextItem, spec: ContextSpec, prompt_sha: str) -> tuple` = (doc_id, page, 본문 SHA-256, model, effort, prompt_sha)
  - `describe_all(items: list[ContextItem], spec: ContextSpec, *, path: Path = DESC_PATH, client=None, call=describe_chunk, allow_new: bool = True) -> list[str]` — 파일에 같은 키가 있으면 그 설명(부르지 않음). 없으면 최대 2회 부르고 성공하는 즉시 한 줄 덧붙임(키 필드 + `chunk_id`, `description`, `attempts`, `input_tokens`, `output_tokens`, `created`). 끝까지 빠진 조각이 있으면 `MissingDescriptions(count)`(SystemExit 하위)를 모두 돈 뒤 낸다. `allow_new=False`면 빠진 것이 있을 때 부르지 않고 바로 낸다
  - `embedding_input(description: str, content: str) -> str` = `f"{description}\n{content}"`
  - `ingest_texts(doc: dict, chunks_src: list[tuple[int | None, str, str]], settings, models: dict[str, dict], *, describe=describe_all) -> list[str]` — `settings.chunk_context_model`이 비면 본문 목록 그대로(`describe` 부르지 않음), 아니면 `ContextSpec(설정 모델, 설정 추론)`으로 설명을 받아 `embedding_input`

- [ ] **Step 1: 실패하는 테스트** (`tests/ingest/test_describe.py`, `tests/core/test_config.py`, `tests/evaluation/test_run_config.py`)

```python
def test_chunks_with_sources_matches_build_chunks_and_contains_chunk(monkeypatch)  # 설명서(가짜 쪽)·가이드(fixtures/sample_guide.html) 모두: 앞 둘 == build_chunks, 조각 in 글
def test_embedding_input_puts_description_then_newline_then_content():
    assert embedding_input("설명", "본문") == "설명\n본문"
def test_clean_description_rules():
    assert clean_description('{"description": " 가 \n 나 "}') == "가 나"
    assert clean_description('{"description": "  "}') is None
    assert clean_description('{"description": "' + "가" * 151 + '"}') is None
    assert clean_description("JSON 아님") is None
def test_prompt_template_has_each_field_once_and_no_eval_words()  # {doc_label}{scope}{source}{chunk} 각 1회, "평가"·"정답"·"질문" 없음
def test_build_prompt_scope_by_doc_type()  # manual → "설명서 한 쪽의 글 전체", guide → "해결 가이드 글 전체", 본문의 "{x}"는 그대로
def test_describe_chunk_sends_model_effort_schema()  # 가짜 client 인자: model "gpt-6-luna", reasoning {"effort": "low"}, text.format.name "chunk_context", max_output_tokens 1000
def test_describe_all_retries_once_then_reports_missing(tmp_path)  # B는 2회 모두 None → MissingDescriptions(1), B 호출 2회, A는 attempts 1로 파일에
def test_describe_all_reuses_stored_without_calling(tmp_path)  # 같은 키 기록이 있으면 call 0회
def test_describe_all_key_includes_model_effort_prompt(tmp_path)  # 요청문 해시가 다른 기록은 쓰지 않음
def test_describe_all_allow_new_false_refuses_without_calling(tmp_path)
def test_ingest_texts_unchanged_when_context_off()  # 설정 "" → 본문 그대로, describe가 불리면 실패
def test_ingest_texts_prepend_when_on()  # 설정 "gpt-6-luna" → ["설명\n본문"], describe가 받은 spec == ContextSpec("gpt-6-luna", "low")
def test_chunk_context_settings_from_env(monkeypatch)  # 없음 → "" · "low", 값 있으면 그 값(get_settings 캐시 비우기)
def test_production_has_chunk_context_off()  # PRODUCTION 두 키 값, 설정 "gpt-6-luna"면 differences에 chunk_context_model
```

- [ ] **Step 2:** `.venv/Scripts/python -m pytest -q tests/ingest tests/core tests/evaluation` → 새 테스트 FAIL 확인 → 테스트 커밋. 이번에 쓸 스킬: test-driven-development
- [ ] **Step 3:** 구현(위 Interfaces). 요청문 파일은 Task 0에서 넣은 것을 그대로 쓴다(고치지 않음). `ingest/__main__.py`는 `models = {m["id"]: m for m in load_models()}`, `embed_texts(ingest_texts(doc, chunks_src, get_settings(), models))`, 저장은 지금처럼 원문 `(page, text)`. `.gitignore`에 `data/chunk_context/`, `.env.example`에 `CHUNK_CONTEXT_MODEL=`(빈 값, "비면 조각 설명을 쓰지 않음(지금 운영)") 한 줄
- [ ] **Step 4:** `.venv/Scripts/python -m pytest -q -m "not integration"` 전부 PASS → 구현 커밋. `prompt_sha256()` 값을 보고에 적는다(결정기록 037 값과 같아야 함)

### Task 2: 실험 벌·시간 쌍·판정지 (측정 코드, AI 비용 0)

**Files:** Create `measure/chunk_context.py`, `tests/measure/test_chunk_context.py`. Modify `measure/emb_large.py`, `measure/v17_bundle.py`, `measure/stage2.py`, `measure/v17_blind4.py`, 해당 테스트

**Interfaces:**
- Consumes: Task 1 `ContextItem`·`context_items`·`describe_all`·`embedding_input`·`CANDIDATE_CONTEXT`·`DESC_PATH`·`MAX_OUTPUT_TOKENS`; `emb_large.EmbedSpec`·`production_chunks`·`text_mismatches`·`rank_buckets`
- Produces (`measure/v17_bundle.py`): `SAME_TEXT_BUNDLES = frozenset({"emb_large", "ctx_small"})` — 운영과 번호·글이 같고 임베딩만 다른 벌. `test_v17_bundle.py`의 두 통합 테스트가 `BUNDLE_EMBED` 대신 이것을 본다
- Produces (`measure/emb_large.py`): `store_reembedded(name, chunks, spec, *, conn, embed=None, inputs: list[str] | None = None) -> int` — `inputs`가 있으면(길이가 조각 수와 같아야 함) 그것을 임베딩하고 저장 본문은 `c.content`. `measure(out_name: str = "emb-stage1", bundle: str = BUNDLE)` — 지금 동작 그대로, 잴 벌만 인자로
- Produces (`measure/chunk_context.py`):
  - `BUNDLE = "ctx_small"`, `SMALL = EmbedSpec("text-embedding-3-small", None)`, `OUT = ROOT/"measure"/"out"/"chunk-context"`, `SAMPLE_SEED = 20261121`, `PRICE_SMALL_PER_CHAR = 2e-8`
  - `production_items(conn, docs: list[dict], models: dict[str, dict]) -> list[tuple[BundleChunk, ContextItem]]` — 운영 조각(id 순)을 문서별로 다시 자른 조각과 `(page, content)` 순서대로 짝짓는다. 문서별로 하나라도 다르거나, DB에만·파일에만 있는 문서가 있으면 멈춤(메시지에는 문서 id와 수만)
  - `estimate_describe(items: list[ContextItem]) -> dict` — `{"items", "input_chars", "cost_usd"}`, 비용 = (`build_prompt` 글자 합) × `PRICE_IN`/1e6 + 조각 수 × `MAX_OUTPUT_TOKENS` × `PRICE_OUT`/1e6(상한 어림)
  - `unsupported_tokens(description: str, item: ContextItem) -> list[str]` — 설명 속 숫자·영문·코드 토큰(`re.findall(r"[0-9A-Za-z]+(?:[.,][0-9]+)?", 설명)`) 중 글·조각·문서 이름을 이은 글에 부분 문자열로 없는 것(대소문자 무시, 중복 제거·나온 순서)
  - `sample_items(pairs, n: int = 20, seed: int = SAMPLE_SEED) -> list[int]`(조각 id) 
  - `store_contextual(conn, pairs, descriptions: list[str]) -> int` — 빈 설명이 있거나 수가 다르면 멈춤. `store_reembedded(BUNDLE, chunks, SMALL, conn=conn, inputs=[embedding_input(d, c.content) ...])`
- Produces (`measure/stage2.py`): `RULE_033`(평가-규칙.md "덧붙임 판정 규칙" 1~4를 옮긴 글, `BLIND_HEADER`와 `v17_blind4` 머리말에 들어감), `paired_latency(rows: list[dict], base: str, cand: str, min_pairs: int = 10) -> dict` — `{"pairs", "pair_diff_ms", "all_diff_ms", "basis": "pairs"|"all", "diff_ms", "pass"}`. 짝 = 같은 `run`·같은 `id`에 두 방법 모두 `found` 참·`rule_blocked` 거짓·`latency_ms` 있음. `all_diff_ms` = 후보 전체 평균 − 운영 전체 평균(`summarize_methods`와 같은 제외). `"True"`/`"False"`·숫자 글자도 읽음. `pass` = `diff_ms <= 500`

- [ ] **Step 1: 실패하는 테스트**

```python
def test_same_text_registry():
    assert set(BUNDLE_EMBED) <= SAME_TEXT_BUNDLES and chunk_context.BUNDLE in SAME_TEXT_BUNDLES
def test_embed_for_ctx_bundle_is_production():
    assert embed_for("ctx_small", base) is base
def test_store_reembedded_embeds_inputs_but_stores_content()  # embed가 받은 글 == inputs, INSERT의 content == 원문
def test_store_reembedded_refuses_inputs_length_mismatch()
def test_production_items_pairs_by_doc_in_id_order()
def test_production_items_refuses_text_mismatch()  # 메시지에 본문 글자가 없음
def test_store_contextual_refuses_missing_description()
def test_estimate_describe_upper_bound()
def test_unsupported_tokens_flags_new_number_and_code()  # 글에 없는 "60"·"E5"는 걸리고, 글에 있는 "5C"는 안 걸림
def test_sample_items_is_seeded_and_20()
def test_paired_latency_only_both_found_same_run()
def test_paired_latency_pools_two_runs()
def test_paired_latency_falls_back_to_all_under_10_pairs()
def test_paired_latency_excludes_rule_blocked()
def test_paired_latency_reads_csv_strings()  # found "True"/"False", latency_ms "1234"/"", rule_blocked "False"
def test_blind_headers_have_033_rule()  # BLIND_HEADER와 v17_blind4 머리말에 "일반적인 안전 주의"와 "버튼·기능·코스 이름"
```

- [ ] **Step 2:** 새 테스트 FAIL 확인 → 테스트 커밋
- [ ] **Step 3:** 구현. CLI `python -m measure.chunk_context`:
  - `estimate`: `production_items`(DB 읽기만, 원본 파일과 짝 확인) → 조각 수·글자 수·설명 비용 어림·small 임베딩 비용(설명 150자 가정 + 본문 글자 × `2e-8`)
  - `describe`: `describe_all(..., CANDIDATE_CONTEXT)` → 수, 빈 0·150자 초과 0, 2회 부른 조각 수, 입력·출력 토큰 합과 실제 비용, 설명 길이(최소·평균·최대), 파일 SHA-256, `unsupported_tokens`에 걸린 조각 수. 설명 글은 출력하지 않는다
  - `sample`: `OUT/"sample-20.md"`(표본 20개 + `unsupported_tokens`에 걸린 조각: 조각 id·문서·쪽·글·조각·설명·걸린 토큰). git 밖, 게시하지 않는다
  - `store`(설명이 하나라도 빠지면 멈춤) / `verify`(`text_mismatches == []`) / `measure [--out 폴더]`(`emb_large.measure(out, bundle=BUNDLE)`)
  - `latency <r1 CSV> <r2 CSV>`: 두 CSV를 `run`=파일 이름으로 합쳐 `summarize_methods`와 `paired_latency(rows, "m0", BUNDLE)`를 출력
  - `check-ingest`(Task 6에서 씀): `get_settings()`의 설명 설정이 `CANDIDATE_CONTEXT`와 다르면 멈춤 → 문서마다 `chunks_with_sources` → `ingest_texts(..., get_settings(), ..., describe=partial(describe_all, allow_new=False))`가 같은 설명 파일로 `store`가 만든 입력(`production_items` 순서의 `embedding_input`)과 글자까지 같은지, 새로 쓸 설명 0개인지. AI 호출·DB 쓰기 없음
- [ ] **Step 4:** `pytest -q -m "not integration"` 전부 PASS → 구현 커밋 → 브랜치 PR·병합(사용자 확인, requesting-code-review) → 운영 `/api/health`

### Task 3: 0단계·1단계 (설명·임베딩 비용)

- [ ] **Step 1:** 잔액(사용자가 결제 화면 확인) → `python -m measure.chunk_context estimate`(짝 확인이 멈추면 원인을 확인하기 전에 진행하지 않음) → 장부에 설명 쓰기 행·임베딩 행·1단계 행(질문 45개 small) → `check_budget` 결과를 리포트에
- [ ] **Step 2:** `describe` → 위 출력 그대로 리포트에. 빠진 조각이 있으면 멈추고 보고(다시 돌릴지는 사용자). 실제 비용이 예상의 2배를 넘으면 멈춤
- [ ] **Step 3 (멈춤, 채팅 Claude):** `sample` → 사용자가 `measure/out/chunk-context` 폴더를 Cowork에 연결(채팅 Claude 가이드) → 채팅 Claude가 표본 20개를 글과 대조. 자동 검사(`unsupported_tokens`)에 걸린 표본 밖 조각도 같은 방식으로 대조한다(사용자 결정 2026-11-20). 원문에 없는 숫자·절차·버튼·기능 이름이 하나라도 있으면 멈추고 사용자가 정한다(요청문을 고쳐 v2로 한 번 더, 또는 미완료). 대조 결과(수·조각 id)를 리포트에
- [ ] **Step 4:** `store` → `verify`(어긋남 0) → 넣은 행 332 → `measure --out ctx-stage1`(운영 1~20위가 `fable-stage1`과 같음) → `measure.fable_split.b1_pass(summary, "ctx_small")`
- [ ] **Step 5:** 리포트 "1단계": 5위 안 표(개발용·30문항), 순위 구간, 순위가 바뀐 문장(id·순위만), 029 M1(개발용 +2)·v1.9 large(8 → 14)와 나란히. B-1 실패면 미채택 → Task 7. 통과면 Task 4. 커밋(메시지 먼저)

### Task 4: 3단계 (답변까지, 개발용 21문장)

- [ ] **Step 1:** 장부(21문장 × 2벌 × 2회 + 5C 3회) → `check_budget`
- [ ] **Step 2:** `python -m measure.stage2 evaluation/paraphrase_dev.csv --methods m0 ctx_small --label ctx-s3-r1`, 같은 명령 `--label ctx-s3-r2`. 5C: v1.9의 `measure/out/emb-large/5c.csv`를 `measure/out/chunk-context/5c.csv`로 복사해 `--methods ctx_small --label ctx-s3-5c` → `found` 3회 모두 true인지 센다
- [ ] **Step 3:** `python -m measure.chunk_context latency <r1> <r2>` → 시간 쌍 수·쌍 평균 차이·전체 평균 차이·판정 근거(쌍/전체)·비용 비율을 리포트에(사람 판정 전 자동 값)
- [ ] **Step 4:** `python -m measure.stage2 <r1> <r2> --blind --label ctx-s3` → 머리말에 033 규칙이 있는지 확인 → 대응표 해시를 판정 전에 커밋. 결과 CSV는 판정이 끝날 때까지 커밋하지 않는다
- [ ] **Step 5 (멈춤, 사용자 판정):** 채팅 Claude가 v1.9와 같은 클릭 판정 화면("덧붙임" 칸 포함)을 만든다. 사용자가 전부 판정
- [ ] **Step 6:** 대응표 공개 → ⑰ → B-2(정답 +3 이상·환각 0, 비용 1.5배 이하, Step 3의 시간 판정, 5C 3/3). 경계 판정을 뒤집었을 때 결론이 바뀌는지 적는다. 032 다시 볼 조건(설명서에 없는 코드에 다른 코드의 절차를 붙인 환각)은 따로 적고 사용자에게 알린다
- [ ] **Step 7:** B-2 통과면 `measure/out/chunk-context/stage3-pass.json`(날짜·판정 요약·대응표 해시) → Task 5. 실패면 미채택 → Task 7

### Task 5: 4단계 (확인용 세트, 3단계를 통과했을 때만)

**Files:** Create `measure/stage4.py`, `tests/measure/test_stage4.py`. Modify `measure/stage2.py`

**Interfaces:** Fable 계획 Task 8 Interfaces 그대로(`old_chunk_refs_to_pages`, `load_backup_pages`, `run_followups_same_run`), 다른 점: `STAGE3_PASS = ROOT/"measure"/"out"/"chunk-context"/"stage3-pass.json"`을 `measure/stage4.py`에 두고, `stage2.py`의 `--open-test-set`이 이 파일이 있을 때만 연다. `emb_large.measure(out_name, bundle, test_set: Path | None = None)`와 `chunk_context measure --test-set 파일`을 더한다: 같은 파일이 있을 때만 그 확인용 파일 하나를 재고(운영·후보 5위 안), 운영 순위 대조는 건너뜀

- [ ] **Step 1:** 테스트 먼저: `test_old_manual_chunk_ref_becomes_page`, `test_guide_and_page_refs_unchanged`, `test_stage2_refuses_test_set_without_pass_file`, `test_measure_refuses_test_set_without_pass_file`, `test_followups_same_run_alternates_methods` → 커밋 → 구현 → 커밋(3단계 판정을 기다리는 동안 해도 된다. 확인용 파일은 열지 않는다)
- [ ] **Step 2:** 확인용 세트 준비: v1.9 계획 Task 5 Step 2 그대로
- [ ] **Step 3:** 장부 → `python -m measure.chunk_context measure --out ctx-stage4 --test-set <합친 파일>` → 한 실행 안에서 운영·후보 각 2회: 확인용·30문항 `stage2 --methods m0 ctx_small`(확인용은 `--open-test-set`), 이어지는 질문 `run_followups_same_run(["m0", "ctx_small"], ...)` → 시간은 `latency`로
- [ ] **Step 4 (멈춤, 판정):** v1.9 계획 Task 5 Step 4 그대로(확인용은 사용자가 전부, 회귀는 ⑳, 판정지에 033 규칙). 대응표 해시는 판정 전에 커밋
- [ ] **Step 5:** B-3 → 결론(설계 6절). 채택이고 11/23 밤 안이면 Task 6, 아니면 "채택 후보"로 Task 7

### Task 6: 운영 반영 (채택됐을 때만, 11/24)

**Files:** Create `measure/emb_rollout.py`, `tests/measure/test_emb_rollout.py`. Modify `.env`(로컬, 커밋 안 함), `.env.example`, `evaluation/run_config.py`, `docs/결정기록/015-최종-설정.md`(덧붙임), `docs/superpowers/specs/2026-11-17-phase2-model-request-design.md`(덧붙임)

**Interfaces:** v1.9 계획 Task 6 Interfaces 그대로(`backup_embeddings`, `load_backup`, `vectors_from_bundle`, `swap_embeddings`). CLI `python -m measure.emb_rollout backup|swap|restore --bundle ctx_small --backup measure/out/chunk-context/rollout-backup/chunks-embeddings.jsonl`

- [ ] **Step 1:** 테스트 먼저: `test_backup_refuses_existing_file`, `test_backup_roundtrip`, `test_vectors_from_bundle_refuses_text_mismatch`, `test_swap_refuses_when_rowcount_differs` → 커밋 → 구현 → 커밋
- [ ] **Step 2:** `backup` → 행 수 332·해시, 백업 한 행을 읽어 운영과 대조. `vectors_from_bundle(conn, "ctx_small")`(글이 같을 때만, 비용 0)
- [ ] **Step 3 (사용자 확인 뒤):** `swap`(332행, 다르면 전체 되돌림) → `/api/health`, 5C 질문 1회(장부 먼저). 환경 변수·다시 배포는 하지 않는다(설계 8절 1)
- [ ] **Step 4:** 로컬 `.env`에 `CHUNK_CONTEXT_MODEL=gpt-6-luna`, `run_config.PRODUCTION`을 `"gpt-6-luna"`·`"low"`로, `.env.example` 설명 → `warn_if_different`가 아무것도 알리지 않음 → `python -m measure.chunk_context check-ingest`(새로 쓸 설명 0, 입력 332개 글자까지 같음) → 결정기록 015에 최종 설정 바뀜 덧붙임
- [ ] **Step 5:** 장부 → `python -m evaluation --label ctx-rollout-r1`·`-r2` → 사용자가 전부 판정(⑰, 합격선 24/30 이상·환각 0). 미달·오류면 사용자 확인 뒤 `restore` → `/api/health` → `.env`·`PRODUCTION` 되돌림 → 보고
- [ ] **Step 6:** 2차 설계 덧붙임(설계 8절 7): 채팅 Claude 초안 → 사용자 확인 → 문서 끝에 "덧붙임 (v1.95 반영)" 절로 넣는다(기존 글은 고치지 않음)

### Task 7: 결론 기록

- [ ] **Step 1:** 리포트 "정리"(결과·비용·한계·다음 후보), 결정기록 038(결론: 채택/미채택/채택 후보/미완료와 근거), 개발일지, AI 실수 기록(누가 했는지 구분)
- [ ] **Step 2:** 최종 검토 서브에이전트(requesting-code-review, 확인용 세트 파일·`data/chunk_context/`·`measure/out/chunk-context/sample-20.md` 읽기 금지를 요청문에) → 지적 목록을 고치기 전에 보고(측정·판정에 닿는 지적은 사용자 결정)
- [ ] **Step 3:** verification-before-completion → 커밋 → push·PR·병합(사용자 확인). `bundle_chunks`의 `ctx_small`을 지울지는 사용자에게 묻는다. 노션(v1.95 단계 선택지 추가·타임라인·도구 비교 모음)과 인수인계 노트는 채팅 Claude
