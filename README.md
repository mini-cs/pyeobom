# 펴봄 — 가전 설명서, 대신 펴 봐 드려요

자취생이 세탁기·에어컨 모델을 고르고 질문하면, 그 모델의 공식 설명서에서 근거를 찾아 페이지와 함께 알려 주는 웹 서비스입니다(비영리 학습용 포트폴리오).

## 로컬 실행

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -v -m "not integration"
```

화면까지 함께 띄우려면 `.env`를 채운 뒤 `.venv/Scripts/python -X utf8 experiments/dev_server.py`로 실행하고 http://127.0.0.1:8765 에서 확인합니다(로컬 확인 전용).

## 배포 (Vercel)

- 운영 주소: https://pyeobom.vercel.app
- **구조:** 루트 `index.py`가 FastAPI 앱을 노출하고, `public/`은 Vercel CDN이 제공합니다. `vercel.json`이 `framework: fastapi`와 함수 지역 `regions: ["sin1"]`을 고정합니다(결정기록 013·018).
- **데이터베이스:** Neon Postgres + pgvector(`ap-southeast-1`)입니다. 스키마는 `ingest/schema.sql`, 적재는 `python -m ingest --doc-id <id>`로 로컬에서 합니다.
- **환경 변수:** `.env.example`의 키를 Vercel 대시보드의 Production·Preview에 직접 입력합니다. 값은 저장소·화면·로그에 남기지 않습니다. `FORCE_FAIL`은 운영(Production)에 넣지 않습니다.
- **배포 흐름:** 기능 브랜치 → PR(미리보기 배포에서 확인) → `main`에 merge commit으로 병합하면 운영에 배포됩니다.

자세한 내용은 [기획서](docs/기획서.md)를 참고하세요.
