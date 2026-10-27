# 펴봄 — 가전 설명서, 대신 펴 봐 드려요

자취생이 세탁기·에어컨 모델을 고르고 질문하면, 그 모델의 공식 설명서에서 근거를 찾아 페이지와 함께 알려 주는 웹 서비스입니다(비영리 학습용 포트폴리오).

## 로컬 실행

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -v -m "not integration"
```

자세한 내용은 [기획서](docs/기획서.md)를 참고하세요.
