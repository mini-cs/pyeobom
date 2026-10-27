# Vercel 진입점: 로직은 app/ 에 두고 여기서는 앱만 노출한다 (pyproject.toml의 tool.vercel.entrypoint).
from app.web import create_app

app = create_app()
