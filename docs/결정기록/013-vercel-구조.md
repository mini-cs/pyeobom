# 013. Vercel 파이썬 배포 구조

- 날짜: 2026-10-27
- 상태: **잠정** — 배포 URL에서 `/api/health`와 `/`를 확인한 뒤 확정한다
- 배경: 기획서 5.8에서 "Vercel 서버 함수·정적 파일 위치는 구현 단계에서 최신 문서로 확인"으로 남겨 둔 항목. 계획은 진입 파일을 `api/index.py`로 정했다.
- 확인한 문서 (2026-10-27):
  - Deploy a FastAPI app on Vercel (`/docs/frameworks/backend/fastapi`): FastAPI 인스턴스 `app`을 `app.py`·`index.py`·`server.py`·`main.py`·`wsgi.py`·`asgi.py` 또는 `src/`·`app/` 안의 같은 이름에서 찾는다. 다른 위치는 `pyproject.toml`의 `[tool.vercel] entrypoint = "module:app"`으로 지정. `public/` 폴더 파일은 CDN에서 루트 경로로 제공하며 `app.mount()`로 붙이지 말라고 한다.
  - Using the Python Runtime (`/docs/functions/runtimes/python`): 지원 버전 3.12(기본)·3.13·3.14. 의존성은 `pyproject.toml`·`requirements.txt`·Pipfile. `/api` 폴더의 파일 기반 함수는 "기존 프로젝트" 호환 방식으로 따로 설명한다.
  - Configuring regions (`/docs/functions/configuring-functions/region`): 새 프로젝트의 함수 기본 지역은 `iad1`(워싱턴 D.C.). 대시보드 Settings → Functions 또는 `vercel.json`의 `regions`로 바꾼다. Hobby는 지역 1개.
- 선택지:
  - A. `api/index.py` 유지 + `pyproject.toml`의 `tool.vercel.entrypoint = "api.index:app"` — 계획 구조 그대로, 설정 한 줄 추가
  - B. 루트 `index.py`로 옮김 — 설정 없이 자동 감지, 계획의 파일 구조와 달라짐
  - C. `api/` 폴더 파일 기반 함수 방식 — 기존 프로젝트용 호환 방식이라 `/api/health` 같은 하위 경로 라우팅을 따로 맞춰야 함
- 결정: **A**. 파이썬 버전은 `.python-version`으로 3.14(로컬 개발 버전과 같음). 의존성은 `requirements.txt`(실행용)와 `requirements-dev.txt`(테스트용 pytest·httpx)로 나눠 함수 번들에 테스트 도구가 들어가지 않게 한다. 화면은 `public/`에 두고 FastAPI에 붙이지 않는다.
- 함수 지역: 기본값 `iad1`. Neon DB 지역과 맞추는 일은 Task 12에서 한다.
- 맞바꾼 것: 자동 감지가 아니라 설정 한 줄에 기대므로, 이 설정이 빠지면 배포가 진입점을 못 찾는다.
- 다시 볼 조건: 배포에서 `api/` 폴더가 파일 기반 함수로도 잡혀 경로가 겹치거나, `/`가 `public/index.html`을 보여 주지 않으면 진입 파일만 루트 `index.py`(B)로 옮기고 `app/` 패키지는 그대로 둔다.
- 배포 확인 결과: (배포 후 기록)
