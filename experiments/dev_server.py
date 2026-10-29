"""로컬 확인 전용 서버: API(index:app)와 화면(public/)을 한 주소로 띄운다.

사용법: .venv/Scripts/python -X utf8 experiments/dev_server.py  → http://127.0.0.1:8765
Vercel은 public/을 CDN에서 루트 경로로 제공하고 FastAPI에 붙이지 않는다(결정기록 013). 그래서 배포 코드가 아니라 여기서만 붙인다.
.env의 접속 주소·키를 읽지만 출력하지 않는다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingest.__main__ import load_env  # noqa: E402

load_env()

import uvicorn  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.web import create_app  # noqa: E402

app = create_app()
app.mount("/", StaticFiles(directory=ROOT / "public", html=True), name="public")  # API 경로를 먼저 등록한 뒤 붙인다

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
