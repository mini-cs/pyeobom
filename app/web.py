from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="펴봄")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app
