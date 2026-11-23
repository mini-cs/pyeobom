# 펴봄 2차 — 내 모델 요청 흐름 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 날짜: 2026-11-21 (2차 기간 2026-11-25 수 ~ 12-01 화)
- 상태: **승인 (2026-11-21, 사용자 "추천대로").** "계획에서 정한 것" 9개도 이 승인에 들어간다. 실행 방식: **Native**(Claude Code가 날마다 직접 구현, 브랜치별 검토는 각 Task에 적은 대로).
- 작성: 채팅 Claude. 근거: 설계 3판(승인 2026-11-20), 인수인계 노트(2026-11-21 새벽 판), 저장소 main `2370fb2` 코드(클라우드에서 읽기 전용으로 받아 확인).
- 표시: **(사용자 결정)**, **(설계)** = 설계 3판에 있음, **(Claude 판단)** = 이 계획에서 채팅 Claude가 정함, 사용자가 고칠 수 있음.

**Goal:** 내 가전 모델이 없으면 로그인해 요청하고, 운영자가 모델 추가 도구로 넣고 합격선을 통과하면 요청자에게 메일이 가는 고리를 pyeobom.help에서 끝까지 돌리고, 모델 추가 시간을 도구 전후로 잰다.

**Architecture:** 질문·답변(RAG)은 지금 그대로 Vercel 파이썬(FastAPI) + Neon. 로그인과 요청 표는 Supabase(Auth + Postgres + RLS)를 화면에서 공개 키로 직접 부른다. 메일은 인증 코드는 Supabase → Resend SMTP, 알림은 Supabase 데이터베이스 웹훅 → 새 알림 주소(`/api/notify`) → Resend API. 모델 추가 도구는 운영자 PC에서 도는 파이썬 명령(`python -m ingest.add_model`)이다.

**Tech Stack:** Python 3.14·FastAPI·psycopg·pgvector(지금 그대로), Supabase Auth·Postgres·RLS·Database Webhooks, supabase-js(버전 고정, 저장소에 사본), Resend(SMTP·API·받기), Playwright(파이썬 sync API, 지금 방식), Node `--test`(화면 JS 단위 테스트, 지금 방식).

**Spec:** `docs/superpowers/specs/2026-11-17-phase2-model-request-design.md` (3판, 승인 2026-11-20). 실행하는 사람은 설계와 이 계획을 함께 읽는다.

## Global Constraints

모든 Task에 적용된다. 값은 설계·결정 원문 그대로.

1. 질문·답변 흐름을 바꾸지 않는다: `app/ask/`·`app/retrieval/`·`app/answer/`는 손대지 않는다(설계 3.5-1). 적재 설정은 운영 그대로: 임베딩 text-embedding-3-small, `OPENAI_EMBED_DIMENSIONS` 비움, `CHUNK_CONTEXT_MODEL` 비움.
2. 요청자 이메일은 Supabase 인증 쪽에만 둔다. 요청 표·저장소·로그·노션·개발일지·영상에 복사하지 않는다(설계 3.5-3, 3.7-4).
3. service 키·Resend 키는 Vercel 환경 변수에만. 화면에는 공개(anon/publishable) 키만, 그것도 저장소에 쓰지 않고 `/api/public-config`로 내려준다(설계 3.5-4, CLAUDE.md "API 키 커밋 금지").
4. "추가됨"은 ① 배포가 끝나 운영 화면에서 그 모델이 보이고 ② 합격선을 통과한 **뒤에만**(설계 8.3). 미달이면 모델 목록(`data/models.json`)을 배포하지 않는다.
5. 카테고리는 세탁기·건조기·에어컨만. 값은 `washer`·`dryer`·`aircon`(models.json `appliance`와 같은 코드) (사용자 결정 / 코드값은 Claude 판단).
6. 합격선: 확인 질문 10개, 사람 판정, **정답 8개 이상 · 환각 0**, 경계 판정은 오답·환각 쪽으로 뒤집어도 넘어야 합격. 판정 규칙은 `docs/평가/평가-규칙.md` "사람 판정"(033 덧붙임 포함), 가린 판정은 안 함(설계 9.3-8). 미달이면 질문을 고치지 않는다. 적재 문제(추출·쪽 표시·json·가이드 연결)를 고친 경우에만 같은 질문으로 **1번** 다시 돌린다(설계 9.3-8 제안을 측정 전에 확정).
7. 개선: 비교용 모델 재추가의 **추가 작업 시간이 전의 절반 이하**이고 **사람 단계 수가 줄면** 개선. 아니면 "개선 확인 못 함"(설계 9.3-6).
8. **DB 연결 규칙(사용자 결정 2026-11-21)**: 오래 걸리는 작업은 DB 연결을 DB 작업 직전에 열고 바로 닫는다. AI 호출·파일 처리·대기 동안 연결을 쥐고 있지 않는다(서버는 트랜잭션 열린 연결을 5분, 놀고 있는 연결도 6~16분 사이에 끊음).
9. **가이드 문서는 다시 적재하지 않는다 (Claude 판단)**: 새 모델에 가이드를 연결할 때는 `document_models`에 한 줄만 넣는다. `python -m ingest --doc-id guide-…`는 가이드 조각을 지우고 새로 넣어 조각 번호 298~335가 바뀌고, 평가 세트의 기대 근거가 깨진다.
10. AI 비용: 2차 장부 상한 **1달러**(`check_budget(rows, new, cap_usd=1.0)`), 운영 잔액 1달러 이상, 3일차 전에 잔액 확인. 확인용 세트는 봉인 그대로.
11. 무료 한도: Resend 하루 100통(받은 메일 포함), Supabase 사용자 지정 SMTP 시간당 30통, 인증 코드 같은 사람 60초에 1번·1시간 유효.
12. 시험 계정은 Resend 받기 주소(`test1@<계정 id>.resend.app` 형식)만 쓴다. 테스트 값은 누가 봐도 가짜인 값만. 상호 테스트 참가자 계정·요청은 데모데이 뒤 지운다.
13. CLAUDE.md 그대로: 모델·강도 Opus · high, 테스트 먼저 커밋 2번, merge commit, main 직접 커밋 금지, DB 구조 SQL·데이터 삭제는 실행 전에 멈추고 사용자 확인, 화면은 `docs/design/디자인-가이드.md`의 CSS 변수만, Vercel·Supabase·Resend 설정은 공식 문서(Context7 포함)로 확인한 뒤 적용.
14. 코드 동결: 4일차(11/30) 밤. 5일차(12/1) 아침은 확인·리허설·10시 제출만.
15. 밀리면 설계 3.6 순서로 뺀다: "내 요청" 카드 → 구글 로그인 → 도구 자동화 일부(글자 없는 PDF·쪽 표시 검사와 확인 질문 실행은 남김) → Playwright 범위(핵심 흐름 1개는 남김). 여유 시 항목(대화 서버 저장, 탈퇴 버튼, 네이버·카카오)은 이 계획에 없다 — 하려면 새 계획.

## Review Focus

테스트가 따로 없으면 사람이 가장 먼저 부딪힐 다섯 가지. 각 줄의 테스트는 맡은 Task에 넣었다.

1. **Supabase가 멈추거나 `/api/public-config`가 실패할 때**: 모델 고르기·질문하기는 그대로 되고, 로그인·요청만 "잠시 쓸 수 없어요"(설계 10-7). → Task 6 `test_request_unavailable_keeps_chat_working`
2. **같은 웹훅이 두 번 오거나 상태를 같은 값으로 다시 저장할 때**: 요청자 메일이 두 번 가지 않는다(바뀐 경우에만 보냄). → Task 7 `test_update_same_status_sends_nothing`
3. **화면과 DB의 모델명 정규화가 다를 때**: "이미 요청하셨어요"·"이미 있어요" 안내가 틀린다. 같은 사례 파일로 JS와 실제 DB 둘 다 확인한다. → Task 4 `test_model_key_matches_cases_live`, Task 6 `request.test.mjs`
4. **로그인이 끊긴 채(세션 만료·다른 탭 로그아웃) 요청할 때**: 날것 오류 대신 로그인 시트로 다시 안내. → Task 6 `test_request_after_session_expired_shows_login`
5. **"추가됨"을 배포 전에 눌렀을 때**: 알림 주소가 자기 배포의 models.json에 그 모델이 없으면 메일을 보내지 않는다(설계 3.5-2를 코드로 막음, Claude 판단). → Task 7 `test_added_but_not_deployed_sends_nothing`

---

## 브랜치 전략 (CLAUDE.md "브랜치·Task 매핑")

한 번에 브랜치 하나, 앞 브랜치 병합 뒤 최신 main에서 다음 브랜치를 만든다.

1. `chore/phase2-prep` — Task 1 (2차 전, 11/21~24)
2. `feat/phase2-measure-prep` — Task 2 (1일차 오전)
3. `feat/model-<비교용 모델 id>` — Task 3, 지금 방식 추가 = 전 측정 (1일차)
4. `feat/phase2-request-flow` — Task 4~7 (2일차)
5. `feat/phase2-add-model-tool` — Task 8~9 (3일차)
6. `chore/model-<비교용 모델 id>-remove` → `feat/model-<비교용 모델 id>-readd` → `feat/model-<요청 모델 id>`(최대 2개) — Task 10 (4일차)
7. `feat/phase2-qa` — Task 11 (4일차, 코드 동결 전)
8. `docs/phase2-submission` — Task 12 (4일차 밤~5일차 아침, 문서만)

## 사용자 작업 (채팅 Claude가 그때 단계별 가이드를 준다)

코드 Task가 기다리는 순서대로. 멘토 확인(2차 전 계정 준비 허용) 뒤에 한다.

- U1 (Task 1 병합 뒤): Vercel에 pyeobom.help 연결. 옛 주소를 넘겨줄지는 연결 화면에서 방식(301/308 등)을 보고 정한다.
- U2: Resend 계정, pyeobom.help 도메인 인증(DNS 기록은 Vercel DNS에), 받기 시험 주소 2개(시험 계정 둘 = RLS 시연용).
- U3: Supabase 프로젝트 만들기. 지역은 **서울(Northeast Asia)** (Claude 판단: 로그인·요청은 브라우저가 Supabase를 직접 부르고, 서버→Supabase는 알림 때만이라 사용자 위치가 더 중요). 사용자 지정 SMTP = Resend(`smtp.resend.com`, 465, 사용자명 `resend`), Magic Link 템플릿에 `{{ .Token }}`.
- U4: 구글 OAuth 클라이언트 → Supabase Google 제공자, 허용 돌아올 주소(pyeobom.help, 미리보기 주소).
- U5: Vercel 환경 변수 7개(Task 5·7 표 참고), 로컬 `.env`에도 같은 이름.
- U6 (Task 4): `supabase/schema.sql`을 Supabase SQL 편집기에서 실행(구조 SQL이라 사용자가 직접).
- U7 (Task 7 병합 뒤): 데이터베이스 웹훅 2개 등록(INSERT·UPDATE → `https://pyeobom.help/api/notify`, 비밀 값 헤더).
- U8 (3일차 전): OpenAI 잔액 확인(Billing), 장부에 적기.
- U9 (3일차): 상호 테스트 참가자에게 주소 공유, 참가자는 코드(A·B·C…)로만 기록.

---

### Task 1: 2차 전 정리 — 새 주소도 운영으로 막기, 기록 정리

**브랜치:** `chore/phase2-prep` · **언제:** 11/21~24, U1(도메인 연결) **전에** 병합

**Files:**
- Modify: `measure/load_common.py:6` (`PRODUCTION_HOST` → 여러 개)
- Modify: `tests/measure/test_load_common.py:22`
- Create: `docs/superpowers/plans/2026-11-21-phase2-model-request-plan.md` (이 계획, `docs/Claude outputs/` 사본을 그대로)
- Modify: `docs/개발일지/<그날>.md`, `docs/AI-실수-기록.md`
- Create: `.claude/skills/ffmpeg-usage/`, `.claude/skills/security-audit/`, `skills-lock.json` 항목, watch 플러그인 프로젝트 범위 설정(`.claude/settings.json`, 설치 명령이 만드는 그대로)

**왜:** 설계 15-5 확인 결과(채팅 Claude, 코드 읽기): 측정 스크립트는 운영 주소를 직접 부르지 않고 주소를 인자로 받는다. 다만 부하 측정 막기(`assert_not_production`)가 `pyeobom.vercel.app`만 막아서, 도메인을 붙이면 `pyeobom.help`로는 부하 측정이 막히지 않는다.

**Interfaces:**
- Produces: `PRODUCTION_HOSTS: frozenset[str] = {"pyeobom.vercel.app", "pyeobom.help", "www.pyeobom.help"}`, `assert_not_production(url: str) -> None`(이름·동작 그대로, 집합으로 검사)

- [ ] **Step 1: 실패 테스트** — `test_load_common.py`의 막는 주소 parametrize에 `"https://pyeobom.help"`, `"https://pyeobom.help/api/ask"`, `"www.pyeobom.help"`를 더한다(모두 `ValueError`). 미리보기 주소(`https://pyeobom-git-x-mini-cs.vercel.app`)는 통과하는 경우를 그대로 둔다.
- [ ] **Step 2:** `pytest tests/measure/test_load_common.py -v` → 새 경우 FAIL. 테스트 커밋.
- [ ] **Step 3:** `PRODUCTION_HOSTS` 집합으로 바꾸고 `assert_not_production`이 `host in PRODUCTION_HOSTS`로 본다. 다른 곳에서 `PRODUCTION_HOST`를 쓰면 함께 고친다(`grep -rn PRODUCTION_HOST`).
- [ ] **Step 4:** `pytest -v -m "not integration"` 전부 통과. 구현 커밋.
- [ ] **Step 5: 기록** — 개발일지에 PR #83 병합 `33cff85`, PR #86 병합 `2370fb2`, DB 연결 오류 조사 결과(인수인계 노트 v1.95 "DB 연결 오류 원인 확인" 요약, 개발일지 "나중에"의 DB 오류 줄 옆에 "원인 확인됨, 2026-11-21" 덧붙임), 이 계획 파일 추가. 계획 파일은 `docs/Claude outputs/` 사본의 SHA-256을 채팅 Claude가 준 값과 대조한 뒤 넣는다. 문서 커밋.
- [ ] **Step 6: 스킬 범위 바로잡기 (CLAUDE.md "설치는 프로젝트 범위로만, 전역 -g 금지")** — 2026-11-20에 사용자 범위로 설치한 3개(ffmpeg-usage, security-audit, watch 플러그인)를 프로젝트 범위로 옮긴다. 방법은 기존 accessibility 스킬과 같은 방식(`DISABLE_TELEMETRY=1 npx skills add …`, `-g` 없이)과 `claude plugin install --scope project`. 설치 전에 들어올 파일 목록을 보고하고, SKILL.md·참고 문서 말고 실행 파일(install.sh 등)이 들어오면 멈춘다. ffmpeg-usage SKILL.md 해시는 `f233ed03…`(전과 같아야 함). 옮긴 뒤 사용자 범위 사본·플러그인을 지우기 전에 목록을 보여 주고 사용자 확인. 그 전부터 사용자 범위에 있던 example-skills 플러그인·web-design-guidelines는 건드리지 않고 개발일지에 사실만 적는다. AI 실수 두 줄: 채팅 Claude(설치 지시에 CLAUDE.md 스킬 범위 규칙을 확인하지 않고 "사용자 범위로만"이라고 씀), Claude Code(설치 때 이 규칙과 다른 점을 짚지 못함).
- [ ] **Step 7:** 마무리(CLAUDE.md 브랜치 마무리 순서). PR 본문에 "U1 도메인 연결은 이 PR 병합 뒤".

### Task 2: 측정 준비 — 시간 기록지·확인 질문·합격 판정을 코드로 고정

**브랜치:** `feat/phase2-measure-prep` · **언제:** 1일차 오전, 측정 시작 전에 병합

**Files:**
- Create: `evaluation/phase2_timelog.py`, `evaluation/phase2_verdict.py`
- Create: `evaluation/phase2/ledger.csv` (열 `date,item,estimate_usd,actual_usd,note`, 첫 줄은 머리만)
- Create: `docs/평가/phase2-model-add.md` (리포트 뼈대: 측정 전 결정 = 설계 9.3 1~12를 그대로 옮김, 장부, 전·후 표, 합격 판정, 한계)
- Create: `docs/결정기록/039-2차-구조와-DB-연결-규칙.md`, `docs/PRD.md`
- Test: `tests/evaluation/test_phase2_timelog.py`, `tests/evaluation/test_phase2_verdict.py`

**Interfaces:**
- Produces (`evaluation/phase2_timelog.py`):
  - `KINDS = ("사람", "기다림", "질문 쓰기", "판정", "배포 대기", "멈춤")`
  - `read_timelog(path: str) -> list[dict]` — CSV 열 `step,kind,start,end,note`, 시각 `YYYY-MM-DD HH:MM`. 열 없음·모르는 kind·end<=start·줄끼리 겹침이면 `ValueError`(줄 번호 포함).
  - `summarize(rows: list[dict]) -> dict` — 키 `extra_work_min`(사람+기다림), `total_min`(멈춤 뺀 전부), `excluded_min`(질문 쓰기+판정+배포 대기), `paused_min`, `person_steps`(kind == "사람" 줄 수)
  - `improved(before: dict, after: dict) -> bool` — `after["extra_work_min"] <= before["extra_work_min"] / 2 and after["person_steps"] < before["person_steps"]`
- Produces (`evaluation/phase2_verdict.py`):
  - `VERDICTS = ("정답", "오답", "환각", "찾지 못함")`
  - `validate_confirm_set(rows: list[dict], page_count: int) -> list[str]` — 확인 질문 CSV(열 `qid,kind,question,expected_pages,source`, kind는 `사용법`·`에러 코드`, expected_pages는 `12;13`, source는 `manual` 또는 `guide:<doc_id>`)의 문제 목록. 비면 통과.
  - `passes(judgments: list[dict]) -> tuple[bool, dict]` — 판정 CSV(열 `qid,verdict,borderline,worse_verdict`). 경계(`borderline == "yes"`) 줄은 `worse_verdict`로 센다. detail 키 `correct, hallucination, correct_worst, hallucination_worst`.

- [ ] **Step 1: 실패 테스트** (값은 설계 9.3 그대로)

```python
def test_summarize_excludes_question_writing_judging_deploy_wait(tmp_path): ...
    # 사람 10분 + 기다림 5분 + 질문 쓰기 40분 + 판정 15분 + 배포 대기 3분 + 멈춤 30분
    assert s["extra_work_min"] == 15 and s["total_min"] == 73 and s["paused_min"] == 30 and s["person_steps"] == 1
def test_improved_needs_half_time_and_fewer_person_steps():
    assert improved({"extra_work_min": 60, "person_steps": 9}, {"extra_work_min": 30, "person_steps": 8})
    assert not improved({"extra_work_min": 60, "person_steps": 9}, {"extra_work_min": 31, "person_steps": 3})
    assert not improved({"extra_work_min": 60, "person_steps": 9}, {"extra_work_min": 10, "person_steps": 9})
def test_read_timelog_rejects_overlap_unknown_kind_and_reversed_time(tmp_path): ...
def test_confirm_set_rules():
    # 10개가 아니면, 에러 코드가 0·2개가 아니면, 사용법 8개(또는 에러 코드 0개면 10개)가
    # 쪽 범위 앞·중간·뒤 1/3마다 2개 이상이 아니면, expected_pages가 비면 문제를 돌려준다
def test_passes_counts_borderline_by_worse_verdict():
    # 정답 9(그중 경계 2, worse 오답) + 오답 1 → correct 9, correct_worst 7 → 불합격
    # 정답 8 + 오답 2, 환각 0 → 합격 / 정답 10 중 경계 1(worse 환각) → 불합격
```

- [ ] **Step 2:** `pytest tests/evaluation/test_phase2_timelog.py tests/evaluation/test_phase2_verdict.py -v` → FAIL. 테스트 커밋.
- [ ] **Step 3:** 두 파일 구현. 표준 라이브러리만(csv, datetime).
- [ ] **Step 4:** 통과 확인, 전체 `-m "not integration"` 통과. 구현 커밋.
- [ ] **Step 5: 문서** — 결정기록 039: ① 2차 계정·요청은 Supabase(결정기록 005의 "2차 로그인·기록도 같은 DB"를 바꿈, 이유 설계 4-4) ② DB 연결 규칙(Global 8, 근거 v1.95 DB 오류 조사) ③ 가이드는 다시 적재하지 않고 연결만(Global 9) ④ 알림은 Supabase 웹훅 → 파이썬 알림 주소(설계 4-7). PRD.md는 기획서의 2차 부분 + 설계 1~3절 요약. 리포트 뼈대에 측정 전 결정을 옮기고 `git log`에 남게 커밋(측정 전에 정했다는 증거). 문서 커밋 후 마무리.

### Task 3: 비교용 모델 고르기·확인 질문 쓰기·지금 방식 추가 (전 측정)

**브랜치:** `feat/model-<id>` · **언제:** 1일차 · **누가:** 사용자(사람 단계) + Claude Code(명령 실행·기록)

**Files:**
- Create: `evaluation/phase2/<model_id>-confirm.csv`, `measure/out/phase2/<model_id>-before.timelog.csv`(git 밖, 시각만이라 리포트에 요약 표를 옮김)
- Modify: `data/documents.json`, `data/models.json`, `public/js/examples.js`(예시 질문), `public/images/models/<model_id>.svg`(결정기록 025)
- Modify: `docs/평가/phase2-model-add.md` (확인 질문 파일 해시, 전 측정 요약)

- [ ] **Step 1: 비교용 모델 고르기(사용자, 설계 9.3-11)** — 글자 있는 PDF, 삼성·LG, 세탁기 또는 에어컨, 지금 3개와 다른 모델. 이용 조건 확인. 기록지 첫 줄 시작 = PDF를 손에 넣은 시각.
- [ ] **Step 2: 확인 질문 쓰기(사용자, 기록지 kind `질문 쓰기`)** — 설계 9.3-7 구성. 설명서 원문 대조, 답이 있는 쪽 모두. `validate_confirm_set` 통과 → 커밋 → SHA-256(LF)을 리포트에 적고 커밋. **적재 전에 끝낸다.**
- [ ] **Step 3: 지금 방식으로 추가** — 기록지에 한 줄씩(kind `사람`·`기다림`): documents.json 항목, models.json 항목(diagnostic_refs 포함), 가이드 연결은 Neon SQL 편집기에서 `document_models`에 한 줄 INSERT(사용자 확인 뒤, Global 9), `python -m ingest --doc-id <manual id>`(장부 먼저), error_codes·브랜드 별칭(새 브랜드일 때만), 일러스트, 예시 질문, 로컬 서버(`uvicorn index:app`)를 열고 화면에서 확인 질문 10개를 직접 입력해 답을 판정지로 옮기기.
- [ ] **Step 4: 판정(사용자, kind `판정`)** — `passes()`로 합격 확인. 미달이면 PR을 병합하지 않고 원인을 리포트에 적는다(설계 9.3-8).
- [ ] **Step 5: 배포(kind `배포 대기`)** — PR 병합 → 운영 화면에서 모델이 보이는 시각 = 기록지 마지막 줄 끝. `summarize()` 결과를 리포트 "전" 칸에 적는다.

### Task 4: 요청 표·RLS (Supabase)

**브랜치:** `feat/phase2-request-flow` · **언제:** 2일차 · **필요:** U3

**Files:**
- Create: `supabase/schema.sql`, `docs/db.md`(제출물: 표·열·제약·정책·웹훅 설명)
- Create: `tests/fixtures/model_key_cases.json` (입력 → 정규화 값 사례, 한글·공백·하이픈·점·슬래시·소문자·별표 포함)
- Test: `tests/requests/test_rls_live.py` (`integration`, 실제 Supabase. 비용 OpenAI 0)

**표 `public.model_requests` (열은 설계 7절, 세부는 Claude 판단):**
- `id bigint identity`, `user_id uuid not null default auth.uid()` → `auth.users(id) on delete cascade`(계정을 지우면 요청도 지워져 데모데이 뒤 삭제가 쉬움)
- `category` ∈ `washer|dryer|aircon`, `brand` 1~20자, `model_text` 2~40자이고 영문·숫자 한 글자 이상
- `model_key` 생성 열: `upper(regexp_replace(model_text, '[^0-9A-Za-z가-힣]', '', 'g'))` (영문 대문자로, 영문·숫자·한글 밖의 글자는 모두 뺌)
- `status` ∈ `대기|확인 중|추가됨|추가 어려움` 기본 `대기`, `reason`, `model_id`
- 제약: `status = '추가됨'`이면 `model_id` 필수, `status = '추가 어려움'`이면 `reason` 필수, `unique (user_id, model_key)`
- `created_at`, `updated_at`(바뀔 때 자동 갱신 트리거)
- RLS 켬. 정책: SELECT 본인 행만 / INSERT 본인 행만 + `status = '대기'` + `reason`·`model_id` 비어 있음 + 최근 24시간 본인 요청 5개 미만 / UPDATE·DELETE 정책 없음(사용자 불가, 운영자는 표 화면에서)
- 공개 키로는 `auth.users`를 못 읽는다(이메일은 Supabase Auth에만).

- [ ] **Step 1: 실패 테스트(live)** — 관리 API로 가짜 시험 사용자 2명을 만들고(이메일은 Resend 받기 주소 형식의 가짜, 코드 받기 없이 관리 API로 세션 발급 — 방법은 Supabase 공식 문서로 확인) 각자 공개 키로 요청:
  - `test_user_sees_only_own_requests` · `test_user_cannot_update_or_delete` · `test_insert_with_status_added_is_rejected` · `test_duplicate_model_key_is_rejected` · `test_sixth_request_in_24h_is_rejected` · `test_model_key_matches_cases_live`(사례 파일 전부)
  - 끝나면 시험 사용자와 요청을 지운다(테스트가 만든 것만).
- [ ] **Step 2:** U6 전이라 표가 없어 FAIL 확인. 테스트 커밋.
- [ ] **Step 3:** `supabase/schema.sql` 작성 → **멈추고** 사용자가 SQL 편집기에서 실행(U6).
- [ ] **Step 4:** `pytest tests/requests -m integration -v` 통과. `docs/db.md` 작성. 구현 커밋.

### Task 5: 설정과 공개 설정 주소

**Files:**
- Modify: `app/core/config.py` (Settings에 추가), `app/web.py` (`/api/public-config`)
- Modify: `.env.example`(이름만, 값 없음)
- Test: `tests/core/test_config.py`, `tests/web/test_public_config.py`

**환경 변수 (U5):** `SUPABASE_URL`, `SUPABASE_ANON_KEY`(공개), `SUPABASE_SERVICE_KEY`(서버만), `RESEND_API_KEY`, `NOTIFY_WEBHOOK_SECRET`, `OPERATOR_EMAIL`, `MAIL_FROM`(예: `펴봄 <noreply@pyeobom.help>`). 대시보드가 새 이름(publishable/secret key)을 쓰면 그 값을 넣고 이름은 그대로 둔다 — 관리 API 호출 헤더가 새 키에서 다른지는 Context7로 확인.

**Interfaces:**
- Produces: `Settings.supabase_url, supabase_anon_key, supabase_service_key, resend_api_key, notify_webhook_secret, operator_email, mail_from` (모두 `str`, 기본 `""`)
- Produces: `GET /api/public-config` → 200 `{"supabase_url": str, "supabase_anon_key": str}` / 둘 중 하나라도 비면 503 `{"error_code": "LOGIN_UNAVAILABLE"}` (오류 정의는 `app/core/errors.py` 방식 그대로)

- [ ] **Step 1: 실패 테스트** — `test_public_config_returns_only_public_values`(응답 키가 정확히 둘, service·Resend·비밀 값 문자열이 응답 본문에 없음), `test_public_config_503_when_missing`, 설정 읽기 테스트.
- [ ] **Step 2~4:** FAIL → 테스트 커밋 → 구현 → 통과 → 구현 커밋.

### Task 6: 화면 — 내 모델이 없어요, 로그인 시트, 요청 화면, 건조기

**Files:**
- Create: `public/vendor/supabase.js`(supabase-js 버전 고정 사본. 버전·출처 주소·SHA-256·라이선스를 `public/vendor/README.md`에), `public/js/auth.js`, `public/js/request.js`
- Modify: `public/index.html`(건조기 타일, 모델 화면의 "내 모델이 없어요", 요청 화면 `data-screen="request"`, 로그인 시트), `public/app.js`(`APPLIANCES`에 `dryer: "건조기"`, 경로 `#request/<appliance>`, 빈 목록 안내), `public/styles.css`, `public/icons/<건조기 아이콘>.svg`(지금 아이콘과 같은 Tabler 묶음에서, 이름은 Tabler에서 확인)
- Test: `tests/web/js/request.test.mjs`, `tests/web/test_ui_request.py`(`ui` 표시, 지금 `test_ui_flow.py`처럼 로컬 정적 서버 + 가로채기. 공용 fixture는 `tests/web/conftest.py`로 옮김)

**스킬:** frontend-design, 끝나면 web-design-guidelines로 새 화면만 점검.

**Interfaces:**
- Produces (`public/js/request.js`):
  - `normalizeModelKey(text: string) -> string` — DB 생성 열과 같은 규칙(사례 파일로 고정)
  - `findExistingModel(models, appliance, text) -> model | null` — 그 카테고리 모델의 `model_codes`와 비교. 코드 끝 `*`는 "그 앞부분으로 시작"
  - `validateRequest({appliance, brand, modelText}) -> string | null` (화면에 보일 안내 문장)
  - `requestErrorMessage(error) -> string` — 중복(23505) → "이미 요청하셨어요", 정책 위반(42501, 24시간 5개) → "오늘은 요청을 더 받을 수 없어요. 내일 다시 요청해 주세요", 로그인 끊김(401) → 로그인 시트, 그 밖 → "잠시 쓸 수 없어요"
- Produces (`public/js/auth.js`): `initAuth() -> Promise<Auth | null>`(공개 설정 실패 시 null), `Auth.sendCode(email)`, `Auth.verifyCode(email, code)`, `Auth.google()`, `Auth.session()`, `Auth.client`

**정해진 문구 (설계 5절):** "내 모델이 없어요" · "이미 있어요" + [바로 질문하기] · "이미 요청하셨어요" · "요청을 받았어요. 추가되면 메일로 알려 드릴게요." · "잠시 쓸 수 없어요". 건조기 빈 목록: "아직 등록된 건조기 모델이 없어요." + "내 모델이 없어요". 로그인 시트 안내(Claude 판단, 사용자 확인): "이메일과 요청 내용(가전 종류·브랜드·모델명)을 저장해요. 모델이 추가되면 알려 드리는 데만 써요. 지우고 싶으면 알림 메일에 답장해 주세요. 2차 테스트 기간의 계정과 요청은 데모데이가 끝나면 지워요." (알림 메일의 답장 주소 = `OPERATOR_EMAIL`, 저장소에는 안 씀)

- [ ] **Step 1: 실패 테스트 — JS 단위** (`node --test tests/web/js/`): 사례 파일 전부 `normalizeModelKey` 일치, `findExistingModel`이 `WD90H25AH-1234`를 `WD90H25AH*` 모델로 찾음·다른 카테고리 모델은 안 찾음, 빈 입력·공백만·1자·41자·기호만 거절, `requestErrorMessage` 네 갈래.
- [ ] **Step 2: 실패 테스트 — 화면** (`ui`, Supabase 주소는 가짜 `https://supabase.test`로 가로챔, 비용 0):
  - `test_dryer_tile_shows_empty_list_and_request_button` · `test_request_requires_login_then_returns_to_form` · `test_existing_model_offers_ask_now` · `test_request_success_message` · `test_duplicate_request_message`
  - Review Focus 1 `test_request_unavailable_keeps_chat_working`: `/api/public-config` 503·Supabase 주소 연결 끊김 둘 다에서 모델 고르기·질문(가로챈 `/api/ask`)은 되고 요청 화면만 "잠시 쓸 수 없어요"
  - Review Focus 4 `test_request_after_session_expired_shows_login`: 요청 POST가 401이면 로그인 시트
  - 설계 10-3·10-6 `test_wrong_code_and_resend_wait_messages`: 틀린 코드 → "코드가 맞지 않아요. 다시 확인해 주세요", 60초 안에 다시 보내기(가로챈 429) → "잠시 뒤에 다시 보낼 수 있어요", 코드 메일 보내기 실패 → "메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요"
  - 기존 `test_ui_flow.py`의 카테고리 수·문구 테스트는 건조기에 맞게 고친다(바뀐 사실만, 의도 그대로).
- [ ] **Step 3:** FAIL 확인 → 테스트 커밋.
- [ ] **Step 4:** 구현. 화면은 디자인 가이드 CSS 변수만. 모델명 찾는 법 안내는 1.5차 것 재사용.
- [ ] **Step 5:** `node --test tests/web/js/` · `pytest -m "not integration" -v`(ui 포함) · `measure/a11y.py`(axe) 통과. web-design-guidelines 점검 결과를 개발일지에. 구현 커밋.

### Task 7: 알림 주소 — 운영자·요청자 메일

**Files:**
- Create: `app/notify/__init__.py`, `app/notify/routes.py`, `app/notify/mail.py`, `app/notify/users.py`, `app/notify/messages.py`
- Modify: `app/web.py`(라우터 추가), `requirements.txt`(`httpx==0.28.1`, 지금 dev와 같은 판을 실행 의존성으로)
- Test: `tests/notify/test_notify_routes.py`, `tests/notify/test_messages.py`

**Interfaces:**
- Consumes: Task 5 Settings, `app.catalog.registry.load_models`
- Produces:
  - `POST /api/notify` — 헤더 `x-pyeobom-webhook-secret`를 `hmac.compare_digest`로 확인(틀리거나 없으면 401, 본문 안 읽음). 본문은 Supabase 데이터베이스 웹훅 형식(`type`, `table`, `record`, `old_record` — 필드 이름은 Context7로 확인 후 테스트에 고정). 응답 `{"sent": "operator" | "requester" | "none", "reason": str}`
  - `send_mail(to: str, subject: str, text: str, *, reply_to: str | None = None, post=httpx.post) -> None` (Resend API, 실패면 `MailError`)
  - `get_user_email(user_id: str, *, get=httpx.get) -> str` (Supabase 관리 API, service 키)
  - `operator_message(record: dict) -> tuple[str, str]`, `requester_message(record: dict, model_name: str | None) -> tuple[str, str]`
- 메일 문구(Claude 판단): 운영자 — 제목 "[펴봄] 새 모델 요청 #<id>", 본문 카테고리·브랜드·모델명·요청 시각(요청자 정보 없음). 요청자 추가됨 — 제목 "요청하신 모델이 펴봄에 추가됐어요", 본문 "<브랜드> <모델명>을 이제 물어볼 수 있어요. https://pyeobom.help". 요청자 추가 어려움 — 제목 "요청하신 모델을 추가하지 못했어요", 본문 사유 + "궁금한 점은 이 메일에 답장해 주세요". 답장 주소는 `OPERATOR_EMAIL`.
- 규칙: INSERT → 운영자에게. UPDATE → `old_record.status != record.status`이고 새 status가 `추가됨`·`추가 어려움`일 때만 요청자에게. `추가됨`인데 `record.model_id`가 **이 배포의 models.json에 없으면** 보내지 않고 `reason: "not_deployed"`(Review Focus 5). 로그에는 요청 id·status·결과만(이메일·모델명 안 남김). 메일 실패는 502 + 로그(주소 가림). **다시 보내기 = 표 화면에서 status를 `확인 중`으로 되돌렸다가 다시 바꾸기**(설계 8.2-4, Claude 판단).

- [ ] **Step 1: 실패 테스트** (메일·관리 API는 가짜 함수로, 네트워크 0):
  - `test_rejects_missing_or_wrong_secret` · `test_insert_sends_operator_mail_without_requester_email`
  - `test_status_added_sends_requester_mail_with_reply_to_operator` · `test_status_hard_sends_reason`
  - Review Focus 2 `test_update_same_status_sends_nothing`, `test_update_other_column_sends_nothing`
  - Review Focus 5 `test_added_but_not_deployed_sends_nothing`
  - `test_mail_failure_returns_502_and_logs_no_address` · 메일 문구에 이메일·키가 없음
- [ ] **Step 2~4:** FAIL → 테스트 커밋 → 구현 → 통과 → 구현 커밋.
- [ ] **Step 5: 미리보기에서 한 번** — 미리보기는 Vercel 로그인 보호가 있어, 웹훅 시험은 `x-vercel-protection-bypass` 헤더를 함께 넣는다(지금 `measure/load_common.py` 방식). 시험 계정으로 요청 1건 → 운영자 메일 도착 확인. Resend 하루 한도 안에서.
- [ ] **Step 6: 브랜치 마무리 전 검토** — security-audit 스킬을 **이 브랜치에서 바뀐 파일만** 대상으로 실행하고 결과를 개발일지에. `requesting-code-review`(서브에이전트 Opus · xhigh). 지적 처리 → 마무리(Task 4~7 한 PR). 병합 뒤 U7(웹훅 등록) → 운영에서 1건 확인.

### Task 8: 모델 추가 도구 — 검사·초안·적재·가이드 연결·되돌리기

**브랜치:** `feat/phase2-add-model-tool` · **언제:** 3일차

**Files:**
- Create: `ingest/add_model.py`(CLI `python -m ingest.add_model <명령>`)
- Modify: `ingest/__main__.py` — 본문을 `ingest_document()`로 옮기고 `main()`은 그것을 부름(동작 그대로)
- Test: `tests/ingest/test_add_model.py`, `tests/ingest/test_db_connection_rule.py`

**Interfaces:**
- Produces:
  - `ingest_document(doc_id: str, *, connect=get_conn, embed=embed_texts) -> dict` — 임베딩을 **먼저** 다 만든 뒤 연결을 열어 `save()`하고 바로 닫음. 반환 `{"doc_id", "chunks", "dropped"}`
  - `check_document(doc: dict) -> dict` — `{"pages", "text_pages", "empty_pages", "remaining_markers": [(page, count)], "ok"}`. 글자 없는 PDF 판단(Claude 판단): 공백을 뺀 글자가 30자 미만인 쪽이 절반을 넘으면 실패. 쪽 표시 남음: `ingest.page_marker.count_remaining_markers`가 0이 아닌 쪽이 하나라도 있으면 실패(설계 9.2). 지금 설명서 3개는 둘 다 통과해야 한다.
  - `draft_entries(*, doc_id, model_id, brand, appliance, title, source_url, pdf, codes: list[str], fetched_at) -> tuple[dict, dict]` — documents.json·models.json 항목 초안(이미 있는 id면 `ValueError`). `--write`일 때만 파일에 덧붙임.
  - `link_guide(guide_id: str, model_id: str, *, connect=get_conn) -> bool` — `INSERT INTO document_models … ON CONFLICT DO NOTHING` 한 번 + documents.json의 그 가이드 `model_ids`에도 추가. 조각은 안 건드림(Global 9). 새로 넣었으면 True.
  - `remove_model_data(doc_id: str, model_id: str, *, connect=get_conn, yes: bool = False) -> dict` — 지울 개수만 세어 보여 주고, `yes=True`일 때만 그 문서의 `chunks`·`document_models`·`documents` 행과 그 모델의 가이드 연결 행을 한 트랜잭션으로 지움. `bundle_chunks`·다른 문서는 안 건드림(설계 9.3-12).
  - `error_code_candidates(doc: dict) -> list[str]` — 설명서 글에서 코드처럼 생긴 글자(예: `4E`, `dE`, `CH10`)를 뽑아 사람이 error_codes.json을 채울 때 보게 함(설계 9.2, 밀리면 먼저 뺌)
  - 명령: `check`, `draft`, `codes`, `ingest`(장부 확인 뒤), `link-guide`, `remove`(`--yes`는 사용자 확인 뒤에만 Claude Code가 붙임)
- 참고(코드로 확인함): 질문 API는 `validate_model_id`로 models.json에 없는 모델을 거절한다. 그래서 조각을 DB에 먼저 넣어도 models.json을 배포하기 전에는 새 모델이 화면·질문 API에 열리지 않는다(설계 8.3·14-11).

- [ ] **Step 1: 실패 테스트 — DB 연결 규칙 (사용자 요청)** 공용 검사 `assert_no_ai_while_open(events: list[str]) -> None`을 `tests/ingest/db_rule.py`에 두고(Task 9도 씀), `tests/ingest/test_db_connection_rule.py`에서 가짜 `connect`(열기·닫기를 사건 목록에 적는 컨텍스트 관리자)와 가짜 `embed`(호출을 사건 목록에 적음)를 넣어 `ingest_document`, `link_guide`, `remove_model_data`를 돌린 뒤 확인:
  - 열린 연결 사이(`open`~`close`)에 `ai`·`file`·`sleep` 사건이 없음
  - 모든 `open` 뒤에 `close`가 있음(예외가 나도 닫힘 — 가짜 `save`가 예외를 던지는 경우 포함)
  - `ingest_document`는 `embed`가 끝난 뒤에야 `open`
- [ ] **Step 2: 실패 테스트 — 기능**: `test_check_flags_textless_pdf`(글자 없는 쪽이 많은 가짜 쪽 목록), `test_check_flags_remaining_page_marker`, `test_existing_three_manuals_pass_check`(로컬 PDF가 있을 때만, 없으면 skip), `test_draft_refuses_existing_id`, `test_link_guide_does_not_touch_chunks`(가짜 연결에 보낸 SQL에 `chunks`가 없음), `test_remove_without_yes_deletes_nothing`, `test_ingest_main_behaves_as_before`.
- [ ] **Step 3~5:** FAIL → 테스트 커밋 → 구현 → `pytest -m "not integration" -v` 통과 → 구현 커밋.

### Task 9: 확인 질문 실행·판정지·합격 판정·체크리스트

**Files:**
- Modify: `ingest/add_model.py` (명령 `confirm`, `verdict`, `checklist`)
- Test: `tests/ingest/test_add_model_confirm.py`

**Interfaces:**
- Consumes: Task 2 `validate_confirm_set`, `passes`, `measure.budget.check_budget`, `app.ask.routes.get_deps`, `app.ask.service.answer_question`(운영과 같은 답변 경로, 바꾸지 않음)
- Produces:
  - `run_confirm(model_id: str, questions_path: str, *, expect_sha256: str, label: str, answer=answer_question, deps_factory=get_deps) -> Path` — 파일 해시가 다르면 실행하지 않음. `evaluation/phase2/ledger.csv` + 예상 비용으로 `check_budget(..., cap_usd=1.0)` 실패면 실행하지 않음. 질문 10개를 차례로 묻고 결과 CSV `evaluation/results/phase2-<model_id>-<label>.csv`(질문·답·인용 쪽·found·시간)와 판정지 `measure/out/phase2/<model_id>-<label>-judge.md`(설명서 글 포함 가능, git 밖)를 씀. 연결은 `get_deps`의 검색이 그때그때 열고 닫는다(Global 8).
  - `verdict` 명령: 판정 CSV → `passes()` 결과를 출력하고 리포트에 붙일 한 줄을 만듦
  - `checklist` 명령: 설계 8.3 순서(적재 → 로컬 확인 질문 → 합격 → PR 병합·운영 화면 확인 → 그 뒤에만 "추가됨")를 모델 id와 함께 출력
- 032 다시 볼 조건(설계 9.3-9): 판정 CSV에 `note` 열이 "다른 코드 절차"면 `verdict`가 "결정기록 032 근거로 기록" 줄을 함께 출력(다시 정하기는 2차 뒤).

- [ ] **Step 1: 실패 테스트**: `test_run_confirm_follows_db_rule`(Task 8의 `assert_no_ai_while_open`, 가짜 deps의 검색이 열기·닫기를 적고 답변 호출은 `ai`로 적음), `test_confirm_refuses_hash_mismatch`, `test_confirm_refuses_over_budget`, `test_confirm_writes_results_without_calling_network`(가짜 answer·deps), `test_verdict_prints_pass_and_032_note`, `test_checklist_order`.
- [ ] **Step 2~4:** FAIL → 테스트 커밋 → 구현 → 통과 → 구현 커밋 → `requesting-code-review` → 마무리(Task 8~9 한 PR).

### Task 10: 후 측정 — 비교용 모델 다시 넣기, 실제 요청 모델

**언제:** 4일차 · **필요:** Task 8~9 병합, U8

- [ ] **Step 1: 되돌리기** (`chore/model-<id>-remove`): models.json·documents.json·예시·일러스트에서 비교용 모델을 빼는 PR → 병합. `remove --doc-id … --model-id …`로 개수 확인 → **멈추고 사용자 확인** → `--yes`. 운영 화면에서 사라짐 확인.
- [ ] **Step 2: 도구로 다시 넣기** (`feat/model-<id>-readd`): 새 기록지(`…-after.timelog.csv`), 같은 PDF·같은 확인 질문 파일(해시 같음). `draft --write` → `check` → `ingest` → `link-guide` → `confirm` → 판정 → `verdict` → PR 병합 → 운영 화면 확인. `summarize()`·`improved()` 결과를 리포트에.
- [ ] **Step 3: 실제 요청 모델 최대 2개** (`feat/model-<요청 모델 id>`): 표 화면에서 status `확인 중` → 같은 순서로 추가 + 기록지(기록만, 개선 판정에는 안 씀). 합격 → 병합 → 운영 확인 → status `추가됨`(+`model_id`) → 요청자 메일 확인. 미달·글자 없는 PDF·설명서 못 찾음 → `추가 어려움` + 사유.
- [ ] **Step 4: 결론** — 리포트에 전·후 표, 합격 판정, 한계(손에 익는 효과, 표본 작음, 설계 9.3-10), 장부 실제 비용. `docs/결정기록/040-2차-모델-추가-결론.md`(개선 / 개선 확인 못 함). 결론 문장은 `improved()` 결과 그대로.

### Task 11: Playwright 실제 흐름 테스트, "내 요청" 카드(목표), Supabase 깨우기

**브랜치:** `feat/phase2-qa` · **언제:** 4일차, 코드 동결 전

**Files:**
- Create: `tests/e2e/test_request_flow_live.py` (`integration`: 미리보기 주소 + 우회 헤더, Resend 받기 시험 주소 2개로 로그인 → 요청 → 다른 계정에서는 안 보임. 인증 코드는 Resend 받기 API로 읽음 — 주소·응답 형식은 Context7·공식 문서로 확인)
- Modify: `pytest.ini`의 `integration` 설명을 "실제 외부 서비스(OpenAI·Neon·Supabase·Resend)에 연결하는 테스트"로 넓힘 (새 표시 이름을 만들지 않음, Claude 판단)
- Modify: `public/js/request.js`·`public/app.js`·`public/index.html` — 첫 화면 "내 요청" 카드(대기 / 확인 중 / 추가됨 / 추가 어려움, 로그인했을 때만)
- Create: Supabase 깨우기 예약(방법은 Vercel Cron 한도·GitHub Actions 예약을 공식 문서로 비교해 정함. 설계 14-5 "2차가 끝나기 전에")
- Test: `tests/web/test_ui_request.py`에 `test_my_requests_card_shows_status`

- [ ] **Step 1:** 실패 테스트(카드) → 테스트 커밋 → 구현 → 통과 → 구현 커밋.
- [ ] **Step 2:** 실제 흐름 테스트 작성 → 미리보기에서 1회 실행(Resend 한도 안, OpenAI 0) → 결과를 개발일지에. 녹화가 필요하면 Playwright 영상 저장을 켜서 시연 영상 재료로 쓴다(시험 계정만).
- [ ] **Step 3:** 깨우기 예약 추가 → 마무리 → **코드 동결**.

### Task 12: 제출물 (문서만)

**브랜치:** `docs/phase2-submission` · **언제:** 4일차 밤~5일차 아침 9시

- [ ] README: 실행 방법, 고른 메뉴 표(Supabase DB, Playwright QA, 자동화(웹훅→메일)), AI 사용 지도(채팅 Claude / Claude Code / 스킬), 배포 주소 pyeobom.help
- [ ] `prompts/`: `docs/프롬프트.md`·`docs/프롬프트-기록.md`에서 v1→v2 옮기기(2차 새 프롬프트 없음)
- [ ] PRD.md·db.md·CLAUDE.md 최종 확인, 위임 로그(6칸 양식은 멘토 확인 뒤), `제출서.md`
- [ ] 시연 영상 1~3분(설계 12-3 흐름): Playwright 녹화는 **저장소 밖 작업 폴더**에서(watch가 현재 폴더 `.env`를 읽음), ffmpeg-usage로 편집(자를 때 다시 인코딩, 한글 자막 글꼴 지정), `/watch`로 점검(local·받아쓰기 none). 실제 영상으로 watch를 처음 돌리는 날이므로 4일차 낮에 짧은 영상으로 한 번 먼저 돌려 본다.
- [ ] 발표 자료: 채팅 Claude 슬라이드 기능, 4일차부터. 화면 그림은 Playwright 캡처(시험 계정), 문구는 im-not-ai, 숫자는 리포트 원문과 대조.
- [ ] 최종 검토(서브에이전트 Opus · xhigh) → 병합 → 10시 제출.

---

## 계획에서 정한 것 (Claude 판단, 사용자가 고칠 수 있음)

1. **pytest-playwright는 설치하지 않는다.** 지금 화면 테스트(`tests/web/test_ui_flow.py`)가 Playwright sync API를 직접 쓰고 `playwright 1.64.1`이 이미 `requirements-dev.txt`에 있다. 같은 방식으로 쓴다.
2. **가이드는 다시 적재하지 않고 `document_models`에 연결만 한다**(Global 9). 지금 방식(전 측정)에서도 SQL 한 줄로 연결한다.
3. **공개 키도 저장소에 쓰지 않고 `/api/public-config`로 준다.**
4. **모델명 정규화는 DB 생성 열이 기준**이고 화면은 같은 사례 파일로 맞춘다.
5. **알림 주소가 배포 여부를 스스로 확인한다**(models.json에 없으면 "추가됨" 메일을 안 보냄).
6. **Supabase 지역은 서울**, 요청 표 이름은 `model_requests`, 카테고리 코드는 `washer·dryer·aircon`.
7. **새 테스트 표시 이름을 만들지 않고** `integration` 설명만 넓힌다.
8. 측정 스크립트 운영 주소 막기에 pyeobom.help를 더한다(설계 15-5 확인 결과).
9. 2026-11-20에 사용자 범위로 설치한 스킬·플러그인 3개는 CLAUDE.md 규칙대로 프로젝트 범위로 옮긴다(Task 1 Step 6, 2026-11-21 사용자 "추천대로").

## 아직 확인할 것 (계획 실행 중 공식 문서로)

1. Supabase 웹훅 본문 필드 이름과 헤더 넣는 방법(설계 15-4), 관리 API로 시험 세션 만드는 방법, 새 키(publishable/secret)의 헤더 차이.
2. Resend 받기 API 주소·응답 형식(인증 코드 읽기).
3. Vercel에서 옛 주소를 넘겨주는 방식(설계 15-3), 미리보기 주소를 Supabase 돌아올 주소에 넣는 방법(와일드카드).
4. 깨우기 예약에 쓸 Vercel Cron 무료 한도.
