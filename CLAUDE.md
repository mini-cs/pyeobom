# 펴봄 — Claude Code 작업 규칙

## 개요

자취생이 세탁기·에어컨 모델을 고르고 질문하면, 그 모델의 공식 설명서 조각을 근거로 검증된 답변(근거가 없으면 "찾지 못함")을 돌려주는 웹 서비스. 스펙은 `docs/기획서.md`, 구현 계획은 `docs/superpowers/plans/2026-10-27-pyeobom-phase1.md`.

## 기술 스택

Python(FastAPI) + Vercel 함수, OpenAI API(임베딩·답변), Neon Postgres + pgvector, 화면은 정적 HTML/CSS/JS(`public/`), 전처리·평가는 로컬 파이썬 스크립트.

## 폴더 구조

```
api/index.py      Vercel 진입점 (app.web.create_app()만 노출, 로직 없음)
app/web.py        create_app(): 라우터 조립 + /api/health
app/core/         설정·오류 정의·DB 연결
app/input_guard/  입력 검사·개인정보 가리기
app/catalog/      지원 모델 목록 (/api/models)
app/retrieval/    임베딩·검색
app/answer/       프롬프트·AI 호출·답변 검증
app/ask/          질문 처리 흐름 (/api/ask)
ingest/           전처리(로컬): PDF → 조각 → 임베딩 → Neon
evaluation/       평가(로컬): 테스트 30개·채점·리포트
public/           화면
data/models.json  지원 모델 메타데이터 (설명서 본문 없음)
tests/<기능 폴더>/ 기능 폴더와 같은 구조의 테스트
```

- 새 코드는 해당 기능 폴더에, 테스트는 `tests/<기능 폴더>/`에 둔다. 테스트 파일 이름은 폴더가 달라도 겹치지 않게 한다.

## 실행 방법

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -v -m "not integration"
```

Vercel 진입점은 `pyproject.toml`의 `[tool.vercel] entrypoint = "api.index:app"`, 파이썬 버전은 `.python-version`(결정기록 013).

## 금지

- 설명서 PDF, 검색용 조각 데이터, API 키, `.env`, 레퍼런스 원본 이미지 커밋 금지
- API 키·DB 주소를 화면·로그·커밋 메시지에 남기지 않는다. 비밀 값은 사용자가 `.env`와 Vercel 대시보드에 직접 입력한다
- 화면에 설명서 원문 통째 노출 금지 (인용 1~2문장, 150자 이내)
- 테스트에 실제 개인정보 사용 금지 (`010-1234-5678` 같은 가짜 값만)
- 운영(Production) 배포에 `FORCE_FAIL` 켜기 금지

## 작업 규칙

- 작업 후 `docs/개발일지/YYYY-MM-DD.md` 갱신, 중요한 결정은 `docs/결정기록/`에 ADR, Claude 실수는 `docs/AI-실수-기록.md`에 기록
- 화면 작업은 `docs/design/디자인-가이드.md`의 CSS 변수만 사용
- Vercel·OpenAI·Neon 설정은 공식 문서로 확인한 뒤 적용한다. 확인하지 않은 내용을 사실처럼 쓰지 않는다
- 계획에 없는 기능은 만들지 말고 개발일지의 "나중에"에 적는다

## 브랜치 전략

- `main`은 항상 배포 가능한 상태로 두고 직접 커밋하지 않는다(최초 커밋 제외)
- 기능 하나 = 브랜치 하나 = PR 하나. 브랜치·Task 매핑은 구현 계획의 "브랜치 전략" 표를 따른다
- 한 번에 브랜치 하나. 이전 브랜치를 병합한 뒤 최신 `main`에서 다음 브랜치를 만든다: `git switch main && git pull && git switch -c <브랜치>`
- 브랜치 마무리: `pytest -v -m "not integration"` 통과 → push → PR(양식 사용) → Vercel 미리보기 URL에서 확인 → merge commit으로 병합 → 브랜치 삭제 → 개발일지에 PR 링크
- `git push`, PR 생성, 병합 직전에는 항상 사용자에게 확인한다

## 커밋 메시지 규칙

타입·범위는 영어, 제목·본문은 한국어. 템플릿은 `.gitmessage`.

```
<type>(<scope>): <제목 — 무엇을 했는지, 50자 이내, 마침표 없음>

- 무엇을: <바뀐 내용 1~3줄>
- 왜: <이유, 관련 기획서 절>
- 테스트: <실행한 명령과 결과>

Refs: Task <번호>, docs/기획서.md <절>
```

- type: `feat` · `fix` · `test` · `refactor` · `docs` · `chore`
- scope: `setup`, `input-guard`, `catalog`, `ingest`, `retrieval`, `answer`, `ask`, `ui`, `deploy`, `evaluation`, `docs`
- 하지 않는 것: "수정"·"update"처럼 알 수 없는 제목, 여러 기능을 한 커밋에 섞기, 비밀 값·설명서 본문을 메시지에 쓰기
- 커밋 전에 `git diff --staged`를 보고 제목·본문을 작성해 사용자에게 보여 준 뒤 커밋한다

## 테스트 먼저 커밋

코드 작업은 커밋을 두 번 한다.

1. 실패 확인 직후: `test(<scope>): <기능> 테스트 추가 (실패 확인)`
2. 통과 후: `feat`/`fix` 커밋

병합은 merge commit 방식으로 해서 "테스트 → 구현" 순서가 기록에 남게 한다.
