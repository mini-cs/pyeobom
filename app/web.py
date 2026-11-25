from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.ask.routes import register_error_handlers, router as ask_router
from app.catalog.routes import router as catalog_router
from app.core.config import get_settings
from app.core.errors import make_error


def create_app() -> FastAPI:
    app = FastAPI(title="펴봄")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/public-config")
    def public_config():
        # 화면이 Supabase를 직접 부를 때 쓰는 공개 값 두 개만 준다(서버 전용 키는 절대 넣지 않음)
        s = get_settings()
        if not (s.supabase_url and s.supabase_anon_key):
            e = make_error("LOGIN_UNAVAILABLE")
            return JSONResponse(status_code=e.status, content={"error_code": e.code, "message": e.message})
        return {"supabase_url": s.supabase_url, "supabase_anon_key": s.supabase_anon_key}

    app.include_router(catalog_router)
    app.include_router(ask_router)
    register_error_handlers(app)
    return app
