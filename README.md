# 펴봄 — 가전 설명서, 대신 펴 봐 드려요

자취생이 세탁기·에어컨 모델을 고르고 질문하면, **그 모델의 공식 설명서와 제조사 공식 해결 가이드에서 근거를 찾아** 쪽 번호·짧은 인용과 함께 답하는 웹 서비스입니다. 근거가 없으면 지어내지 않고 "설명서에서 찾지 못했어요"라고 답합니다.

- 운영 주소: https://pyeobom.help
- 옛 주소 https://pyeobom.vercel.app 도 아직 응답합니다.
- 노션 주소: https://app.notion.com/p/Q-A-4068ea8ed10081a69794cddee580935c?source=copy_link
- 비영리 학습용 포트폴리오입니다. 설명서 저작권은 각 제조사에 있습니다.
- 지원 모델(1차): 삼성 BESPOKE AI 콤보 세탁건조기, LG 드럼세탁기, LG 벽걸이 에어컨(`data/models.json`)
- 2차: 지원 모델에 없는 가전·모델은 로그인한 뒤 요청할 수 있고, 요청이 추가되면 메일로 알려 줍니다. 2차에 요청 #44로 LG 드럼세탁기 FX21을 더해 운영 모델은 4개입니다(PR #102, 결정기록 044).

## 구조

```mermaid
flowchart TD
  U[휴대폰 브라우저<br>public/ 화면<br>대화는 브라우저에만 저장] -->|POST /api/ask<br>질문 + 앞 대화 최대 3턴| F[Vercel 함수 sin1<br>FastAPI index.py]
  F --> G[입력 검사<br>개인정보 가리기<br>다른 브랜드 질문은 AI 없이 안내]
  G --> R[질문 바꾸기<br>앞 대화가 있을 때만]
  R --> E[OpenAI 임베딩<br>text-embedding-3-small]
  E --> S[(Neon Postgres + pgvector<br>ap-southeast-1)]
  S -->|선택 모델의 조각만| P[프롬프트 v1]
  P --> L[OpenAI 답변<br>gpt-6-luna]
  L --> V[근거 검증<br>인용이 조각에 그대로 있는지]
  V -->|답 + 쪽 번호 + 인용<br>또는 찾지 못함| U
  M[설명서 PDF·가이드 HTML<br>로컬에만] -->|python -m ingest| S
```

| 폴더 | 하는 일 |
|---|---|
| `index.py`, `app/web.py` | Vercel 진입점, API 조립 |
| `app/input_guard/` | 빈 질문·길이·모델 검사, 개인정보(전화·이메일·주소) 가리기 |
| `app/retrieval/` | 임베딩, 모델 필터 검색, 에러 코드 → 진단 안내 쪽 덧붙이기 |
| `app/answer/` | 프롬프트, OpenAI 호출(타임아웃·재시도), 답변 검증 |
| `app/ask/` | `POST /api/ask` 흐름 |
| `public/` | 화면(v1.5 채팅형, 정적 HTML·CSS·JS, Vercel CDN). `js/store.js` 대화 저장, `js/history.js` 앞 대화, `js/evidence.js` 근거 접기 |
| `ingest/` | 전처리(로컬): PDF·HTML → 조각 → 임베딩 → Neon |
| `evaluation/` | 평가(로컬): 테스트 질문 30개, 채점, 리포트 |
| `supabase/schema.sql` | 2차: 모델 요청 표 `model_requests`·RLS·권한(Supabase, `db.md`) |
| `app/notify/` | 2차: 알림 주소 `POST /api/notify`(Supabase 데이터베이스 웹훅 → 운영자·요청자 메일, Resend) |
| `app/wake/` | 2차: Supabase 깨우기 `GET /api/wake`(Vercel Cron 하루 3번) |
| `ingest/add_model.py` | 2차: 모델 추가 도구 `python -m ingest.add_model`(검사·초안·적재·가이드 연결·확인 질문·판정) |

- 2차 요청 흐름: 화면이 Supabase에 바로 로그인·요청하고(공개 값은 `/api/public-config`), 본인 요청만 읽히는 것은 RLS가 맡습니다. 요청이 들어오거나 상태가 바뀌면 데이터베이스 웹훅이 `/api/notify`를 불러 메일을 보냅니다(`db.md`, 결정기록 043).

## 화면 흐름 (v1.5, 2026-11-11)

1. **랜딩**(처음 열면 항상): 서비스 소개와 "시작하기", 최근 대화 1개
2. **카테고리:** 세탁기·에어컨 타일(더 추가 예정), 최근 대화 3개. 2차에 건조기 타일을 더함(등록된 모델 없음)
3. **모델 선택:** 모델 카드(AI 일러스트, 모델 코드, "모델명 찾는 법"). 2차: [내 모델이 없어요] → 로그인(메일 코드·구글) → 내 모델 요청하기
4. **채팅:** 질문 → 답. 근거는 쪽 번호가 보이는 접힌 한 줄이고, "공식 설명서를 드릴까요?"를 누르면 공식 링크가 나옵니다. 이어지는 질문은 앞 대화로 질문을 바꿔 찾고 "'○○'로 찾았어요"로 보여 줍니다
5. **지난 대화(☰ 서랍):** 대화 다시 열기, 하나 지우기, 전체 삭제
6. **내 요청(2차):** 로그인했고 요청이 있으면 첫 화면에 "내 요청 N건" 요약이 보이고, 누르면 요청마다 상태(대기·확인 중·추가됨·추가 어려움)를 봅니다(PR #106)

- 대화는 **이 기기의 브라우저에만** 저장되고, 개인정보를 가린 질문만 저장합니다(결정기록 022). ~~로그인은 없습니다.~~ → 질문에는 로그인이 없고, 모델을 요청할 때만 로그인합니다(2차).
- 화면 결정은 결정기록 021(흐름), 024(디자인 체계), 025(제품 그림)에 있습니다.

## 고른 메뉴 (2차, `PRD.md` 6.3)

| 메뉴 | 어디에 썼나 | 맡은 사람 |
|---|---|---|
| Supabase DB | 로그인(메일 코드·구글)과 모델 요청 표 `model_requests`. RLS로 본인 요청만 읽히고, 넣기는 세 열만, 같은 모델 다시 요청·하루 5개 넘는 요청은 DB가 막음(`supabase/schema.sql`, `db.md`, PR #94). 요청이 들어오거나 상태가 바뀌면 데이터베이스 웹훅 → `/api/notify` → 메일(`app/notify/`, PR #94·#95). 첫 화면 "내 요청"은 화면이 RLS로 바로 읽음(PR #106). 무료 프로젝트가 멈추지 않게 하루 3번 1줄 읽기(`app/wake/`, PR #108) | 본인(개인 프로젝트) |
| Playwright QA | 가짜 Supabase로 요청 화면을 도는 화면 테스트(`tests/web/test_ui_request.py`, PR #94·#106). 운영 주소에서 실제 메일 코드로 두 계정이 로그인해, 요청이 그 계정의 "내 요청"에만 보이고 다른 계정에는 안 보이는지 확인하는 실제 흐름 테스트(`tests/e2e/test_request_flow_live.py`, PR #107). 접근성 점검(axe)에 "내 요청" 화면 상태를 더함(`measure/a11y.py`, PR #106) | 본인(개인 프로젝트) |
| MCP | Context7: Supabase·Resend 공식 문서 확인(로그인 흐름·웹훅 본문·관리 API·메일 보내기, 개발일지 2026-11-25). Supabase 연결 도구: 채팅 Claude가 운영 DB를 읽기만 해서 `schema.sql` 최종 상태와 같은지 확인(개발일지 2026-11-25·11-26). 구조 SQL은 MCP로 실행하지 않고 사용자가 SQL 편집기에서 실행. Notion: 상호 테스트 따라 하기 가이드 페이지(채팅 Claude, 개발일지 2026-11-26) | 본인(개인 프로젝트) |
| 서브에이전트·훅·스킬 | Superpowers 스킬(계획대로 실행 `executing-plans`, 테스트 먼저 `test-driven-development`, 끝나기 전 확인 `verification-before-completion`), 계획 끝 최종 검토 서브에이전트(`requesting-code-review`, 개발일지 2026-11-24), 보안 점검 `security-audit`(바뀐 파일만, 개발일지 2026-11-25·11-26·11-28, PR #87에서 프로젝트 범위로), Supabase 공식 스킬 `supabase`·`supabase-postgres-best-practices`(요청 표·RLS, PR #94). 스킬은 `.claude/skills/`(출처·라이선스는 아래 "외부 스킬과 라이선스"). 프로젝트 훅은 쓰지 않음(`.claude/settings.json`에 훅 없음) | 본인(개인 프로젝트) |
| RAG 챗봇 | 1차부터 직접 만든 설명서·공식 가이드 기반 Q&A, LangChain 없음. 고른 모델의 조각만 pgvector로 찾고(`app/retrieval/`) → 답변 AI가 근거 조각과 인용을 함께 냄(`app/answer/`, 프롬프트는 [prompts/](prompts/README.md)) → 인용이 검색된 조각에 그대로 있는지 검사(`app/answer/check.py`, 어긋나면 한 번 더 묻고 또 어긋나면 "찾지 못함"). 2차에 모델 추가 도구로 새 설명서를 더함(`ingest/add_model.py`, PR #98·#102). 멘토 답(2026-11-25)에 따라 메뉴에 넣음(`PRD.md` 6.3) | 본인(개인 프로젝트) |

- 웹훅 → 메일은 메뉴의 "n8n 자동화"가 아니라서 메뉴로 세지 않고 기능 설명에 둡니다(2차 계획 덧붙임 C-2).

## AI 사용 지도 (2차)

| 부분 | 만든 도구(누가) | 쓴 프롬프트·스킬 | 사람이 결정한 것 |
|---|---|---|---|
| 기획·설계 | 채팅 Claude가 설계·계획 초안과 짧은 설계를 쓰고 사용자가 승인. Claude Code는 받은 파일의 SHA-256을 대조해 저장소에 넣음 | Superpowers 계획 형식(계획 머리말의 `executing-plans` 안내). 1차 기획 때는 `brainstorming`·`writing-plans`(`docs/프롬프트.md` 2부) | 고른 메뉴 표(2026-11-23, 덧붙임 C-2)와 RAG 챗봇 넣기(멘토 답 2026-11-25), Supabase 깨우기는 Vercel Cron으로(2026-11-28) (`PRD.md`, 2차 계획 덧붙임, `docs/superpowers/specs/2026-11-28-supabase-wake-design.md`) |
| 구현 | Claude Code | `executing-plans`·`test-driven-development`(테스트 커밋 → 구현 커밋), 화면은 `frontend-design`, Context7로 공식 문서 확인 | 하루 5개 제한을 정책 대신 트리거로(2026-11-25), "내 요청"은 화면이 Supabase에서 바로 읽는 방법으로(2026-11-27) (`CLAUDE.md` "스킬", 개발일지 2026-11-25, `docs/superpowers/specs/2026-11-27-my-requests-design.md`) |
| 측정·평가 | Claude Code(측정 실행·판정 코드·시간 기록), 사용자·채팅 Claude(답 판정) | `docs/평가/평가-규칙.md`, 장부와 `check_budget`(AI 비용은 먼저 적음) | 비교용 모델과 시간 규칙을 측정 전에 정함, 판정은 사용자와 채팅 Claude가 함께(2026-11-24) (개발일지 2026-11-24, 결정기록 044) |
| 테스트·QA | Claude Code | pytest, Playwright(가짜 Supabase 화면 테스트·실제 흐름 테스트), axe 접근성 점검(`measure/a11y.py`), `verification-before-completion` | 실제 흐름 테스트는 두 계정 모두 실제 메일 코드로 운영 주소에서, 녹화하되 받기 주소 글자를 가림(2026-11-27) (`docs/superpowers/specs/2026-11-27-live-flow-test-design.md`, 개발일지 2026-11-27) |
| 보안 점검 | Claude Code(바뀐 파일 소스 읽기), 채팅 Claude(Supabase 연결 도구로 운영 DB 읽기만) | `security-audit`(guidance 모드), Supabase 공식 스킬, push 전 점검(키·uuid·메일 주소 모양을 개수로) | 구조 SQL은 MCP·CLI로 실행하지 않고 사용자가 SQL 편집기에서(2026-11-25), OpenAI `store=False`(2026-11-25) (`CLAUDE.md`, 개발일지 2026-11-25) |
| 기록(개발일지·결정기록) | Claude Code가 쓰고, 채팅 Claude가 대조 | `CLAUDE.md` 작업 규칙(결정한 것은 사용자 결정 / Claude 판단, AI 실수는 채팅 Claude / Claude Code로 나눔) | push 전 점검 규칙(2026-11-25), 테스트 커밋 → 구현 커밋 순서를 다시 지키기(2026-11-25) (`CLAUDE.md`, 개발일지 2026-11-25, `docs/AI-실수-기록.md`) |
| 시연 영상 | Claude Code(운영 화면 녹화, Playwright), 사용자(영상 스킬 채팅창에서 편집·음성 합성), 채팅 Claude(시나리오·답 판정·완성본 확인) | Playwright 녹화, 영상 스킬 채팅창, 음성 합성(Gemini TTS) | 녹화한 답의 판정 확정, v2를 최종본으로(2026-11-28) (개발일지 2026-11-28) |
| 발표 자료 | 진행 중 | 진행 중 | 1차 대비 디자인 변천은 영상이 아니라 발표 자료 한 장으로(2026-11-28) (개발일지 2026-11-28) |

- 역할: 채팅 Claude는 설계·계획·판정·지시 블록, Claude Code는 저장소 작업(코드·테스트·측정 실행·기록·PR), 병합·push는 사용자 승인 뒤(`CLAUDE.md` "브랜치 전략").
- AI가 틀린 일은 `docs/AI-실수-기록.md`에 한 줄씩 남깁니다(채팅 Claude / Claude Code 구분).

## 로컬 실행

**필요한 것:** Python 3.14(Windows는 `py` 런처), Git, Neon 계정(무료), OpenAI API 키

아래 명령은 Windows의 **Git Bash** 기준입니다. PowerShell·명령 프롬프트에서는 `.venv/Scripts/python`을 `.venv\Scripts\python`으로 바꿔 입력합니다.

```bash
git clone https://github.com/mini-cs/pyeobom.git
cd pyeobom
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -m "not integration"   # 여기까지는 키·DB·설명서 없이 됩니다
```

- 마지막 줄은 모두 통과해야 합니다. 해결 가이드 HTML(`data/guides/`)을 받기 전에는 테스트 1개가 건너뛰어집니다(skipped).
- 설치는 1~2분 걸립니다.

`.env.example`을 `.env`로 복사하고 비밀 값 두 개만 직접 채웁니다. 나머지는 예시 값 그대로 써도 됩니다.

```bash
OPENAI_API_KEY=sk-...                                   # OpenAI API 키
DATABASE_URL=postgresql://user:password@host/db?sslmode=require   # Neon 접속 주소
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL=gpt-6-luna
EMBED_DIM=1536
OPENAI_REASONING_EFFORT=low
SEARCH_MODE=vector
```

- `.env`는 커밋되지 않습니다(`.gitignore`). 비밀 값을 화면·로그·커밋 메시지에 남기지 마세요.
- 2차 기능(로그인·모델 요청·알림 메일·깨우기)을 로컬에서 쓰려면 아래 이름도 채웁니다. 값은 여기에 적지 않습니다. Supabase 요청 표는 `supabase/schema.sql`(`db.md`)로 만듭니다.

```bash
SUPABASE_URL=            # 로그인·요청(화면에 내려가는 공개 값)
SUPABASE_ANON_KEY=       # 공개 키(화면에 내려가는 공개 값)
SUPABASE_SERVICE_KEY=    # 비밀 키(서버 전용: 알림 메일의 요청자 메일 찾기, 깨우기)
RESEND_API_KEY=          # 알림 메일 보내기
NOTIFY_WEBHOOK_SECRET=   # 웹훅 → /api/notify 인증
OPERATOR_EMAIL=          # 운영자 알림을 받을 주소
MAIL_FROM=               # 보내는 주소
CRON_SECRET=             # 깨우기 /api/wake 인증(운영 Vercel Production에만, 로컬은 비워 둠)
```

- 운영 비밀 값은 Vercel 대시보드에만 있습니다(저장소·`.env.example`에는 이름만).
- 실제 흐름 테스트 전용 이름 `RESEND_RECEIVING_API_KEY`·`RESEND_RECEIVING_DOMAIN`·`E2E_BASE_URL`은 로컬에만 두고 Vercel에는 넣지 않습니다(`.env.example` 주석).

## 설명서·가이드 받기 (원본은 저장소에 없음)

설명서 PDF와 가이드 HTML은 저작권 때문에 저장소에 넣지 않았습니다(결정기록 009). 아래 공식 페이지에서 직접 받아 **`data/documents.json`의 `file` 경로와 같은 이름**으로 저장합니다.

| 문서 | 받는 곳 | 저장 위치 |
|---|---|---|
| 삼성 세탁건조기 설명서 | 삼성전자서비스 다운로드 자료실(https://www.samsungsvc.co.kr/download)에서 `WD90H25AHTN1`로 검색해 받음(표지 모델명 `WD90H25AH*` 계열) | `data/manuals/OID140081_IB_WD80H-AD_7LCD_KO_260331.pdf` |
| LG 드럼세탁기 설명서 | LG전자 제품 설명서(https://www.lge.co.kr/support/product-manuals)에서 `FX24GNG`로 검색해 받음(표지 모델명 `FX25*N*`/`FX24*N*`/`FX23*N*`, 문서 번호 `MFL71792818`) | `data/manuals/WM_KOR_MFL71792818_10_251204_00_OM_WEB.pdf` |
| LG 벽걸이 에어컨 설명서 | 같은 페이지에서 `SQ06FA1WDS`로 검색해 받음(공용 설명서, 문서 번호 `MFL71890636`) | `data/manuals/[CW_RAC_24515]_250626_MFL71890636_01_Domestic_2025_WLM_2LED_CO.pdf` |
| LG 드럼세탁기 FX21 설명서(2차) | 같은 페이지에서 받음(표지 모델명 `FX21*NC`, 문서 번호 `MFL71792820`) | `data/manuals/WM_KOR_MFL71792820_06_251204_00_OM_WEB.pdf` |
| 해결 가이드 8개 | `data/documents.json`의 각 `source_url` | `data/guides/<id>.html` |

- 가이드는 브라우저에서 **"웹페이지 전체 저장"**으로 저장합니다. 인쇄(PDF 저장)를 하면 탭 안에 숨은 설명이 빠질 수 있습니다.
- 파일 이름이나 판이 달라졌다면 `data/documents.json`의 `file`을 맞추고, 쪽 번호가 바뀌었는지 확인합니다.

## 적재 (Neon)

1. Neon SQL Editor에서 `ingest/schema.sql`을 한 번 실행합니다. vector 확장과 테이블 3개(`documents`, `document_models`, `chunks`)가 만들어집니다.
2. 문서 11개(2차에 FX21 설명서를 더해 지금 `data/documents.json`은 12개)를 하나씩 적재합니다.

```bash
# Git Bash
for id in $(.venv/Scripts/python -c "import json;print(' '.join(d['id'] for d in json.load(open('data/documents.json',encoding='utf-8'))))"); do
  .venv/Scripts/python -X utf8 -m ingest --doc-id "$id"
done
```

```powershell
# PowerShell
(Get-Content data/documents.json -Encoding utf8 -Raw | ConvertFrom-Json).id | ForEach-Object { .venv\Scripts\python -X utf8 -m ingest --doc-id $_ }
```

- 문서마다 "조각 N개, 적용 범위 밖이라 뺀 문단 M개"가 출력됩니다. 전체 약 332개가 나와야 합니다(1차 문서 11개 기준). 2차에 더한 FX21 설명서는 조각 106개였습니다(개발일지 2026-11-27).
- 같은 문서를 다시 적재하면 그 문서의 기존 조각을 지우고 새로 넣습니다.

## 실행과 테스트

```bash
.venv/Scripts/python -m pytest -v -m "not integration"   # 기본 테스트(키·DB 없이)
.venv/Scripts/python -m pytest -v -m integration         # 실제 외부 서비스(OpenAI·Neon·Supabase·Resend) 연결 테스트(.env 필요)
.venv/Scripts/python -X utf8 experiments/dev_server.py   # 화면 + API → http://127.0.0.1:8765
```

- 2차 integration 테스트: `tests/requests/test_rls_live.py`(실제 Supabase RLS·제약), `tests/e2e/test_request_flow_live.py`(운영 주소에서 실제 메일 코드 로그인 → 요청 → 다른 계정에서는 안 보임, 만든 계정은 끝나면 지움).
- `dev_server.py`는 로컬 확인 전용입니다. 배포에서는 `public/`을 Vercel CDN이 제공합니다(결정기록 013).
- 디버그: `POST /api/ask?debug=true`이면 검색된 근거(`retrieved_refs`, 조각 번호 `retrieved_chunk_ids`)와 단계별 시간(`embed_ms`·`db_connect_ms`·`search_ms`·`llm_ms`·`rewrite_ms`)이 응답에 붙습니다. `rewrite_ms`는 질문 바꾸기를 하지 않은 요청이면 `null`입니다.
- **v1.5 API(이어지는 질문, 결정기록 023):**
  - 요청에 선택 항목 `history`: `[{"question", "answer"}]` 최대 3개(질문 500자·답 4,000자). 넘치거나 형식이 틀리면 `400 INVALID_REQUEST`. 서버는 답을 가린 뒤 앞 1,000자만 질문 바꾸기에 씁니다. 없으면 1차와 똑같이 동작합니다. 화면은 최근 3턴(오류 턴 제외)의 가린 질문과 답을 보냅니다. 가린 질문은 원래 질문보다 길어질 수 있어 화면이 보낼 때 500자로 자릅니다(2026-11-12).
  - 응답에 `question_masked`(개인정보를 가린 새 질문, 항상)와 `rewritten_question`(앞 대화로 바꾼 질문, 바꾸기에 성공했을 때만, 아니면 `null`)이 붙습니다.
  - 앞 대화는 질문 바꾸기에만 쓰고 답변 AI에는 넘기지 않습니다. 고른 모델과 다른 제조사 이름이 든 질문은 AI 없이 안내합니다(결정기록 027).
  - 응답에 `reason`: 다른 제조사 질문이라 안내했으면 `"other_brand"`, 아니면 `null`. 화면은 이 값으로 브랜드 안내("모델 다시 고르기" 버튼)를 찾지 못함과 구분합니다.

## 평가

```bash
.venv/Scripts/python -X utf8 -m evaluation --label v1 --prompt v1 --search vector
```

- `evaluation/questions.csv`의 고정 질문 30개(2026-10-28 고정)를 돌려 채점합니다.
- 결과는 `evaluation/results/<label>-<날짜>.csv`(사람 판정용 `human_verdict` 열)와 `docs/평가/<날짜>-<label>.md`에 저장됩니다.
- 한 번 돌리는 데 OpenAI 비용이 약 1센트입니다(실측 85회 기준 질문당 약 0.035센트).

## 배포 (Vercel)

- **구조:** 루트 `index.py`가 FastAPI 앱을 노출하고, `public/`은 Vercel CDN이 제공합니다. `vercel.json`이 `framework: fastapi`와 함수 지역 `regions: ["sin1"]`을 고정합니다(결정기록 013·018).
- **데이터베이스:** Neon Postgres + pgvector(`ap-southeast-1`)이고, 함수와 같은 싱가포르에 둡니다.
- **환경 변수:** `.env.example`의 키를 Vercel 대시보드의 Production·Preview에 직접 입력합니다. 값은 저장소·화면·로그에 남기지 않습니다. `FORCE_FAIL`은 운영(Production)에 넣지 않습니다. 2차의 `CRON_SECRET`은 Production에만 넣습니다.
- **도메인(2차):** 운영 주소는 https://pyeobom.help 이고, 옛 주소 https://pyeobom.vercel.app 도 아직 응답합니다.
- **예약(2차):** `vercel.json`의 `crons`가 하루 3번 `/api/wake`를 불러 Supabase 무료 프로젝트가 활동 부족으로 멈추지 않게 합니다(PR #108, `db.md` "Supabase 깨우기").
- **검색 방식 `SEARCH_MODE`:** 운영은 `vector`입니다. 벡터 검색을 하고, 근거에 없는 에러 코드면 진단 안내 쪽을 덧붙입니다(결정기록 019). `hybrid`(질문 단어·코드 키워드를 섞음)는 시도한 뒤 채택하지 않은 실험용입니다(결정기록 020).
- **시연 영상(1차):** https://docs.google.com/videos/d/1exAuemfmZ3Bfjfu3rhLOHd91pgpmKbe9hXKamyf2qUY/play?usp=sharing (핵심 흐름, 이상 입력·개인정보, 환각 방지, 실패 대응). 저장소에는 넣지 않았습니다.
- **배포 흐름:** 기능 브랜치 → PR(미리보기 배포에서 확인) → `main`에 merge commit으로 병합하면 운영에 배포됩니다.

## 결과 요약 (테스트 질문 30개)

| 버전 | 바꾼 것 | 자동 채점 정답률 | 사람 판정 정답률 | 근거 적중률 | 환각률 | 결정 |
|---|---|---|---|---|---|---|
| v1 | 기준 | 68.0% | 84.0% | 76.0% | 0% | — |
| v2a | 근거에 없는 에러 코드면 진단 안내 쪽을 덧붙임 | 68.0% | **88.0%** | 80.0% | 0% | **채택(운영)** |
| v2b | + 질문 단어·코드 키워드 검색 | 84.0% | — | 84.0% | 0% | 미채택 |

- 정답률·근거 적중률은 답이 있는 25문항, 환각률은 함정 5문항(답이 없어야 하는 질문)이 분모입니다.
- **변동 폭:** 같은 설정을 두 번 돌리면 자동 판정이 30개 중 2개 정도 바뀝니다. 그래서 1~2문항 차이는 개선으로 보지 않습니다.
- **자동 채점의 한계:** 핵심 단어를 글자 그대로 찾기 때문에, 같은 뜻의 다른 표현(배수 필터 ↔ 거름망)을 오답으로 봅니다. 그래서 사람 판정을 함께 적습니다.
- **v2b 미채택 이유:** 자동 점수는 올랐지만, 겨냥한 문항(q20 "장마철에 습기만 빼고 싶어요")의 정답 근거(제습 26쪽)가 검색에 들어오지 않았습니다. 점수 상승은 표현 차이와 실행 변동이었습니다(결정기록 020).
- **응답 시간 (운영, 이어지는 요청):** 평균 약 2.7초이고, 대부분이 AI 답변 호출입니다. 한동안 쓰지 않다가 처음 보내는 요청은 약 7.7초입니다(결정기록 018).
- 자세한 내용: `docs/평가/2026-11-01-v1.md`, `-v2a.md`, `-v2b.md`
- 회고: [docs/회고.md](docs/회고.md)
- v1.5 개편 전 1차 기준값(도구 6개): [docs/평가/baseline-v1.md](docs/평가/baseline-v1.md)
- v1.5 채택 측정(2026-11-11, 조건 1~4 통과: 30문항 26/30·이어지는 질문 바꾸기 17/17·정답 31/31·환각 0, 시간 +343ms, axe 위반 0·LCP 864ms·CLS 0.0006): [docs/평가/v15-ui.md](docs/평가/v15-ui.md)
- 프롬프트 기록: [docs/프롬프트.md](docs/프롬프트.md), 버전별 원문과 바꾼 이유는 [prompts/](prompts/README.md)
- 2차 모델 추가 도구 결론 "개선"(결정기록 044): [docs/평가/phase2-model-add.md](docs/평가/phase2-model-add.md), 상호 테스트 기록: [docs/평가/phase2-mutual-test.md](docs/평가/phase2-mutual-test.md)

## 한계

- **문서 범위:**
  - 설명서·해결 가이드에 없는 내용(수리비, 부품, 다른 모델)은 답하지 않습니다.
  - 해결 가이드는 제품 종류 공용이라 모델에 따라 다를 수 있습니다. 화면에 경고를 표시합니다.
  - LG 벽걸이 에어컨 설명서는 모델 전용이 아닌 공용 설명서입니다.
- **추출:**
  - 그림 속 글자는 검색하지 못합니다.
  - 글자가 거의 없는 PDF도 다루지 못합니다(OCR 없음).
  - 표의 칸이 줄바꿈으로 나뉘어 읽힐 수 있습니다.
- **검색:** 뜻은 같고 글자가 다른 질문(습기 ↔ 제습)을 놓칠 수 있습니다(2차 과제).
- **에러 코드:** 에어컨 에러 코드는 공용 가이드에 있는 코드만 답합니다. 없는 코드는 "없다"고 밝힌 뒤 스마트 진단을 안내합니다. 삼성 세탁건조기 설명서에는 고장 진단 기능이 없어 진단 안내를 붙이지 않습니다.
- **평가:** 테스트 30개의 소규모 평가라 수치를 일반화하기 어렵습니다. 같은 30개로 설정을 고르면 그 질문에 맞춰질 위험이 있어, 이번에는 그런 조정을 하지 않았습니다.
- **대화:** ~~대화를 기억하지 않아, 이어지는 질문의 맥락을 반영하지 못합니다.~~ → v1.5(2026-11-11)부터 최근 3턴으로 이어지는 질문을 바꿔 찾습니다. 대상이 빠진 모호한 질문도 짐작해 바꾸며 되묻지 않습니다(다음 계획 후보). 대화는 그 기기 브라우저에만 있어 다른 기기에서는 볼 수 없습니다.
- **근거 표시:** 답변 AI가 인용의 조각 번호를 잘못 적으면 답 전체를 버리고 "찾지 못함"으로 보여 줍니다. 진짜 못 찾은 경우와 화면에서 구분되지 않습니다(다음 계획에서 다룸).
- **약관:** 실제로 상용화한다면 제조사 약관상 사전 승낙이 필요합니다.

## 결정기록 (`docs/결정기록/`)

| 번호 | 제목 |
|---|---|
| 001 | 주제 변경: 개발자 도구 → 비개발자 반복 업무 → 가전 설명서 Q&A |
| 002 | 1차 사용자: 자취생 중심, 어르신·상담원은 2~4차 |
| 003 | 대상 가전: 세탁기 + 에어컨 |
| 004 | 기술 구조: HTML + 파이썬 서버 함수(Vercel) |
| 005 | 검색 데이터: Neon + pgvector |
| 006 | 1차 범위: 핵심 흐름 우선, 추가 기능은 여유 시 |
| 007 | 화면 구성: C안 검색형 |
| 008 | 컴퓨터(노트북) 카테고리: 2차 이후 |
| 009 | 저작권 정책: 원본·조각 비공개, 짧은 인용, 고지, 허락 문의 |
| 010 | 수리 연결·리뷰 로드맵 |
| 011 | 형상관리: 기능별 폴더 + 기능별 브랜치 + PR |
| 012 | 서비스명 '펴봄'과 첫 화면 소개 영역(랜딩 A안) |
| 013 | Vercel 파이썬 배포 구조 |
| 014 | 근거 문서 선정 |
| 015 | 1차 최종 설정 (각 결정기록 요약) |
| 016 | 추출 도구 선택 (+ 부록: 측정 기록) |
| 017 | 임베딩·답변 모델 선택 |
| 018 | 배포 지역: Vercel 함수 sin1 + Neon 싱가포르 |
| 019 | v2a: 근거에 없는 에러 코드는 진단 안내 쪽을 덧붙인다 |
| 020 | v2b(질문 단어·코드 키워드 하이브리드 검색): 시도 후 미채택 |
| 021 | v1.5 채팅형 화면 개편 (검색형 → 랜딩·카테고리·모델·채팅) |
| 022 | 대화는 브라우저에만 저장 (가린 질문만, 버전 1) |
| 023 | 질문 바꾸기(방법 A)와 바꾸기 설정 |
| 024 | v1.5 디자인 체계 (흑백, Pretendard) |
| 025 | 제품 그림은 세 모델 모두 같은 스타일의 AI 일러스트 |
| 026 | 1차 기준값 측정 도구와 방법 |
| 027 | 다른 브랜드 질문은 코드로 "찾지 못함" (결정 A) |
| 028 | 채택 조건 3 예외 (v1.5 서버, 이어지는 질문) |
| 029 | 검색 개선(표현이 다른 질문) 미채택, 운영 M0 유지 |
| 030 | 서랍 맨 윗줄에 뒤로·처음으로·닫기 아이콘 버튼 |
| 031 | v1.7 확인용 세트 구성과 측정 전 결정 |
| 032 | v1.7 결론: 쪽 표시 지우기 채택, 도구·자르기 미채택 |
| 033 | Fable 분할 실험 측정 전 결정 |
| 034 | Fable 분할 실험 결론: 미채택 |
| 035 | 임베딩 모델 바꾸기(v1.9) 측정 전 결정 |
| 036 | 임베딩 모델 바꾸기(v1.9) 결론: 미채택 |
| 037 | 조각 설명 붙이기(v1.95) 측정 전 결정 |
| 038 | 조각 설명 붙이기(v1.95) 결론: 미채택 |
| 039 | 첫 질문 다듬기(v1.96) 측정 전 결정 |
| 040 | 첫 질문 다듬기(v1.96) 결론: 미채택 |
| 041 | 임베딩 large 다시 해 보기(v1.97) 측정 전 결정 |
| 042 | 임베딩 large 다시 해 보기(v1.97) 결론: 채택 후보 |
| 043 | 2차 구조와 DB 연결 규칙 |
| 044 | 2차 모델 추가 도구 결론: 개선 |

- 최종 설정을 한곳에서 보려면 015를 보면 됩니다.
- 2차 문서: `PRD.md`, `db.md`, 설계 `docs/superpowers/specs/2026-11-17-phase2-model-request-design.md`, 계획 `docs/superpowers/plans/2026-11-21-phase2-model-request-plan.md`
- 그 밖의 문서: 기획서 `docs/기획서.md`, 구현 계획 `docs/superpowers/plans/2026-10-27-pyeobom-phase1.md`, 개발일지 `docs/개발일지/`, AI 실수 기록 `docs/AI-실수-기록.md`, 안정성 기록 `docs/안정성-테스트.md`

## 외부 스킬과 라이선스

- `.claude/skills/accessibility/`: Claude Code 프로젝트 스킬(접근성 점검, WCAG 2.2). 출처 [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills) `skills/accessibility`, **MIT License**(Copyright (c) 2026 Addy Osmani). 내려받은 그대로이며 고치지 않았다(`skills-lock.json`의 `computedHash`로 확인).
- `.claude/skills/ffmpeg-usage/`: Claude Code 프로젝트 스킬(영상 편집 명령 모음, 2차 시연 영상용). 출처 [ychoi-kr/claude-ffmpeg-skill](https://github.com/ychoi-kr/claude-ffmpeg-skill) `b88cb5c`, **MIT License**(Copyright (c) 2025 Yong Choi, 원문은 폴더 안 `LICENSE`). 내려받은 그대로이며 고치지 않았다(`skills-lock.json`의 `computedHash`로 확인). 폴더 안 `install.sh`·`validate.py`·`examples/conversion.sh`는 원본에 들어 있는 파일이며 이 프로젝트는 실행하지 않는다.
- `.claude/skills/security-audit/`: Claude Code 프로젝트 스킬(보안 검토). 출처 [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) `skills/security-audit` `c1c8a8c`, **MIT License**(Copyright (c) 2025-2026 Cloudflare, Inc., 원문은 아래). 내려받은 그대로이며 고치지 않았다(`skills-lock.json`의 `computedHash`로 확인).
- `.claude/skills/supabase/`: Claude Code 프로젝트 스킬(Supabase 작업 지침·보안 체크리스트, 2차 요청 표·RLS·로그인 토큰 확인용). 출처 [supabase/agent-skills](https://github.com/supabase/agent-skills) `skills/supabase` `c9be0e9`, **MIT License**(Copyright (c) 2026 Supabase, 원문은 아래). 내려받은 그대로이며 고치지 않았다(`skills-lock.json`의 `computedHash`로 확인).
- `.claude/skills/supabase-postgres-best-practices/`: Claude Code 프로젝트 스킬(Postgres 규칙 모음, RLS 정책·테스트·스키마용). 출처 [supabase/agent-skills](https://github.com/supabase/agent-skills) `skills/supabase-postgres-best-practices` `c9be0e9`, **MIT License**(Copyright (c) 2026 Supabase, 원문은 아래). 내려받은 그대로이며 고치지 않았다(`skills-lock.json`의 `computedHash`로 확인).
- 라이선스 안내를 스킬 폴더 안에 두지 않은 이유: 폴더에 파일을 더하면 `skills-lock.json`의 해시가 달라져 수정된 스킬로 보인다.

<details>
<summary>MIT License 원문 (addyosmani/web-quality-skills)</summary>

```
MIT License

Copyright (c) 2026 Addy Osmani

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

</details>

<details>
<summary>MIT License 원문 (cloudflare/security-audit-skill)</summary>

```
MIT License

Copyright (c) 2025-2026 Cloudflare, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

</details>

<details>
<summary>MIT License 원문 (supabase/agent-skills)</summary>

```
MIT License

Copyright (c) 2026 Supabase

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

</details>
