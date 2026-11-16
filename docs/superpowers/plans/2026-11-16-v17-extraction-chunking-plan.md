# 펴봄 v1.7 검색·PDF 추출 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설명서 PDF 추출 도구를 비교하고 소제목 단위 자르기와 쪽 표시 지우기를 측정해, 설계 7절 기준을 통과한 것만 운영에 반영할 근거를 만든다.

**Architecture:** 순수 함수 세 개(쪽 표시 지우기·마크다운 기호 지우기·소제목 자르기)는 `ingest/`에 두되 운영 적재 경로에는 연결하지 않는다. 추출 도구는 도구별 가상환경에서 돌려 쪽별 JSON으로 저장한다. 실험 조각은 운영 `chunks`와 따로 저장하고, 기존 측정 도구(`measure/search_eval.py`·`measure/stage2.py`)에 실험 조각 이름을 받는 인자를 더해 같은 실행 안에서 비교한다.

**Tech Stack:** Python, pypdfium2(지금), 후보 도구 5개, Neon(pgvector), OpenAI 임베딩·답변, pytest

**Spec:** `docs/superpowers/specs/2026-11-16-v17-extraction-chunking-design.md` (이 계획은 설계 문서의 절 번호로 근거를 댄다. 실행 전에 둘 다 읽는다)

## Global Constraints

- 운영 표(`chunks`)와 운영 적재·검색·답변 경로는 바꾸지 않는다. 표를 새로 만들거나 구조를 바꾸면 실행 전에 사용자 확인(CLAUDE.md)
- 판단 기준은 설계 7절 그대로 쓰고, 결과를 본 뒤 바꾸지 않는다. 계획에 없는 판정 규칙이 필요하면 집계 전에 멈추고 묻는다(평가 규칙)
- 확인용 세트(`evaluation/paraphrase_test.csv`와 새 응답의 확인용 10카드 문장)는 Task 11의 여는 조건 전까지 검색·채점하지 않고, 문장 내용을 출력하지 않는다
- 평가 세트의 기대 근거는 고치지 않는다(설계 5절 4)
- 장부: v1.7 리포트 안, `check_budget(rows, new, cap_usd=2.0)` 통과 뒤 실행. 상한 안이라도 잔액이 1달러 아래로 내려갈 실행은 하지 않는다. 멈춤: `check_budget` 실패, 실제 비용이 그 행 예상의 2배 초과, 원인 모를 오류
- 추출 결과·조각 글은 git 제외(`measure/out/v17/`). 리포트에는 위치·글자 수·있다/없다만
- 추출 도구는 `requirements.txt`(Vercel)에도 `requirements-dev.txt`에도 넣지 않는다. 도구마다 따로 가상환경(git 제외)을 쓰고 버전을 기록한다. 파이썬 버전이 맞지 않으면 그 가상환경만 다른 버전을 써도 되고, 쓴 버전을 기록한다
- 라이선스로 거르지 않고 기록만 한다(코드·모델 따로)
- 일정: 목표 11/24. 도구 하나의 설치·첫 실행 시도 1시간, 설명서 하나 처리 30분까지
- 개인정보 시험 값은 누가 봐도 가짜인 값만, 테스터 이름은 어디에도 적지 않는다
- 새 규칙·새 이름(기록에 계속 쓸 용어)은 사용자에게 먼저 묻는다. PR·브랜치·파일·코드 식별자 이름은 보고에만 적는다. 리포트에서 실험 조각 한 벌의 이름은 "운영 그대로", "쪽 표시만 지운 것", "<도구> 800자", "<도구> 소제목"처럼 풀어 쓴다

## Review Focus

1. 도구가 빈 쪽을 건너뛰거나 표지를 0쪽으로 세서 쪽 수는 같은데 번호가 밀림 → 근거 "N쪽"이 틀린다. 쪽 맞춤 검사로 잡는다(Task 4 `test_page_alignment_detects_shift`)
2. 쪽 표시 지우기가 본문 숫자를 지움(4쪽 "36 °C", "155 ml", 쪽 맨 앞 목록 번호) → 남겨야 한다(Task 2 테스트)
3. 마크다운 기호 지우기가 모델명·숫자를 망가뜨림("WD90H25AH*/WD90H25BH*"의 `*`, "4.0 kg", "1/2", "220 V/60 Hz") → 그대로여야 한다(Task 3 테스트)
4. 실험 조각에서 가이드 조각의 번호나 본문이 달라짐 → `chunk:299`·`chunk:300` 기대 근거가 깨진다(Task 5 `test_guide_chunks_identical_to_production`)
5. 실험 조각으로 답할 때 운영 조각 본문이 답변 AI에 들어감 → 실험이 무효가 된다(Task 9 `test_bundle_content_reaches_prompt`)

---

### Task 1: 설계·계획 커밋과 측정 전 준비 (내용을 보지 않음)

**Files:**
- Add: 설계 문서(Spec 경로), 이 계획(`docs/superpowers/plans/2026-11-16-v17-extraction-chunking-plan.md`)
- Create: `docs/평가/v17-extraction.md`(리포트), `docs/결정기록/031-v17-확인용-세트와-측정-전-결정.md`, `measure/v17_count.py`, `tests/measure/test_v17_count.py`
- Modify: `docs/평가/v16-not-found.md`(사용량 대조 한 줄), 개발일지 2026-11-16, `docs/AI-실수-기록.md`

**Interfaces:**
- Produces: `count_new_responses(csv_path: Path, cutoff: datetime, dev_cards: set[int], test_cards: set[int]) -> dict[str, int]` — 키는 `"dev"`, `"test"`, `"other"`(카드 번호를 알 수 없는 것), `"blank"`

- [ ] **Step 1: 실패하는 테스트**

```python
def test_counts_only_numbers(tmp_path, capsys):
    # 가짜 응답 3줄: 기존(11/09)·새 개발용 카드·새 확인용 카드
    result = count_new_responses(csv, cutoff=..., dev_cards={1}, test_cards={2})
    assert result == {"dev": 1, "test": 1, "other": 0, "blank": 0}
    assert "가짜문장" not in capsys.readouterr().out  # 문장 내용을 출력하지 않음
```

- [ ] **Step 2:** 실행해서 실패 확인 → `pytest tests/measure/test_v17_count.py -v`
- [ ] **Step 3:** `measure/v17_count.py` 구현. 새 응답 구분 기준(응답 시각 등)과 카드 번호 읽는 법은 `measure/out/p-set-responses.csv`의 열 이름만 보고 정한다. 개발용·확인용 카드 번호는 `evaluation/paraphrase_dev.csv`·`evaluation/paraphrase_split.json`에서 읽는다(확인용 파일 본문은 읽지 않는다)
- [ ] **Step 4:** 테스트 통과 확인. 실제 파일로 실행해 숫자만 보고한다
- [ ] **Step 5:** `evaluation/paraphrase_test.csv`의 해시가 `evaluation/paraphrase_split.json`과 같은지 기존 테스트(`tests/evaluation/test_paraphrase_set.py`)로 확인
- [ ] **Step 6:** 리포트 뼈대 작성: 설계 7절 기준을 그대로 옮긴 "판단 기준" 절, 장부 표(상한 2달러, 잔액 US$2.61·2026-11-16 사용자 화면), 단계별 빈 절
- [ ] **Step 7:** 결정기록 031: 확인용 세트 구성과 029 규칙 변경 이유(설계 5절 3), 확인용 여는 조건(5절 6), 기대 근거 유지(5절 4), 라이선스 기록만(5절 7), 장부 상한 2달러
- [ ] **Step 8:** v1.6 리포트 장부 아래에 덧붙임: 11/16(UTC) OpenAI 사용량 입력 276,274·출력 14,649토큰, 리포트 2·3단계 토큰 합(입력 256,374·출력 13,414)과 맞고 남는 차이는 4단계와 질문 바꾸기 몫으로 봄, 달러 금액은 대조하지 않음. 개발일지에 PR #67 병합 커밋 31b21fc와 운영 배포 상태(인수인계 노트의 남은 기록). AI 실수 기록 한 줄: 2026-11-16 · 채팅 Claude · v1.7 설계·계획 초안에서 새 이름 두 개(마크다운 기호 지우기, 실험 조각 한 벌을 가리키는 줄임말)를 묻지 않고 씀 → 계획 넘기기 전 채팅 Claude가 밝히고, 사용자 결정으로 풀어 쓰기로 고침
- [ ] **Step 9:** 전체 테스트 → 커밋 → PR → 사용자 확인 후 병합

### Task 2: 쪽 표시 지우기 (순수 함수)

**Files:** Create `ingest/page_marker.py`, `tests/ingest/test_page_marker.py`

**Interfaces:**
- Produces:
  - `strip_page_marker(text: str, page: int, *, check_tail: bool = False) -> tuple[str, list[str]]` — 지운 뒤 글과 지운 글자 목록. 운영 적재(`ingest/clean.py`)에는 연결하지 않는다
  - `count_remaining_markers(text: str, page: int) -> int` — 쪽 글 전체에서 "자기 쪽 번호만 있는 줄"과 "한국어 N"·"N 한국어"의 수(설계 6절 확인 방법)

규칙은 설계 6절 1단계 "쪽 표시 지우기": 앞 20자 안에서 자기 쪽 번호 N이 앞뒤 숫자 없이 처음 나오는 자리(붙은 "한국어" 포함)와 바로 뒤 공백 또는 줄바꿈 하나(`\r\n`은 하나로 본다). 본문을 지우지 않도록, N(또는 "한국어 N"·"N 한국어")은 앞이 글 시작·공백·줄바꿈이고 뒤가 공백·줄바꿈·글 끝일 때만 쪽 표시로 본다(채팅 Claude 계획 단계 보완, 지우는 범위를 좁히는 쪽). `check_tail=True`이면 끝 20자에서 같은 방법으로 찾고 바로 앞 공백 또는 줄바꿈 하나를 함께 지운다.

- [ ] **Step 1: 실패하는 테스트**

```python
def test_samsung_odd(): assert strip_page_marker("한국어 55\n5. 부드러운 솔", 55) == ("5. 부드러운 솔", ["한국어 55\n"])
def test_samsung_crlf(): assert strip_page_marker("한국어 7\r\n 세탁물이", 7) == (" 세탁물이", ["한국어 7\r\n"])
def test_samsung_even_after_chapter():
    assert strip_page_marker("제품 사용 방법\n36 한국어\n AI 맞춤+", 36) == ("제품 사용 방법\n AI 맞춤+", ["36 한국어\n"])
def test_lg_space(): assert strip_page_marker("12 사용 전에", 12) == ("사용 전에", ["12 "])
def test_lg_newline(): assert strip_page_marker("12\n사용 전에", 12) == ("사용 전에", ["12\n"])
def test_other_number_kept(): t = "• 36 °C 이상 고온"; assert strip_page_marker(t, 4) == (t, [])
def test_digit_neighbors_kept(): t = "155 ml 이하"; assert strip_page_marker(t, 55) == (t, [])
def test_list_number_kept(): t = "1. 세탁물을 분류하세요."; assert strip_page_marker(t, 1) == (t, [])
def test_beyond_20_kept(): t = "가" * 25 + "\n55"; assert strip_page_marker(t, 55) == (t, [])
def test_tail(): assert strip_page_marker("본문 끝\n55", 55, check_tail=True) == ("본문 끝", ["\n55"])
def test_tail_off_by_default(): t = "본문 끝\n55"; assert strip_page_marker(t, 55) == (t, [])
def test_count_remaining(): assert count_remaining_markers("본문\n55\n더\n한국어 55 끝", 55) == 2
def test_count_ignores_other_numbers(): assert count_remaining_markers("55 ml\n155", 55) == 0
```

- [ ] **Step 2:** 실패 확인 → `pytest tests/ingest/test_page_marker.py -v`
- [ ] **Step 3:** `ingest/page_marker.py` 구현
- [ ] **Step 4:** 통과 확인
- [ ] **Step 5:** 지금 DB의 설명서 조각 대신 pypdfium2 쪽 글(지금 `ingest/pdf.py` + `ingest/clean.py` 결과)에 돌려, 지운 글자 목록 전체를 `measure/out/v17/page_marker/`에 저장하고, 리포트에는 설명서별 지운 쪽 수와 지운 글자 모양 종류만 적는다. v1.6 셈법(`measure/v16_not_found.py`)으로 다시 세면 쪽 표시 0개인지 확인
- [ ] **Step 6:** 커밋

### Task 3: 마크다운 기호 지우기 (순수 함수)

**Files:** Create `ingest/plaintext.py`, `tests/ingest/test_plaintext.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class PlainPage: text: str; headings: list[tuple[int, str]]` (제목 줄이 시작하는 글자 위치, 제목 글자), `markdown_to_plain(md: str) -> PlainPage`

규칙은 설계 6절 1단계 "마크다운 기호 지우기". 굵게는 `**…**` 짝만 지운다(홑 `*`는 모델명에 쓰이므로 건드리지 않는다). 목록 기호 `-`·`•`는 원문에도 있으므로 남긴다. 표 칸 구분은 공백 한 칸.

- [ ] **Step 1: 실패하는 테스트**

```python
def test_heading():
    p = markdown_to_plain("## 쾌속\n일상 세탁물을 빠르게")
    assert (p.text, p.headings) == ("쾌속\n일상 세탁물을 빠르게", [(0, "쾌속")])
def test_table():
    md = "| 설정 | 온도 (°C) |\n|---|---|\n| 선택 가능 | 냉수 / 20 / 30 |"
    assert markdown_to_plain(md).text == "설정 온도 (°C)\n선택 가능 냉수 / 20 / 30"
def test_bold_image_comment(): assert markdown_to_plain("**주의** ![](a.png)<!-- image -->내용").text == "주의 내용"
def test_model_star_kept(): assert markdown_to_plain("WD90H25AH*/WD90H25BH*").text == "WD90H25AH*/WD90H25BH*"
def test_numbers_kept(): t = "최대 용량: 4.0 kg, 1/2, 220 V/60 Hz"; assert markdown_to_plain(t).text == t
def test_list_kept(): assert markdown_to_plain("- 세탁물을 분류하세요.").text == "- 세탁물을 분류하세요."
def test_heading_offsets_after_table():  # 표 줄이 바뀐 뒤에도 제목 위치가 평문 기준인지
    p = markdown_to_plain("| a | b |\n|---|---|\n# 미세플라스틱저감\n본문")
    assert p.text[p.headings[0][0]:].startswith("미세플라스틱저감")
```

- [ ] **Step 2–4:** 실패 확인 → 구현 → 통과 (`pytest tests/ingest/test_plaintext.py -v`)
- [ ] **Step 5:** 커밋. 이 규칙은 Task 6(1단계 측정) 전에 고정하고 이후 바꾸지 않는다(설계 11절)

### Task 4: 0단계 — 탈락 검사 함수와 도구 실행

**Files:**
- Create: `measure/v17_gate.py`, `tests/measure/test_v17_gate.py`, `experiments/v17_extract/README.md`, `experiments/v17_extract/run_<도구>.py`(도구마다 하나), `measure/v17_toc.json`(목차 목록, 쪽 번호와 항목 글자만)
- 출력(git 제외): `measure/out/v17/extract/<도구>/<문서 id>.json` = `[{"page": int, "markdown": str}]`

**Interfaces:**
- Consumes: `markdown_to_plain`(Task 3)
- Produces (`measure/v17_gate.py`):
  - `Pages = list[tuple[int, str]]` (쪽 번호, 평문)
  - `page_count_ok(tool: Pages, base: Pages) -> bool`
  - `page_alignment(tool: Pages, base: Pages) -> float` — base 쪽에서 그 설명서에 한 번만 나오는 15자 이상 줄을 하나씩 골라, 도구의 같은 쪽 글에 있는 비율(그런 줄이 있는 쪽만 셈). 0.9 미만이면 탈락 조건 2
  - `decimal_ok(samsung: Pages) -> bool` — 38쪽에 "4.0 kg" 있음, "4 0 kg" 없음
  - `table_rows_ok(lg_drum: Pages) -> bool` — 16쪽에 `40\s+15\s+30`, `50\s+20\s+35`, `60\s+25\s+45`가 이 순서로 있음
  - `broken_lines(pages: Pages) -> int` — `(cid:`이 있는 줄 + 깨진 글자 판정 줄(판정 글자 집합은 이 Task에서 테스트로 고정하고 pypdfium2에 먼저 센 뒤 바꾸지 않는다)
  - `char_ratio(tool: Pages, base: Pages) -> float` — 공백 뺀 글자 수 비율, 0.9 미만이면 탈락 조건 6
  - `heading_hit_rate(headings: dict[int, list[str]], toc: list[tuple[int, str]]) -> float` — 공백을 뺀 글자로 한쪽이 다른 쪽을 포함하면 맞음(같은 쪽만)

- [ ] **Step 1: 실패하는 테스트** (작은 가짜 쪽 데이터)
  - `test_page_alignment_detects_shift`: base 3쪽, 도구가 2쪽을 비우고 4쪽을 덧붙여 쪽 수는 같지만 번호가 밀림 → `page_alignment < 0.9`
  - `test_decimal_ok`: "최대 용량: 4.0 kg" → True, "4 0 kg" 섞이면 False
  - `test_table_rows_ok`: 세 행 순서대로 → True, 행 섞임("40 50 60 …") → False
  - `test_char_ratio`, `test_heading_hit_rate`("세제함 사용하기" 목차 26쪽 ↔ 26쪽 제목 "세제함 사용하기" 맞음, 27쪽이면 틀림)
  - `test_broken_lines`: `(cid:12)` 줄 1개 + 정상 한글 줄 → 1
- [ ] **Step 2–4:** 실패 확인 → 구현 → 통과
- [ ] **Step 5: 목차 목록** — 세 설명서의 목차 쪽 글(pypdfium2)로 `measure/v17_toc.json` 초안을 만든다(목차 쪽이 없는 설명서는 비움). **멈춤: 채팅 Claude가 원문과 대조**한 결과를 받아 고친 뒤 커밋한다
- [ ] **Step 6: 도구 실행** — 후보마다(PyMuPDF4LLM, Docling, Marker, MinerU, OpenDataLoader PDF) 따로 가상환경 → 설치 → 세 설명서 실행. 여러 쪽을 이어 붙이는 도구는 한 쪽짜리 PDF로 나눠 돌린다. 기본 설정으로 돌리고 바꾼 옵션은 기록. 기록: 버전, 라이선스(코드·모델, 공식 저장소나 PyPI 기준), 설치 시간, 설명서별 실행 시간, 쓴 파이썬 버전. 설치 1시간·설명서 30분을 넘으면 제외하고 이유를 적는다. 기준인 pypdfium2는 지금 `ingest/pdf.py` 결과를 같은 JSON 모양으로 저장
- [ ] **Step 7: 판정** — `python -m measure.v17_gate`로 도구마다 탈락 조건 1~6과 설명서별 제목 잡기 비율을 리포트 0단계 표에 적는다(통과 도구, 탈락 도구와 이유, "제목을 잡는 도구" 여부)
- [ ] **Step 8: 멈춤: 채팅 Claude 원문 대조** — 통과 도구의 평문(쪽 표시 지우기 전)을 삼성 7·38쪽, LG 드럼 16·55쪽, LG 에어컨 "고장 신고 전 확인" 쪽만 `measure/out/v17/review/`에 쪽별 파일로 저장하고, 사용자에게 그 폴더 읽기 권한을 요청한다. 대조 결과(2단 표 칸 섞임 등)를 리포트에 옮긴다(탈락 조건 아님)
- [ ] **Step 9:** 커밋

### Task 5: 실험 조각 저장과 검색

**Files:** Create `measure/v17_bundle.py`, `tests/measure/test_v17_bundle.py`. Modify: 검색 함수(지금 `search_vector(..., variant=...)`가 있는 파일)

**Interfaces:**
- Consumes: `strip_page_marker`(Task 2), `markdown_to_plain`(Task 3), `ingest.chunk.chunk_pages`
- Produces:
  - `@dataclass class BundleChunk: id: int; doc_id: str; page: int | None; content: str`
  - `build_bundle(name: str, manual_pages: dict[str, list[tuple[int, PlainPage]]], chunker: Callable[[list[tuple[int, PlainPage]]], list[tuple[int, str]]]) -> list[BundleChunk]` — 설명서 조각 + 운영 가이드 조각(번호·본문 그대로). 설명서 조각 번호는 운영 번호와 겹치지 않게
  - 800자 자르기용 `chunk_plain_800(pages: list[tuple[int, PlainPage]]) -> list[tuple[int, str]]` = `chunk_pages([(p, pp.text) for p, pp in pages], max_chars=800, overlap=100)`. pypdfium2 글은 `PlainPage(text, [])`로 감싼다
  - `store_bundle(name: str, chunks: list[BundleChunk], *, apply: bool) -> int` — 임베딩해 실험 저장소에 넣음. `apply=False`면 글자 수로 예상 비용만 계산
  - 검색: 실험 조각 이름을 받으면 그 한 벌의 조각(번호·쪽·본문)을 돌려준다. 이름이 없으면 지금과 똑같이 동작
- [ ] **Step 1: 저장소 확인 (멈춤 가능)** — `measure/chunk_variants.sql`과 `chunk_variants`가 경계·본문이 다른 조각을 담을 수 있는지 확인한다. 안 되면 새 표 설계안(열, 인덱스, 지우는 방법)을 보고하고 **사용자 확인 뒤** 만든다
- [ ] **Step 2: 실패하는 테스트**
  - `test_guide_chunks_identical_to_production`: 실험 조각 한 벌의 가이드 조각 번호·본문이 운영과 같음(299·300 포함)
  - `test_manual_chunks_stay_in_page`: 모든 설명서 조각의 본문이 그 쪽 평문의 부분 글자이고 쪽 번호가 원래 쪽
  - `test_bundle_ids_do_not_collide`: 설명서 조각 번호가 운영 번호와 겹치지 않음
  - `test_default_search_unchanged`: 실험 조각 이름 없이 부르면 기존 검색 테스트 결과 그대로(기존 통합 테스트 재사용)
- [ ] **Step 3–4:** 구현 → 통과(통합 테스트는 장부에 임베딩 몇 회를 적고 실행)
- [ ] **Step 5:** 커밋

### Task 6: 1단계 측정과 판정 (검색만)

**Files:** Modify `measure/search_eval.py`(실험 조각 이름 인자), 리포트

- [ ] **Step 1:** 실험 조각 만들기(`apply=False`로 예상 비용 계산): "쪽 표시만 지운 것"(pypdfium2 + `strip_page_marker` → `chunk_plain_800`), 0단계 통과 도구마다 "<도구> 800자"(`markdown_to_plain` → `strip_page_marker(check_tail=True)` → `chunk_plain_800`). 도구별 `count_remaining_markers` 합계를 기록
- [ ] **Step 2:** 장부에 행 추가 → `check_budget` → `store_bundle(apply=True)` → 실제 비용 기록
- [ ] **Step 3:** 같은 실행 안에서 "운영 그대로"와 모든 실험 조각을 `evaluation/paraphrase_dev.csv`·`evaluation/questions.csv`로 잰다(`.settings.json`에 실험 조각 이름, 확인용은 재지 않음)
- [ ] **Step 4:** 리포트 1단계 표: 실험 조각 한 벌마다 개발용 P 5위 안(분모 20)·30문항 5위 안(분모 25), 도구별 남은 쪽 표시 수. 판정: A-1("쪽 표시만 지운 것" vs 운영), "<도구> 800자" 각각 B-1 통과 여부, 2단계에 쓸 도구(제목을 잡는 도구 중 개발용 최고, 차이 1문장 이내면 단순·빠른 쪽)
- [ ] **Step 5:** 커밋. **멈춤: 사용자에게 1단계 결과 보고**

### Task 7: 소제목 자르기 (순수 함수)

**Files:** Create `ingest/section_chunk.py`, `tests/ingest/test_section_chunk.py`

**Interfaces:**
- Consumes: `PlainPage`(Task 3), `ingest.chunk.chunk_pages`
- Produces: `chunk_sections(pages: list[tuple[int, PlainPage]], max_chars: int = 800, overlap: int = 100, min_chars: int = 100) -> list[tuple[int, str]]`

규칙은 설계 6절 2단계. 첫 제목 앞의 글(앞 쪽에서 이어진 글)도 한 절로 본다. 100자 미만 절은 같은 쪽의 다음 절과 합치고, 다음 절이 없으면 앞 절과 합치며, 쪽에 절이 하나뿐이면 그대로 둔다.

- [ ] **Step 1: 실패하는 테스트**
  - `test_new_chunk_at_each_heading`: 한 쪽에 제목 2개(각 300자) → 조각 2개, 각 조각이 제목 글자로 시작
  - `test_text_before_first_heading_is_section`: 제목 앞 200자 → 별도 조각
  - `test_no_page_crossing`: 절이 다음 쪽으로 이어지면 다음 쪽 글은 새 조각, 쪽 번호 +1
  - `test_long_section_split`: 1,900자 절 → `chunk_pages(800, 100)`과 같은 결과
  - `test_short_section_merged_with_next` / `test_short_last_section_merged_with_previous` / `test_single_short_section_kept`
  - `test_no_added_text`: 모든 조각이 그 쪽 평문의 부분 글자
- [ ] **Step 2–4:** 실패 확인 → 구현 → 통과
- [ ] **Step 5:** 커밋. 숫자(800·100·100)는 이후 바꾸지 않는다

### Task 8: 2단계 측정과 최종 후보 (검색만)

- [ ] **Step 1:** Task 6에서 고른 도구로 "<도구> 소제목" 실험 조각(`chunk_sections`) → 장부 → 저장. 제목을 잡는 도구가 없으면 이 Step은 건너뛰고 이유를 리포트에 적는다
- [ ] **Step 2:** 같은 실행 안에서 운영 그대로, 쪽 표시만 지운 것, 1단계 최고 도구 800자, 소제목 실험 조각을 잰다
- [ ] **Step 3:** 리포트 2단계 표와 판정: 후보 둘의 B-1, 최종 후보(설계 6절 2단계 "최종 후보 고르기"), 최종 후보의 A-1(운영 그대로와 비교). 통과 후보가 없으면 "도구·자르기 미채택"을 적고 Task 9의 최종 후보 관련 Step은 건너뛴다
- [ ] **Step 4:** 커밋. **멈춤: 사용자에게 보고**

### Task 9: 실험 조각으로 답하기 (측정 도구 확장)

**Files:** Modify `measure/stage2.py`(또는 새 `measure/v17_answer.py`), 이어지는 질문 실행 코드. Test: `tests/measure/test_v17_answer.py`

**Interfaces:**
- Consumes: Task 5의 실험 조각 검색
- Produces: 서비스 흐름(개인정보 가리기 → 질문 바꾸기 → 검색 → 답변 → 검증)을 실험 조각 이름으로 돌리는 함수. 결과에 실험 조각 이름, 받은 조각 번호, 원래 출력, 최종, 토큰, 시간

- [ ] **Step 1: 실패하는 테스트** (가짜 LLM)
  - `test_bundle_content_reaches_prompt`: 실험 조각 본문이 프롬프트의 `<chunk>`에 들어가고 운영 본문은 들어가지 않음
  - `test_quote_checked_against_bundle_content`: 인용 검사가 실험 조각 본문 기준
  - `test_default_path_unchanged`: 실험 조각 이름 없이 부르면 기존 결과 그대로
  - `test_followup_turn_uses_bundle`: 이어지는 질문 턴도 바꾼 질문으로 같은 실험 조각을 검색하고 그 본문으로 답함
- [ ] **Step 2–4:** 실패 확인 → 구현 → 통과
- [ ] **Step 5:** 커밋 → PR → 코드 검토(requesting-code-review) → 사용자 확인 후 병합

### Task 10: 3단계 (답변까지, 개발용 21문장)

- [ ] **Step 1:** 장부(21문장 × 실험 조각 벌 수 × 2회 + 5C 6회) → `check_budget`
- [ ] **Step 2:** 같은 실행 안에서 운영 그대로, 쪽 표시만 지운 것, (있으면) 최종 후보로 개발용 21문장. 5C: "물이 안 빠지고 5C가 떠요"(washer-samsung-wd90h25, 앞 대화 없음, 바꾸기 포함)를 쪽 표시만 지운 것과 최종 후보에서 각 3회
- [ ] **Step 3:** 가린 판정지(`--blind`), 대응표는 git 밖, SHA-256 해시(LF 기준)를 판정 전에 커밋
- [ ] **Step 4: 멈춤: 사용자 판정** (판정 기준은 평가 규칙 "사람 판정"과 검색 개선 계획 Task 7의 판정 방법 그대로)
- [ ] **Step 5:** 판정 받은 뒤 대응표 공개, 리포트 3단계 표: A-2·A-3(3단계 부분)은 "쪽 표시만 지운 것"과 최종 후보를 각각 운영 그대로와 비교, B-2는 최종 후보를 "쪽 표시만 지운 것"과 비교(정답 +3문장 이상·환각 0·질문당 비용 1.5배 이하·응답 시간 증가 0.5초 이하), 경계 판정 민감도
- [ ] **Step 6:** 커밋. **멈춤: 사용자에게 보고하고 Task 11의 갈래 확인**

### Task 11: 4단계 또는 회귀 실행

여는 조건은 설계 6절 4단계: 최종 후보가 B-2를 통과했을 때만 확인용 세트를 연다.

**갈래 가 — 확인용을 여는 경우**
- [ ] **Step 1:** 새 응답자 3명의 확인용 10카드 문장 정리(중복·동의·개인정보는 검색 개선 계획 Task 1 Step 1 규칙), 카드의 11/10 기대 근거를 붙임
- [ ] **Step 2: 멈춤** — 카드와 다른 것을 묻는 문장 후보를 `measure/out/v17/confirm-review.md`(git 제외)에 적고, 채팅 Claude가 원문으로 확인(답 없음 → 함정, 다른 쪽에 답 → 제외 후보), 사용자가 확정
- [ ] **Step 3:** 지난 20문장 해시 확인 → 합친 파일과 새 해시 커밋
- [ ] **Step 4:** 장부 → 같은 실행 안에서 3벌 × (확인용 + 30문항 + 이어지는 질문 31턴)
- [ ] **Step 5:** 가린 판정지·해시 커밋 → **멈춤: 사용자 판정** → A-3(4단계 포함), B-3, "둘을 합쳐 정하는 법"(설계 7절)으로 결론

**갈래 나 — 확인용을 열지 않는 경우**
- [ ] **Step 1:** 장부 → 같은 실행 안에서 운영 그대로·쪽 표시만 지운 것 × (30문항 + 이어지는 질문 31턴)
- [ ] **Step 2:** 가린 판정지·해시 커밋 → **멈춤: 사용자 판정** → A-3으로 쪽 표시 지우기 결론. 확인용 세트는 봉인 그대로

**공통:** 11/24까지 끝내지 못하면 설계 8절 "일정"대로 끝낸 단계까지 기록하고 멈춘다.

### Task 12: 결론 기록

- [ ] **Step 1:** 결정기록 032(v1.7 결론): 채택·미채택·미완료, 기준별 결과, 한계(p22-2·p15-2 관찰, 11/10 확인용 문장을 본 일, AGPL 도구가 이겼다면 그 사실)
- [ ] **Step 2:** 리포트 맨 위 "정리", 개발일지, AI 실수 기록(누가 했는지 구분)
- [ ] **Step 3:** 채택한 것이 있으면 운영 반영 계획(적재 코드, 운영 `chunks` 다시 넣기, 조각 번호 변경의 영향: 평가 세트 `chunk:<번호>`, 실험 표, 브라우저 저장 대화)을 먼저 보고하고 **사용자 확인 뒤** 별도 계획으로 진행
- [ ] **Step 4:** 계획 전체 최종 검토(서브에이전트) → 커밋 → PR → 사용자 확인 후 병합

## 계획 보완 (2026-11-16, 사용자 결정)

이유: Task 2·3 작업과 브랜치 전체 검토에서 찾은 계획 안 어긋남(Task 2 테스트끼리 충돌, 마크다운 기호 지우기가 설계보다 좁음, 쪽 표시를 지운 뒤 제목 위치가 밀림)을 사용자가 2026-11-16에 정함.

- ① 끝 20자 검사는 앞에서 지운 것이 없을 때만 한다(설계 6절 보완, 지우는 범위를 좁힘). 앞·끝에서 지운 수를 따로 기록한다(Task 6 실행 도구에서: `check_tail=False`로 먼저 불러 지웠으면 앞, 못 지웠으면 `check_tail=True` 결과로 끝을 센다 — Claude Code 판단). 테스트: `check_tail=True`에서 앞과 끝 모두에 쪽 번호가 있으면 앞만 지운다.
- ② 쪽 표시를 지운 뒤 제목 위치를 맞춰 주는 함수 `strip_plain_page(pp: PlainPage, page: int, *, check_tail: bool = False) -> tuple[PlainPage, list[str]]`를 `ingest/page_marker.py`에 더한다(이름·모양은 Claude Code가 정함). 지운 구간과 글자 범위가 겹치는 제목(지운 자리 안에서 시작하는 제목 포함)은 버리고, 지운 구간 뒤 제목은 지운 길이만큼 당긴다. 테스트: 지운 뒤 남은 모든 제목에 대해 `text[위치:]`가 그 제목 글자로 시작하고, 지운 자리 안에서 시작하는 제목은 버린다. Task 7 전까지만 있으면 된다(Task 6 "<도구> 800자"와 Task 8 소제목 실험 조각이 이 함수를 쓴다).
- ③ Task 4 Step 6(도구 실행) 뒤, Step 7(판정) 전에 새 단계: 도구별로 `markdown_to_plain` 출력에 남은 기호를 숫자로만 센다 — 백슬래시 escape(`\` 뒤 기호), HTML 태그 이름별, 마크다운 링크 `](`, 홑 `*` 또는 `_`로 감싼 글 후보. 내용은 출력하지 않는다. 0이 아니면 멈추고 보고한다(정리 규칙은 사용자·채팅 Claude가 정한 뒤 테스트로 고정하고 판정).
- ④ 제목 적중(heading_hit_rate)의 "포함" 판정을 좁힌다(사용자 결정, Step 7 전·도구 출력 보기 전). 공백을 지운 뒤 한쪽이 다른 쪽에 들어 있고, 짧은 쪽이 2자 이상이며 긴 쪽 길이의 절반 이상일 때만 맞다(같은 쪽 조건은 그대로). 테스트: 목차 "경고"↔제목 "경고" 맞음, 목차 "제품을 설치할 때"↔제목 "설치"·"때" 틀림.
- ⑤ 삼성 38쪽 소수점 검사(decimal_ok)는 "4.0"과 "kg" 사이 공백이 0개 이상이어도 통과한다(사용자 결정, Step 7 전·도구 출력 보기 전). "4 0 kg" 모양 검사는 그대로. 테스트: "4.0kg"·"4.0  kg"·"4.0 kg" 통과.
- ⑥ GPU(사용자 결정, 측정 결과 보기 전): CPU로 먼저 돌리고, CPU에서 설명서 하나에 30분을 넘긴 도구만 같은 설정(같은 백엔드·옵션, 장치만 GPU)으로 RTX 4070에서 다시 돌린다. GPU용 설치도 1시간 제한 안. GPU로 통과한 도구는 "GPU 필요"로 기록하고, 그 도구가 이기면 결정기록에 "적재가 이 컴퓨터 GPU에 의존"을 적는다. 설계 탈락 조건 1은 "이 컴퓨터에서 돌릴 수 있어야 함"으로 읽는다. 코드: Step 7 기본 모드가 run.json의 `gpu_required`를 표에 "GPU 필요"로 보여 주고, 조건 1의 30분 넘음은 마지막으로 돈 장치의 `run_seconds` 기준이다(`excluded`가 true여도 조건 1).
- ⑦ 도구 쪽 글에도 운영과 같은 `clean_text`를 적용한다(사용자 결정, 측정 결과 보기 전). 순서: markdown_to_plain → clean_text → (쪽 표시 지우기). 0단계 판정(조건 2·5·6, 제목 잡기)과 1단계 모두 같은 순서. `--leftover` 셈은 ③ 그대로 markdown_to_plain 결과에 센다. 제목 위치 처리(R22, Claude Code 판단): `ingest/plaintext.py`의 `clean_plain_page`가 줄마다 clean_text를 적용해 결과 text가 `clean_text(pp.text)`와 같고, 지워진 줄의 제목은 버리고 남은 제목은 새 줄 시작 위치로 옮기며 깨끗해진 줄이 제목 글자로 시작하지 않으면 버린다.
- ⑧ 후보에 Unstructured(오픈소스 `unstructured` 라이브러리, `partition_pdf`)를 더하고 다른 도구 뒤 맨 마지막 차례로 돌린다(사용자 결정 2026-11-16, 측정 결과 보기 전). `strategy="hi_res"`로 지정한다(화면 배치 모델로 제목·표를 나누는 것이 넣는 이유라서). 기본값 auto가 아니라는 것을 "바꾼 옵션"으로 기록하고 그 밖의 옵션은 기본값. 제목은 요소 종류 Title, 쪽 번호는 요소의 쪽 정보(실제로 나오는지 먼저 확인하고, 안 나오면 기록한 뒤 한 쪽짜리 PDF로 나눠 돌림). 탈락 조건·설치 1시간·실행 30분·⑥ GPU·⑦ clean_text 순서는 다른 도구와 같다. 라이선스(코드·모델)를 기록한다. 장부 1단계 실험 조각은 최대 7벌(예상 +0.01달러). Claude Code 판단: Unstructured 요소를 마크다운으로 바꾸는 법은 Title 요소는 "# " + 글, 나머지 요소는 글 그대로 한 줄씩(표도 글, HTML 표는 쓰지 않음), 쪽마다 요소 순서대로 잇는다(다른 도구와 같은 markdown_to_plain을 쓰려고).
- ⑨ `markdown_to_plain`을 보완한다. 모든 도구에 똑같이 적용하고, Step 7 판정 전에 테스트로 고정한다(사용자 결정 2026-11-16, 남은 기호 숫자만 보고 판정 결과는 보기 전).
  1) HTML 표는 `<tr>`마다 한 줄로 만든다. `<td>`·`<th>` 칸은 공백 한 칸으로 잇고 빈 칸은 건너뛴다. `<table>`·`<thead>`·`<tbody>`와 닫는 태그는 지운다.
  2) `<br>`·`<br/>`·`<br />`는 공백 한 칸으로 바꾼다.
  3) `<img …>` 태그는 통째로 지운다(base64 포함).
  4) 그 밖의 HTML 태그는 태그만 지우고 안의 글자는 남긴다. 태그로 보는 조건은 "<" 바로 뒤가 영문자 또는 "/"+영문자이고, 같은 줄에서 ">"로 닫히는 것이다.
  5) 마크다운 링크 `[글](주소)`는 글만 남긴다. 취소선 `~~글~~`도 글만 남긴다.
  6) 백슬래시 뒤가 ASCII 문장부호이면 백슬래시만 지운다. 다른 규칙을 모두 적용한 뒤 맨 마지막에 한다. 백슬래시 뒤가 영문자(LaTeX 명령)이면 그대로 둔다.
  7) 홑 `*`·`_`로 감싼 글은 지우지 않는다.
  - 테스트 값 11개는 사용자 지시 그대로 쓴다.
  - ⑨를 적용한 뒤 ③을 다시 센다. 종류는 다음과 같다.
    - (가) 닫힌 HTML 태그, (나) 백슬래시+문장부호, (다) 링크, (라) 취소선.
    - 기록만 하는 종류: (마) 홑 `*`·`_` 감싸기, (바) 백슬래시+영문자, (사) 닫히지 않은 "<".
  - (가)~(라)가 모두 0이면 Step 7(판정)과 Step 8까지 하고 멈춘다. 0이 아니면 숫자만 보고하고 멈춘다.
  - 탈락 조건 2·5·6과 제목 잡기는 ⑨·⑦을 적용한 글로 센다(base64가 글자 수에 들어가지 않게).
  - Claude Code 판단: 처리 순서와 셈 패턴.
    - 순서: 주석 → `<img>` → `<br>` → 표 블록 → 그 밖 태그 → 줄 단위(이미지·표 줄·제목·굵게·링크·취소선) → 백슬래시. 백슬래시는 그 줄의 마지막에 처리한다.
    - 통째로 지운 줄은 기존 이미지처럼 공백을 정리하고, 비면 줄째 버린다.
    - 셈 패턴은 ⑨ 정의와 같다.
- ⑩ MinerU 기본 층(standard)은 탈락 조건 1로 기록한다. 이 컴퓨터에서 LG 드럼(FX25) 실행 오류가 두 번 났고, 원인은 확인하지 못했다. basic 층을 MinerU 후보로 세고, "바꾼 옵션 `--tier basic`"과 이유(기본 층이 CPU에서 30분을 넘고 GPU에서도 LG 드럼 실패)를 기록하며, 같은 탈락 검사를 받는다(사용자 결정 2026-11-16).
