# 펴봄 — 가전 설명서, 대신 펴 봐 드려요

자취생이 세탁기·에어컨 모델을 고르고 질문하면, **그 모델의 공식 설명서와 제조사 공식 해결 가이드에서 근거를 찾아** 쪽 번호·짧은 인용과 함께 답하는 웹 서비스입니다. 근거가 없으면 지어내지 않고 "설명서에서 찾지 못했어요"라고 답합니다.

- 운영 주소: https://pyeobom.vercel.app
- 비영리 학습용 포트폴리오입니다. 설명서 저작권은 각 제조사에 있습니다.
- 지원 모델(1차): 삼성 BESPOKE AI 콤보 세탁건조기, LG 드럼세탁기, LG 벽걸이 에어컨(`data/models.json`)

## 구조

```mermaid
flowchart TD
  U[휴대폰 브라우저<br>public/ 화면] -->|POST /api/ask| F[Vercel 함수 sin1<br>FastAPI index.py]
  F --> G[입력 검사<br>개인정보 가리기]
  G --> E[OpenAI 임베딩<br>text-embedding-3-small]
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
| `public/` | 화면(정적 HTML·CSS·JS, Vercel CDN) |
| `ingest/` | 전처리(로컬): PDF·HTML → 조각 → 임베딩 → Neon |
| `evaluation/` | 평가(로컬): 테스트 질문 30개, 채점, 리포트 |

## 로컬 실행

**필요한 것:** Python 3.14, Neon 계정(무료), OpenAI API 키

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

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

## 설명서·가이드 받기 (원본은 저장소에 없음)

설명서 PDF와 가이드 HTML은 저작권 때문에 저장소에 넣지 않았습니다(결정기록 009). 아래 공식 페이지에서 직접 받아 **`data/documents.json`의 `file` 경로와 같은 이름**으로 저장합니다.

| 문서 | 받는 곳 | 저장 위치 |
|---|---|---|
| 삼성 세탁건조기 설명서 | 삼성전자서비스 다운로드 자료실(https://www.samsungsvc.co.kr/download)에서 `WD90H25AHTN1`로 검색해 받음(표지 모델명 `WD90H25AH*` 계열) | `data/manuals/OID140081_IB_WD80H-AD_7LCD_KO_260331.pdf` |
| LG 드럼세탁기 설명서 | LG전자 제품 설명서(https://www.lge.co.kr/support/product-manuals)에서 `FX24GNG`로 검색해 받음(표지 모델명 `FX25*N*`/`FX24*N*`/`FX23*N*`, 문서 번호 `MFL71792818`) | `data/manuals/WM_KOR_MFL71792818_10_251204_00_OM_WEB.pdf` |
| LG 벽걸이 에어컨 설명서 | 같은 페이지에서 `SQ06FA1WDS`로 검색해 받음(공용 설명서, 문서 번호 `MFL71890636`) | `data/manuals/[CW_RAC_24515]_250626_MFL71890636_01_Domestic_2025_WLM_2LED_CO.pdf` |
| 해결 가이드 8개 | `data/documents.json`의 각 `source_url` | `data/guides/<id>.html` |

- 가이드는 브라우저에서 **"웹페이지 전체 저장"**으로 저장합니다. 인쇄(PDF 저장)를 하면 탭 안에 숨은 설명이 빠질 수 있습니다.
- 파일 이름이나 판이 달라졌다면 `data/documents.json`의 `file`을 맞추고, 쪽 번호가 바뀌었는지 확인합니다.

## 적재 (Neon)

1. Neon SQL Editor에서 `ingest/schema.sql`을 한 번 실행합니다. vector 확장과 테이블 3개(`documents`, `document_models`, `chunks`)가 만들어집니다.
2. 문서 11개를 하나씩 적재합니다.

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

- 문서마다 "조각 N개, 적용 범위 밖이라 뺀 문단 M개"가 출력됩니다. 전체 약 332개가 나와야 합니다.
- 같은 문서를 다시 적재하면 그 문서의 기존 조각을 지우고 새로 넣습니다.

## 실행과 테스트

```bash
.venv/Scripts/python -m pytest -v -m "not integration"   # 기본 테스트(키·DB 없이)
.venv/Scripts/python -m pytest -v -m integration         # Neon·OpenAI 연결 테스트(.env 필요)
.venv/Scripts/python -X utf8 experiments/dev_server.py   # 화면 + API → http://127.0.0.1:8765
```

- `dev_server.py`는 로컬 확인 전용입니다. 배포에서는 `public/`을 Vercel CDN이 제공합니다(결정기록 013).
- 디버그: `POST /api/ask?debug=true`이면 검색된 근거(`retrieved_refs`)와 단계별 시간(`embed_ms`·`db_connect_ms`·`search_ms`·`llm_ms`)이 응답에 붙습니다.

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
- **환경 변수:** `.env.example`의 키를 Vercel 대시보드의 Production·Preview에 직접 입력합니다. 값은 저장소·화면·로그에 남기지 않습니다. `FORCE_FAIL`은 운영(Production)에 넣지 않습니다.
- **검색 방식 `SEARCH_MODE`:** 운영은 `vector`입니다. 벡터 검색을 하고, 근거에 없는 에러 코드면 진단 안내 쪽을 덧붙입니다(결정기록 019). `hybrid`(질문 단어·코드 키워드를 섞음)는 시도한 뒤 채택하지 않은 실험용입니다(결정기록 020).
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
- **대화:** 대화를 기억하지 않아, 이어지는 질문의 맥락을 반영하지 못합니다.
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

- 최종 설정을 한곳에서 보려면 015를 보면 됩니다.
- 그 밖의 문서: 기획서 `docs/기획서.md`, 구현 계획 `docs/superpowers/plans/2026-10-27-pyeobom-phase1.md`, 개발일지 `docs/개발일지/`, AI 실수 기록 `docs/AI-실수-기록.md`, 안정성 기록 `docs/안정성-테스트.md`
