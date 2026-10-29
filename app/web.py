from fastapi import FastAPI

from app.ask.routes import router as ask_router
from app.catalog.routes import router as catalog_router


def create_app() -> FastAPI:
    app = FastAPI(title="펴봄")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(catalog_router)
    app.include_router(ask_router)
    return app
