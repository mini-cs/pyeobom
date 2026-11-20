# v1.7 추출 도구 실행 스크립트

v1.7 계획 Task 4 Step 6에서 후보 도구로 설명서 3개를 쪽별 마크다운으로 뽑은 스크립트다. 판정은 `measure/v17_gate.py`가 하고, 결과와 수치는 `docs/평가/v17-extraction.md` 0단계에 적는다.

- 데이터는 들어 있지 않다. 설명서 PDF(`data/manuals/`)는 각자 내려받아 둔다.
- 출력은 `measure/out/v17/extract/<도구>/<문서 id>.json`(`[{"page": 1부터, "markdown": 글}]`)과 `run.json`(버전·시간·바꾼 옵션)에 쓴다. 설명서 본문이 들어가므로 커밋하지 않는다(`measure/out/`은 git 제외).
- 서비스 코드가 아니다. 테스트하지 않고, 프로젝트 모듈(`app/`·`ingest/`)을 import하지 않는다. 도구는 `requirements*.txt`에 넣지 않는다.
- 도구마다 가상환경을 따로 만든다: `measure/out/v17/venv/<도구>`. 파이썬 3.14가 안 되는 도구만 uv로 3.12를 쓴다.

## 실행

```bash
py -3.14 -m venv measure/out/v17/venv/<도구>
measure/out/v17/venv/<도구>/Scripts/python -m pip install <패키지>
measure/out/v17/venv/<도구>/Scripts/python experiments/v17_extract/run_<도구>.py <PDF> measure/out/v17/extract/<도구>/<문서 id>.json
```

| 스크립트 | 패키지 | 쪽 나누기 | 덧붙임 |
|---|---|---|---|
| `run_pymupdf4llm.py` | `pymupdf4llm` | 도구 옵션 `page_chunks=True` | |
| `run_opendataloader-pdf.py` | `opendataloader-pdf pypdfium2` (Java 필요) | 도구 옵션 `markdown_page_separator` | 이름에 `-`가 있어 직접 실행만 된다 |
| `run_docling.py` | `docling` | 문서의 쪽 번호(`page_no`) | 셋째 인자 `cpu`/`cuda` |
| `run_marker.py` | `marker-pdf` (파이썬 3.12) | 도구 옵션 `paginate_output=True`(0부터 → +1) | `PYTHONUTF8=1`, 셋째 인자 `cpu`/`cuda` |
| `run_mineru.py` | `mineru pypdfium2` | `page_idx`(0부터 → +1) | 셋째 인자 tier(기본 `standard`), 넷째 인자 ocr_mode(기본 `auto`, Fable 계획 Task 3은 `txt`), 장치는 환경변수 `MINERU_MODEL_ONNX_DEVICE=cpu`/`gpu` |
| `run_unstructured.py` | `"unstructured[pdf]"` + tesseract(conda-forge로 `measure/out/v17/tess`에 받아 실행 프로세스에만 `PATH`·`TESSDATA_PREFIX`) | 요소의 `metadata.page_number` | `strategy="hi_res"`, Title 요소 → `# ` 제목, 나머지 요소 글은 한 줄씩 |

- 판정 기준 글자(pypdfium2)는 `python -m measure.v17_gate --baseline`이 만든다.
