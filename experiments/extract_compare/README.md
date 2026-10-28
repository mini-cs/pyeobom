# 추출 도구 비교 스크립트

결정기록 016(추출 도구 선택)과 부록(`docs/결정기록/016-부록-추출-도구-측정.md`)의 수치를 재현하는 스크립트다.

- 데이터는 들어 있지 않다. 설명서 PDF(`data/manuals/`)와 가이드 HTML(`data/guides/`)은 각자 내려받아 둔다.
- 추출 결과는 이 폴더의 `out/`에 쓴다. `out/`에는 설명서 본문이 들어가므로 `.gitignore`로 커밋하지 않는다.
- 서비스 코드가 아니다. 테스트하지 않고, 비교용 도구는 `requirements-dev.txt`에 넣지 않는다.

## 실행

```bash
.venv/Scripts/python -m pip install "markitdown[pdf]==0.1.9" pdfplumber==0.11.10 pypdfium2==5.14.0 beautifulsoup4
.venv/Scripts/python -X utf8 experiments/extract_compare/pdf_vs_markitdown.py data/manuals/*.pdf
.venv/Scripts/python -X utf8 experiments/extract_compare/pdf_vs_pypdfium2.py data/manuals/*.pdf
.venv/Scripts/python -X utf8 experiments/extract_compare/html_vs_markitdown.py data/guides
```

| 스크립트 | 비교 | 결정기록 016 절 |
|---|---|---|
| `pdf_vs_markitdown.py` | 쪽 수(`\f`로 나눔), 반복 글자 바닥글, 본문 `(cid:)` 잡음 | PDF 비교 (1차) |
| `pdf_vs_pypdfium2.py` | 쪽 수, 소수점 유지·손실, 반복 글자 줄·`Untitled` 줄, `(cid:)` 줄, 추출 시간 | 수정 (2026-10-28 오후) |
| `html_vs_markitdown.py` | 글자 수, 사이트 잡음, LG 숨은 탭 문장, 플렉스워시 | HTML 비교 |

- 숨은 탭 문장 수는 대조할 때 지우는 기호에 따라 조금 달라진다. 이 스크립트는 마크다운 기호까지 지워 LG 414개 중 MarkItDown 412·본문만 414이고, 결정기록의 417/417·398/400은 공백만 지운 셈이다. 결론(두 방식 모두 숨은 탭을 가져옴)은 같다.
