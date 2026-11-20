# 펴봄 Fable 분할 실험 + MinerU 기본 층 다시 하기 — 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fable 5.2가 채팅에서 정한 자를 위치(줄 번호 분할·PDF 분할)와 MinerU 기본 층(GPU)으로 만든 실험 조각이 지금 운영보다 검색·답을 낫게 하는지, 측정 전에 정한 기준(설계 6절)으로 판정한다.

**Architecture:** Fable은 사용자가 채팅에서 돌리고(AI 비용 0), 코드는 Fable 답(위치만)을 읽어 운영과 같은 쪽 글에 자를 위치를 붙인 뒤 v1.7의 `chunk_sections`로 자른다. 실험 조각은 v1.7 `bundle_chunks`·`measure.v17_stage1`·`measure.stage2`를 그대로 써서 저장·측정한다. 새 코드는 `measure/fable_split.py` 하나에 모은다.

**Tech Stack:** Python 3.14, pytest, Neon Postgres + pgvector(`bundle_chunks`), OpenAI 임베딩·답변(기존 코드), MinerU 4.2.2(GPU, 별도 가상환경)

**Spec:** `docs/superpowers/specs/2026-11-19-fable-split-design.md` (사용자 승인 2026-11-20). 실행하는 사람은 설계와 이 계획을 함께 읽는다.

## Global Constraints

- 채택 기준 숫자는 설계 6절 그대로, 측정 전 확정. 결과를 본 뒤 바꾸지 않는다(B-1: 개발용 P 5위 안 +3 이상(분모 20) 그리고 30문항 5위 안 1문항 넘게 안 떨어짐 / B-2: 개발용 사람 판정 +3 이상(분모 21)·환각 0·질문당 비용 1.5배 이하·응답 시간 +0.5초 이하·5C 3회 모두 `found` true / B-3: 확인용 5위 안 +10%p·정답 더 많음·환각 0, 30문항 2문항 넘게 안 떨어짐·환각 0, 이어지는 질문 1턴 넘게 안 떨어짐·환각 0)
- 비교 기준점은 운영 `chunks`(측정 코드의 `None` = production). 기록용: `strip_800`, `docling_sections`
- 탈락: Fable 두 방법 모두 설명서 하나라도 버린 위치(형식 어긋남 + 없는 줄/못 찾음) / 받은 위치 > 0.10이면 탈락
- 최종 후보 순서: `fable_lines` → `fable_pdf` → `mineru_800` (최고값에서 1문장 이내 중 앞 순서)
- 마감: `fable_pdf`·MinerU는 2026-11-21 저녁까지 실험 조각이 없으면 "미완료". 11/24까지 4단계를 못 끝내면 "미완료", 확인용 봉인 유지
- OpenAI 장부 상한 1달러(`check_budget(rows, new, cap_usd=1.0)`), 운영 잔액 1달러 이상, 실행 전 장부와 `check_budget` 결과를 리포트에 적는다
- 설명서 글·줄 번호 파일·Fable 답 원문·조각 글은 `measure/out/fable/`(git 밖)에만. 리포트에는 수·위치·있다/없다만
- 확인용 세트(`evaluation/paraphrase_test.csv`)는 4단계 전에 열지 않는다. 검토 서브에이전트 요청문에도 이 금지를 적는다
- 운영 `chunks`는 읽기만. `bundle_chunks`에 넣는 것은 행 추가이며, 지우기·표 구조 변경은 사용자 확인 뒤
- 실험 조각 코드 이름(보고에만): `fable_lines`(Fable 줄 번호 분할), `fable_pdf`(Fable PDF 분할), `mineru_800`(MinerU 800자). 기록 문장에는 사용자 결정 이름을 쓴다
- Fable 답을 읽는 규칙(`parse_*`, `normalize_alnum`, `locate_start`의 `key_len=12`·`min_len=4`)은 Task 1에서 Fable 답을 받기 전에 커밋해 고정한다. 답을 본 뒤 고치지 않는다. 고쳐야 한다고 보이면 멈추고, 고치기 전 숫자를 남긴 채 사용자가 명시적 예외로 정할지 결정한다(설계 5-3의 3)
- 유료 실행 중 측정 코드를 고치지 않는다. 멈출 때: `check_budget` 실패, 실제 비용 > 그 행 예상의 2배, 원인 모를 오류
- CLAUDE.md 규칙 그대로: 테스트 먼저 커밋, 커밋 메시지는 먼저 보여 주기, push·PR·병합 직전 사용자 확인, 모델 Opus·high(원인 모를 문제만 ultrathink)

## Review Focus

1. 사용자가 붙여 넣은 Fable 답에 코드 블록이 여러 개(“계속” 뒤 이어진 답)·같은 위치 중복·순서 뒤섞임이 있음 → 모든 블록을 합쳐 읽고 중복은 한 번만, 쪽·위치 순으로 쓴다 (Task 1 `test_parse_joins_blocks_dedups_and_sorts`)
2. 붙여 넣은 파일의 줄 끝이 `\r\n`이거나 항목 앞뒤에 공백·설명 글이 붙음 → 형식에 맞는 항목만 읽고 나머지는 "형식 어긋남"으로 센다(멈추지 않음) (Task 1 `test_parse_counts_bad_lines_and_handles_crlf`)
3. 줄 번호 파일을 만든 글과 자를 위치를 계산하는 글이 달라짐(쪽 표시 지우기 등이 그사이 바뀜) → 위치가 엉뚱한 곳을 가리키기 전에 멈춘다 (Task 2 `test_cuts_refuse_when_text_hash_differs`)
4. Fable PDF 분할이 준 쪽 번호가 범위 밖이거나 첫 글자가 너무 짧음(정리 뒤 4자 미만) → "못 찾음"으로 세고 멈추지 않는다 (Task 1 `test_locate_out_of_range_page_and_short_key`)
5. Fable 답에 읽을 수 있는 항목이 하나도 없음 → 탈락이 아니라 "답 전체를 읽을 수 없음"으로 멈춰 다시 돌리기 대상으로 보고한다 (Task 1 `test_zero_items_is_unreadable`)

## 파일 구조

- Create `measure/fable_split.py` — 줄 번호 파일 만들기, Fable 답 읽기, 자를 위치 계산, 탈락 판정, 최종 후보 고르기, API 환산. CLI `python -m measure.fable_split lines|cuts <한 벌>|pick <summary.json>`
- Create `tests/measure/test_fable_split.py`
- Modify `measure/v17_stage1.py` — `BUNDLES`에 `fable_lines`·`fable_pdf`(Task 2), `mineru_800`(Task 3, 거르기 통과 때만)
- Modify `measure/stage2.py` — 4단계 확인용 세트 열기(Task 8, 3단계 통과 때만)
- Create `measure/fable_stage4.py`, `tests/measure/test_fable_stage4.py` — 4단계 같은 실행 안 실행과 옛 조각 번호 바꾸기(Task 8)
- Create `measure/recount_032.py`, `tests/measure/test_recount_032.py` — 032 다시 세기(Task 9)
- git 밖: `measure/out/fable/{input,answers/<한 벌>,cuts,5c.csv,runs.json}`, `measure/out/v17/extract/mineru-gpu/`
- 문서: `docs/superpowers/specs/2026-11-19-fable-split-design.md`, 이 계획, `docs/결정기록/033-fable-분할-측정-전-결정.md`, `docs/평가/fable-split.md`, `docs/평가/평가-규칙.md`, 개발일지, `docs/AI-실수-기록.md`

## 브랜치

| 브랜치 | Task |
|---|---|
| `docs/fable-split-plan` | Task 0 |
| `feat/fable-split-tools` | Task 1~3 |
| `feat/fable-split-measure` | Task 4~8, Task 10 |
| `feat/recount-032` | Task 9 |

---

### Task 0: 설계·계획·측정 전 결정 커밋 (AI 비용 0)

**Files:** Create 설계·계획(프로젝트 지식에서 그대로 복사), `docs/결정기록/033-fable-분할-측정-전-결정.md`, `docs/평가/fable-split.md`. Modify `docs/평가/평가-규칙.md`, `docs/개발일지/2026-11-20.md`, `docs/AI-실수-기록.md`

- [ ] **Step 1:** 설계와 이 계획을 저장소에 넣는다(사용자가 프로젝트 지식 파일을 전달).
- [ ] **Step 2:** 결정기록 033: 설계 5-6 덧붙임 규칙, 두 방법 이름(Fable 줄 번호 분할·Fable PDF 분할)과 탈락 조건(5-2의 4·5-3의 4), 확인용 옛 조각 번호를 모든 벌에서 쪽으로 세기(6절 4단계), 032 다시 볼 조건이 켜졌고 Fable 뒤로 미룸(7절), 7절 다시 셀 범위. 모두 "사용자 결정 2026-11-19·20"과 출처 절을 단다.
- [ ] **Step 3:** `평가-규칙.md` "사람 판정"에 설계 5-6의 1~4를 그대로 덧붙인다(기존 줄은 지우지 않음, 2026-11-20 사용자 결정 표시). (정정 2026-11-20: 덧붙임 규칙 결정일은 2026-11-19, 설계 5-6. 채팅 Claude가 계획에 날짜를 잘못 적음)
- [ ] **Step 4:** `docs/평가/fable-split.md`: 맨 위 "판단 기준(측정 전 확정)"에 설계 6절 B-1·B-2·B-3·최종 후보·탈락·마감을 옮기고, "장부(상한 1달러)" 표를 만든다(설계 8절 예상 4행).
- [ ] **Step 5:** 개발일지 2026-11-20(PR #74·#75 링크 포함, 인수인계 노트의 "다음 브랜치에서" 항목). AI 실수(채팅 Claude, 2026-11-19): "채팅으로 나누면 이겨도 적재 코드에 그대로 못 넣는다"고 말함 → 자를 위치를 파일로 저장하면 지금 설명서 3개는 재현 가능해 틀림(같은 대화에서 정정).
- [ ] **Step 6:** 커밋 → push·PR·병합(사용자 확인).

### Task 1: Fable 답 읽기와 자를 위치 (순수 함수)

**Files:** Create `measure/fable_split.py`, `tests/measure/test_fable_split.py`

**Interfaces:**
- Consumes: `ingest.plaintext.PlainPage(text, headings)`, `ingest.section_chunk.chunk_sections`
- Produces:
  - `numbered_lines(pages: list[tuple[int, PlainPage]]) -> tuple[str, dict[tuple[int, int], int]]` — (파일 글, (쪽, 줄) → 쪽 글 안 시작 위치). 쪽 글을 `"\n"`으로 나눈 줄 중 공백뿐이 아닌 줄만 쪽마다 1부터 번호. 파일 한 줄 = `f"{page}:{n}\t{line}"`
  - `text_hash(pages: list[tuple[int, PlainPage]]) -> str` — 쪽 글 전체의 SHA-256(쪽 순서대로 `f"{page}\n{text}\n"`를 이어 붙임)
  - `@dataclass Parsed: items: list; received: int; bad_format: int`
  - `parse_line_answer(text: str) -> Parsed` — 줄 끝 `\r\n`을 `\n`으로 바꾼 뒤, 모든 ```` ``` ```` 코드 블록(여는 줄의 언어 표시는 무시, 닫히지 않은 마지막 블록은 글 끝까지) 안의 공백 아닌 줄을 받은 항목으로 센다. 코드 블록 밖 글은 세지 않는다. `^\s*(\d+)\s*:\s*(\d+)\s*$`이면 `(쪽, 줄)`, 아니면 형식 어긋남. 중복 제거 후 정렬
  - `parse_pdf_answer(text: str) -> Parsed` — 같은 규칙, 형식 `^\s*(\d+)\s*\|\s*(\S.*?)\s*$` → `(쪽, 첫 글자)`
  - `normalize_alnum(s: str) -> str` — `unicodedata.normalize("NFKC", s)` 뒤 `[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]`만 남김
  - `locate_start(page_text: str, start: str, key_len: int = 12, min_len: int = 4) -> int | None` — `normalize_alnum(start)`의 앞 `key_len`자(정리 뒤 `min_len`자 미만이면 None)를 정리한 쪽 글에서 처음 찾은 자리를 원래 쪽 글 위치로 돌려줌
  - `cuts_from_lines(index: dict[tuple[int, int], int], items: list[tuple[int, int]]) -> tuple[dict[int, list[int]], int]` — (쪽 → 위치 목록, 없는 줄 수)
  - `cuts_from_pdf(pages: list[tuple[int, PlainPage]], items: list[tuple[int, str]]) -> tuple[dict[int, list[int]], int]` — (쪽 → 위치 목록, 못 찾음 수). 없는 쪽 번호도 못 찾음
  - `with_cuts(pages: list[tuple[int, PlainPage]], cuts: dict[int, list[int]]) -> list[tuple[int, PlainPage]]` — 각 쪽 `PlainPage(text, [(off, "") for off in sorted(set(cuts.get(page, [])))])`
  - `dropped_ratio(parsed: Parsed, missing: int) -> float` — `(bad_format + missing) / received`; `received == 0`이면 `ValueError("답 전체를 읽을 수 없음")`
  - `ELIMINATE_OVER = 0.10`

- [ ] **Step 1: 실패하는 테스트**

```python
def test_numbered_lines_skips_blank_and_maps_offsets():
    pp = PlainPage("가나\n\n  \n다라마", [])
    text, idx = numbered_lines([(3, pp)])
    assert text.splitlines() == ["3:1\t가나", "3:2\t다라마"]
    assert idx == {(3, 1): 0, (3, 2): pp.text.index("다라마")}

def test_parse_joins_blocks_dedups_and_sorts():
    ans = "앞말\n```text\n5:3\n4:2\n```\n중간\n```\n5:3\n4:7\n```"
    p = parse_line_answer(ans)
    assert p.items == [(4, 2), (4, 7), (5, 3)] and p.received == 4 and p.bad_format == 0

def test_parse_counts_bad_lines_and_handles_crlf():
    p = parse_line_answer("```\r\n5:3\r\n5:3-7\r\n12쪽 4줄\r\n```")
    assert p.items == [(5, 3)] and p.received == 3 and p.bad_format == 2
    q = parse_pdf_answer("```\n7 | 세탁물의 무게와 종류\n7 세탁물\n```")
    assert q.items == [(7, "세탁물의 무게와 종류")] and q.bad_format == 1

def test_locate_ignores_symbols_spacing_and_fullwidth():
    t = "※ 참고\n• 최대 용량: 9.0 kg\n쾌속 일상 세탁물을"
    assert locate_start(t, "쾌속 일상 세탁물을") == t.index("쾌속")
    assert locate_start(t, "최대용량９") == t.index("최대")

def test_locate_out_of_range_page_and_short_key():
    pages = [(1, PlainPage("첫 쪽 글입니다", []))]
    cuts, missing = cuts_from_pdf(pages, [(9, "첫 쪽 글입니"), (1, "첫"), (1, "첫 쪽 글입니다")])
    assert cuts == {1: [0]} and missing == 2

def test_cuts_from_lines_counts_missing():
    _, idx = numbered_lines([(1, PlainPage("가\n나", []))])
    cuts, missing = cuts_from_lines(idx, [(1, 2), (1, 9), (8, 1)])
    assert cuts == {1: [2]} and missing == 2

def test_with_cuts_feeds_chunk_sections():
    pp = PlainPage("가" * 150 + "\n" + "나" * 150, [])
    out = chunk_sections(with_cuts([(1, pp)], {1: [151]}))
    assert [t[:1] for _, t in out] == ["가", "나"]

def test_unclosed_last_block_reads_to_end():
    p = parse_line_answer("```text\n3:1\n```\n```\n4:2\n4:5")
    assert p.items == [(3, 1), (4, 2), (4, 5)] and p.received == 3

def test_zero_items_is_unreadable():
    with pytest.raises(ValueError):
        dropped_ratio(parse_line_answer("설명만 있음"), 0)

def test_dropped_ratio_counts_bad_and_missing():
    assert dropped_ratio(Parsed(items=[(1, 1)] * 9, received=10, bad_format=1), 1) == 0.2
```

- [ ] **Step 2:** `.venv/Scripts/python -m pytest tests/measure/test_fable_split.py -v` → 모두 FAIL(모듈 없음) → `test(measure): Fable 답 읽기 테스트 추가 (실패 확인)` 커밋
- [ ] **Step 3:** 위 Interfaces대로 구현. `locate_start`는 정리한 글자마다 원래 위치를 담은 목록을 함께 만들어 되돌린다.
- [ ] **Step 4:** 같은 명령 → PASS, `-m "not integration"` 전체 PASS → `feat(measure): Fable 답 읽기와 자를 위치` 커밋

### Task 2: 줄 번호 파일·자를 위치 파일·실험 조각 등록 (AI 비용 0)

**Files:** Modify `measure/fable_split.py`, `measure/v17_stage1.py`, `tests/measure/test_fable_split.py`, `tests/measure/test_v17_stage1.py`

**Interfaces:**
- Consumes: Task 1 전부, `measure.v17_gate.EXTRACT·DOCS·_load`, `measure.v17_bundle.manual_pages_from_pypdfium2`
- Produces:
  - `FABLE = ROOT / "measure" / "out" / "fable"`
  - `base_pages(root: Path = EXTRACT) -> dict[str, list[tuple[int, PlainPage]]]` — `manual_pages_from_pypdfium2({d: _load(root / "pypdfium2", d) for d in DOCS})` (운영·`strip_800`과 같은 글)
  - `write_lines(out: Path = FABLE / "input") -> dict` — 설명서마다 `<doc_id>-lines.txt`와 `meta.json`(`{doc_id: {"text_hash", "pages", "lines", "chars"}}`), 글자는 출력하지 않음
  - `build_cuts(bundle: Literal["fable_lines", "fable_pdf"], answers: Path = FABLE / "answers", out: Path = FABLE / "cuts") -> dict` — `answers/<bundle>/<doc_id>.md`를 읽어 `cuts/<bundle>.json` = `{"cuts": {doc: {page: [off]}}, "stats": {doc: {"received", "bad_format", "missing", "ratio"}}, "eliminated": bool, "text_hash": {doc: hash}}`. 지금 `base_pages()`의 `text_hash`가 `input/meta.json`과 다르면 멈춤
  - `fable_pages(bundle: str) -> Callable[[dict], dict]` — `v17_stage1.BUNDLES`의 두 번째 자리. raw → `manual_pages_from_pypdfium2(raw)` → `cuts/<bundle>.json`으로 `with_cuts`. `eliminated`가 true면 멈춤
  - `v17_stage1.BUNDLES["fable_lines"] = ("pypdfium2", fable_pages("fable_lines"), chunk_sections)`, `["fable_pdf"]`도 같은 꼴

- [ ] **Step 1: 실패하는 테스트**
  - `test_cuts_refuse_when_text_hash_differs(tmp_path)`: `meta.json`의 해시를 바꿔 두면 `build_cuts`가 `SystemExit`
  - `test_build_cuts_marks_eliminated_over_10_percent(tmp_path)`: 한 설명서에서 받은 10개 중 2개가 없는 줄이면 `eliminated is True`, 1개면 False
  - `test_fable_bundles_use_pypdfium2_and_chunk_sections()`: `s1.BUNDLES["fable_lines"][0] == "pypdfium2"`, `[2] is chunk_sections`
  - `test_fable_pages_stops_when_eliminated(tmp_path)`
- [ ] **Step 2:** FAIL 확인 → 테스트 커밋
- [ ] **Step 3:** 구현. CLI `python -m measure.fable_split lines`는 `write_lines`, `cuts <한 벌>`은 `build_cuts` 뒤 stats와 `eliminated`만 출력
- [ ] **Step 4:** PASS 확인 → 구현 커밋
- (덧붙임 2026-11-20, 사용자 결정) `fable_pages`도 cuts 파일의 `text_hash`와 지금 쪽 글 해시를 대조해 다르면 멈춘다. 테스트 `test_fable_pages_stops_when_text_hash_differs` 먼저 커밋 → 구현 커밋
- [ ] **Step 5:** `python -m measure.fable_split lines` 실행 → 설명서별 쪽·줄·글자 수를 리포트 "0단계"에 적는다(파일 위치만, 글 없음). 줄 번호 파일 3개를 사용자에게 넘길 위치를 보고한다.

### Task 3: MinerU 기본 층 다시 하기 (AI 비용 0, systematic-debugging, ultrathink)

**Files:** Modify `measure/v17_stage1.py`(통과할 때만), `docs/평가/fable-split.md`. git 밖 `measure/out/v17/extract/mineru-gpu/`, `measure/out/fable/mineru-debug.md`, `measure/out/fable/gate-mineru.json`

- [ ] **Step 1:** 시작 시각을 적는다. **상한 2시간**(설계 5-4). v1.7과 같은 명령(`experiments/v17_extract/README.md`, `MINERU_MODEL_ONNX_DEVICE=gpu`, tier `standard`)으로 FX25만 다시 돌려 오류 전체(traceback)를 `mineru-debug.md`에 남긴다.
- [ ] **Step 2:** systematic-debugging 절차로 원인을 찾는다. 허용하는 고치기: 실행 옵션·환경 변수·호출 방법. **MinerU 설치 파일(라이브러리 소스) 고치기는 하지 않는다** — 그것밖에 없으면 멈추고 보고한다. 원인을 확인하기 전에 이유를 적지 않는다.
- [ ] **Step 3:** 상한을 넘으면 리포트에 "원인 확인하지 못함, 탈락 유지"와 해 본 것을 적고 Task 3을 끝낸다.
- [ ] **Step 4:** 고쳤으면 설명서 3개를 같은 설정으로 `measure/out/v17/extract/mineru-gpu/<doc_id>.json`에 다시 뽑고, `run.json`에 `device: "gpu"`, `gpu_required: true`, `run_seconds`(설명서별), 바꾼 옵션을 적는다.
- [ ] **Step 5:** `python -c "from measure.v17_gate import run_gate; from pathlib import Path; r=run_gate(out_path=Path('measure/out/fable/gate-mineru.json')); print(r['mineru-gpu']['eliminated'])"` → 탈락 조건 목록을 리포트에 적는다(v1.7 gate.json은 덮어쓰지 않음).
- [ ] **Step 6:** 탈락 조건이 없을 때만: 테스트 `test_mineru_bundle_uses_tool_and_800` 먼저 → `BUNDLES["mineru_800"] = ("mineru-gpu", manual_pages_from_tool, chunk_plain_800)` → 커밋 두 번.
- [ ] **Step 7:** 마감 11/21 저녁. 못 맞추면 "미완료"로 적는다. Task 1~3 브랜치 마무리(사용자 확인).

### Task 4: Fable 채팅 6번 (사용자, 채팅 Claude 안내)

채팅 Claude가 이때 단계별 가이드(①~⑥)를 준다. 고정 문장은 아래가 전부이고, 그 밖의 말은 보내지 않는다(설계 5-1).

- [ ] **Step 1 (사용자):** 프로젝트 밖 새 채팅에서 모델 목록에 Fable 5.2가 있는지, 메모리를 쓰지 않는 채팅(임시 채팅 등)에서도 고를 수 있는지 화면으로 확인해 알려 준다. 쓸 수 있으면 그 채팅을 쓴다.
- [ ] **Step 2 (사용자):** 설명서마다 새 대화 하나. Fable 줄 번호 분할: `<doc_id>-lines.txt`를 올리고 요청문 A를 보낸다. Fable PDF 분할: `data/manuals/`의 원본 PDF를 올리고 요청문 B를 보낸다.
- [ ] **Step 3 (사용자):** 답이 중간에 멈추면 "이어서 같은 형식으로 계속 써 주세요."를 보낸다. 기준을 되물으면 "요청문의 기준대로 판단해 위치만 답해 주세요."를 보낸다(두 번까지, 그래도 위치가 없으면 새 대화로 다시).
- [ ] **Step 4 (사용자):** 답 전체(이어진 답 포함)를 순서대로 복사해 Claude Code에 전달한다. Claude Code는 `measure/out/fable/answers/<fable_lines|fable_pdf>/<doc_id>.md`에 그대로 저장하고, 화면에 보인 모델 이름·날짜·걸린 분·"계속"/되물음 답 횟수·다시 돌린 횟수와 이유·올린 파일 해시를 `measure/out/fable/runs.json`에 적는다.
  - (덧붙임 2026-11-20, 사용자 결정) 기록 항목에 추론 강도(화면 이름 그대로), 메모리(끔), 웹 검색(끔), 채팅 종류(화면에 보인 그대로)를 더한다. 6번 중 하나라도 아래 "Fable 채팅 조건"과 다르면 멈추고 보고한다.
- [ ] **Step 5:** 한 설명서가 올라가지 않으면(문맥 한도 등) 멈추고 채팅 Claude와 정한다. 나눠 올리는 경우 두 방법 모두 같은 단위로 한 대화에 차례로 올린다.

**Fable 채팅 조건** (덧붙임 2026-11-20, 사용자 결정, 측정 전 고정): 추론 강도 "높음", 메모리 끔, 웹 검색 끔, 프로젝트 밖 새 채팅. 6번 모두 같은 조건으로 돌린다.

**요청문 A (Fable 줄 번호 분할)**

````
첨부한 파일은 한 가전제품 사용설명서의 본문을 쪽마다 줄 단위로 적은 것입니다. 각 줄은 "쪽:줄번호", 탭, 그 줄의 글 순서로 되어 있습니다.

이 설명서를 검색용 덩어리로 나누려고 합니다. 사용자가 이 제품에 대해 질문 하나를 했을 때 그 답에 필요한 내용이 한 덩어리 안에 모이도록, 내용이 바뀌는 곳을 골라 주세요.

지킬 것
1. 설명서의 글을 고치거나 줄이거나 덧붙이지 마세요. 자를 위치만 답합니다.
2. 새 덩어리가 시작되는 줄을 "쪽:줄번호" 형식으로 한 줄에 하나씩 적어 주세요.
3. 덩어리는 쪽을 넘지 않습니다. 각 쪽의 첫 줄은 언제나 새 덩어리로 처리하므로 따로 적지 않아도 됩니다.
4. 덩어리 길이는 신경 쓰지 마세요. 내용이 바뀌는 곳만 고르면 됩니다.
5. 답은 아래처럼 코드 블록에만 넣고, 코드 블록 안에는 다른 글을 쓰지 마세요. 설명은 필요 없습니다. (아래 숫자는 형식 예시이며 실제 위치가 아닙니다.)

```text
7:3
7:15
8:4
```

6. 답이 길어 한 번에 다 쓰지 못하면, 쓴 데까지 코드 블록을 닫고 멈춰 주세요. "계속"을 요청하면 이어서 같은 형식으로 씁니다.
````

**요청문 B (Fable PDF 분할)**

````
첨부한 PDF는 한 가전제품 사용설명서입니다.

이 설명서를 검색용 덩어리로 나누려고 합니다. 사용자가 이 제품에 대해 질문 하나를 했을 때 그 답에 필요한 내용이 한 덩어리 안에 모이도록, 내용이 바뀌는 곳을 골라 주세요.

지킬 것
1. 설명서의 글을 고치거나 줄이거나 덧붙이지 마세요. 자를 위치만 답합니다.
2. 새 덩어리가 시작되는 곳을 "쪽 번호 | 그 자리부터 적힌 글자 20자 안팎" 형식으로 한 줄에 하나씩 적어 주세요.
   - 쪽 번호는 PDF 파일의 쪽 순서입니다(첫 쪽이 1). 설명서에 인쇄된 쪽 번호가 아닙니다.
   - 글자는 그 쪽에 적힌 대로 옮겨 주세요. 띄어쓰기나 기호는 조금 달라도 괜찮습니다.
3. 덩어리는 쪽을 넘지 않습니다. 각 쪽의 맨 처음은 언제나 새 덩어리로 처리하므로 따로 적지 않아도 됩니다.
4. 덩어리 길이는 신경 쓰지 마세요. 내용이 바뀌는 곳만 고르면 됩니다.
5. 답은 아래처럼 코드 블록에만 넣고, 코드 블록 안에는 다른 글을 쓰지 마세요. 설명은 필요 없습니다. (아래는 형식 예시이며 실제 위치가 아닙니다.)

```text
7 | 여기에 그 자리의 글자 20자 안팎
8 | 여기에 그 자리의 글자 20자 안팎
```

6. 답이 길어 한 번에 다 쓰지 못하면, 쓴 데까지 코드 블록을 닫고 멈춰 주세요. "계속"을 요청하면 이어서 같은 형식으로 씁니다.
````

### Task 5: 자를 위치 파일·탈락·실험 조각 저장 (임베딩 비용)

- [ ] **Step 1:** `python -m measure.fable_split cuts fable_lines`, `cuts fable_pdf` → 설명서별 받은 수·형식 어긋남·없는 줄/못 찾음·비율·탈락을 리포트에 적는다. 탈락한 방법은 여기서 빠진다. 읽을 수 없음(`ValueError`)이면 멈추고 보고(Task 4 Step 3의 다시 돌리기).
- [ ] **Step 2:** API 환산을 리포트에 적는다: 입력은 줄 번호 파일 글자 수(PDF 분할은 PDF 글 글자 수, 그림 토큰은 빠짐), 출력은 답 글자 수. 토큰은 확인하지 못했으므로 "1글자 = 1토큰(가정)"으로 바꾼 값과 단가(100만 토큰당 입력 8·출력 40달러)를 함께 적고, 생각 토큰이 빠진다는 한계를 적는다. 사용자가 API 키를 주면 별도 지시로 토큰 세기를 더한다(이 계획 범위 밖).
- [ ] **Step 3 (멈춤, 사용자):** 첫 OpenAI 지출 전에 사용자가 OpenAI 결제 화면에서 잔액을 확인하고, 11/17 운영 반영 비용 대조도 함께 한다(설계 8절). 잔액이 장부 합계 + 1달러보다 적으면 멈춘다.
- [ ] **Step 4:** `python -m measure.v17_stage1 estimate fable_lines fable_pdf [mineru_800]` → 장부 행(글자 수 × 2e-8) → `check_budget(앞 행들, 새 행, cap_usd=1.0)` 결과를 장부에 적는다.
- [ ] **Step 5:** `python -m measure.v17_stage1 store <한 벌>`(통과한 것마다) → 실제 비용 기록.
- [ ] **Step 6:** `.venv/Scripts/python -m pytest -m integration tests/measure/test_v17_bundle.py -v`(`test_guide_chunks_identical_to_production`, `test_bundle_diag_ids_in_bundle`) PASS 확인 → 리포트에 적는다.

### Task 6: 1단계 측정과 최종 후보 (검색만)

**Interfaces (Task 1 파일에 더함):**
- `b1_pass(summary: dict, name: str) -> bool` — `summary`는 `measure_sets`의 요약(`summary[set][name or "production"]["hit5"]`). `dev[name] - dev["production"] >= 3` 그리고 `q30["production"] - q30[name] <= 1`
- `pick_final(summary: dict, names: list[str], order: tuple[str, ...] = ("fable_lines", "fable_pdf", "mineru_800")) -> str | None`

- [ ] **Step 1: 실패하는 테스트** (측정 전에 커밋)

```python
def _s(dev, q30):
    return {"dev": {k: {"hit5": v} for k, v in dev.items()}, "q30": {k: {"hit5": v} for k, v in q30.items()}}

def test_b1_needs_plus3_dev_and_q30_not_down_more_than_1():
    s = _s({"production": 8, "a": 11, "b": 10, "c": 11}, {"production": 20, "a": 19, "b": 20, "c": 18})
    assert b1_pass(s, "a") and not b1_pass(s, "b") and not b1_pass(s, "c")

def test_pick_final_takes_order_within_1_of_best():
    s = _s({"production": 8, "fable_lines": 12, "fable_pdf": 13, "mineru_800": 14}, {"production": 20, "fable_lines": 20, "fable_pdf": 20, "mineru_800": 20})
    assert pick_final(s, ["fable_lines", "fable_pdf", "mineru_800"]) == "fable_pdf"

def test_pick_final_none_when_nobody_passes():
    s = _s({"production": 8, "fable_lines": 10}, {"production": 20, "fable_lines": 20})
    assert pick_final(s, ["fable_lines"]) is None
```

- [ ] **Step 2:** FAIL → 테스트 커밋 → 구현 → PASS → 구현 커밋. CLI `python -m measure.fable_split pick <summary.json> <한 벌 ...>`는 한 벌마다 B-1 결과와 최종 후보를 출력한다.
- [ ] **Step 3:** `python -m measure.v17_stage1 measure --out fable-stage1 strip_800 docling_sections <저장된 후보 ...>` — 운영·후보·기록용을 한 실행 안에서 잰다. 질문 임베딩 장부 행 먼저.
- [ ] **Step 4:** `python -m measure.fable_split pick measure/out/v17/fable-stage1/summary.json <후보 ...>` → 리포트 "1단계"에 표(개발용 5위 안, 30문항 5위 안, 5위 안 또는 진단 안내 쪽)와 판정, 최종 후보를 적는다. v1.7처럼 문장별 순위 변화 표는 기록용으로 붙인다(문장 id와 순위만).
- [ ] **Step 5:** 최종 후보가 없으면 미채택으로 적고 Task 10으로 간다. 확인용 세트는 봉인.

### Task 7: 3단계 (답변까지, 개발용 21문장)

- [ ] **Step 1:** 장부(21문장 × 2벌 × 2회 + 5C 3회) → `check_budget` 기록.
- [ ] **Step 2:** `python -m measure.stage2 evaluation/paraphrase_dev.csv --methods m0 <최종 후보> --label fable-s3-r1`, 같은 명령 `--label fable-s3-r2`. 5C: `measure/out/v17/stage3/5c.csv`를 `measure/out/fable/5c.csv`로 복사해 `python -m measure.stage2 measure/out/fable/5c.csv --methods <최종 후보> --label fable-s3-5c` → `found` 3회 모두 true인지 자동으로 센다(설계 6절 3단계).
- [ ] **Step 3:** `python -m measure.stage2 evaluation/results/fable-s3-r1-<날짜>.csv evaluation/results/fable-s3-r2-<날짜>.csv --blind --label fable-s3` → 대응표 해시를 판정 전에 커밋한다. 결과 CSV는 판정이 끝날 때까지 커밋하지 않는다.
- [ ] **Step 4 (멈춤, 사용자 판정):** 채팅 Claude가 v1.7처럼 클릭 판정 화면을 만들고 "덧붙임" 표시 칸을 더한다(설계 5-6). 사용자가 전부 판정한다.
- [ ] **Step 5:** 대응표 공개 → ⑰로 방법별 정답·환각 → B-2(정답 +3 이상, 환각 0, `summarize_methods`의 `cost_per_q_usd` 비율 1.5 이하, `latency_avg_ms` 차이 500 이하, 5C 3/3). 경계 판정을 뒤집었을 때 결론이 바뀌는지 적는다.
- [ ] **Step 6:** 통과하지 못하면 미채택으로 적고 Task 10으로 간다.

### Task 8: 4단계 (확인용 세트, 3단계를 통과했을 때만)

**Files:** Create `measure/fable_stage4.py`, `tests/measure/test_fable_stage4.py`. Modify `measure/stage2.py`

**Interfaces:**
- `old_chunk_refs_to_pages(refs: str, backup: dict[int, tuple[str, int]]) -> tuple[str, int]` — `|`로 이은 기대 근거에서 `chunk:<n>`(1 ≤ n ≤ 297)을 백업의 그 조각 쪽 `manual:<쪽>`으로 바꾼 글과 바꾼 수. 가이드 번호(298~335)와 `manual:`·`guide:`는 그대로. 바꾼 뒤 같은 근거가 겹치면 한 번만
- `load_backup_pages(path: Path = ROOT/"measure"/"out"/"v17-rollout-backup"/"chunks-manual.jsonl") -> dict[int, tuple[str, int]]` — 옛 번호 → (doc_id, 쪽). 파일 해시가 인수인계 노트 값(ba8433aa…)과 다르면 멈춤
- `run_followups_same_run(methods: list[str], label: str) -> Path` — 대화마다 `stage2.method_order(methods, i)` 순서로 방법을 번갈아 돌려 한 CSV(방법 열 포함)에 쓴다. 방법 `m0`은 운영, 그 밖은 `bundle_deps`
- `stage2.py`: 파일 이름에 `test`가 있으면 지금처럼 멈추되, `--open-test-set`이 있고 `measure/out/fable/stage3-pass.json`(Task 7 Step 5가 B-2 통과일 때만 씀)이 있을 때만 연다

- [ ] **Step 1:** 테스트 먼저: `test_old_manual_chunk_ref_becomes_page`, `test_guide_and_page_refs_unchanged`, `test_stage2_refuses_test_set_without_pass_file`, `test_followups_same_run_alternates_methods` → 커밋 → 구현 → 커밋
- [ ] **Step 2:** v1.7 계획 Task 11 "갈래 가" Step 1~3 그대로(새 응답자 확인용 10카드 문장 정리 → 카드와 다른 것을 묻는 문장은 채팅 Claude 원문 확인·사용자 확정 → 지난 20문장 해시 확인 → 합친 파일과 새 해시 커밋). 합친 파일의 기대 근거에 `old_chunk_refs_to_pages`를 쓰고 바꾼 문장 수를 리포트에 적는다.
- [ ] **Step 3:** 장부 → 한 실행 안에서 운영과 최종 후보 각 2회: 확인용·30문항은 `stage2 --methods m0 <후보> --open-test-set`, 이어지는 질문은 `run_followups_same_run(["m0", 후보], ...)`.
- [ ] **Step 4 (멈춤):** 판정 양을 사용자에게 보고하고, 전부 사람 판정인지 ⑳ 방식인지 사용자가 정한다 → 가린 판정지·해시 커밋 → 사용자 판정 → B-3 → 결론(설계 6절 "결론 내는 법").

### Task 9: 032 다시 세기 (AI 비용 0, Fable 실험 뒤, 11/24~25)

**Files:** Create `measure/recount_032.py`, `tests/measure/test_recount_032.py`. git 밖 `measure/out/fable/recount-032/`

**Interfaces:**
- `collect_targets() -> list[dict]` — 설계 7절 범위(v1.7 3단계 2벌×2회, 회귀 30문항·이어지는 질문 2벌×2회, 운영 반영 9단계 30문항 2회)에서 정답·정답(경계)로 판정된 답 전부. 열: `run, method, qid, round, model_id, question, answer, old_verdict`. 판정 원자료는 v1.7 판정 기록(대응표·사람 판정 파일·⑳ 결과, 모두 git 밖)에서 읽는다
- `recount_a3(old: list[dict], new: dict[tuple, str]) -> dict` — 새 판정으로 바꾼 뒤 ⑰로 A-3 표(벌별 정답·환각)를 다시 셈

- [ ] **Step 1:** 테스트 먼저(`test_collect_keeps_only_correct_and_boundary_correct`, `test_recount_applies_17_rule`) → 커밋 → 구현 → 커밋
- [ ] **Step 2:** `targets.csv` 만들기 → 수만 보고(답 글은 출력하지 않음)
- [ ] **Step 3 (멈춤):** 채팅 Claude가 사용자 승인을 받아 `targets.csv`를 읽고, 설명서·해결 가이드 전체 글자 검색으로 "원문에 없는 절차·숫자·이름"이 있는 답을 골라 `flagged.csv`로 넘긴다(315·330·267·354 포함, 고른 기준과 수를 적음)
- [ ] **Step 4 (멈춤):** 사용자가 설계 5-6 규칙으로 판정 → `recount_a3` → 리포트와 결정기록 032 덧붙임(원문은 지우지 않음). A-3이 실패로 바뀌면 쪽 표시 지우기를 어떻게 할지 사용자에게 묻는다(되돌리기 백업 `measure/out/v17-rollout-backup/`, DB 작업은 사용자 확인 뒤).

### Task 10: 결론 기록

- [ ] **Step 1:** 리포트 맨 위 "정리"(결론·기준별 결과·한계·비용). 한계에는 설계 11절 전부와 실행 중 생긴 것(다시 돌린 횟수, "계속" 횟수, 메모리를 끄지 못한 경우 등)을 적는다.
- [ ] **Step 2:** 결정기록 034(결론). 채택이면 운영 반영은 별도 계획(새 모델 처리 방식과 2차 설계 초안의 비목표를 함께 본다), 미채택·미완료면 이유와 확인용 세트 상태.
- [ ] **Step 3:** 개발일지·AI 실수 기록. 노션 개발 타임라인과 도구 비교 모음(MinerU 결과)은 채팅 Claude가 정리한다. `bundle_chunks`의 v1.7 4벌과 이번 벌을 지울지는 사용자에게 묻는다(지우기는 사용자 확인 뒤).
- [ ] **Step 4:** 최종 검토 서브에이전트(Opus·xhigh, requesting-code-review, 확인용 세트 읽기 금지를 요청문에 적음) → 브랜치 마무리(사용자 확인).
