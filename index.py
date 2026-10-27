# Vercel 진입점: 루트 index.py의 `app`을 자동 감지한다. 로직은 app/ 에 둔다 (결정기록 013).
from app.web import create_app

app = create_app()
