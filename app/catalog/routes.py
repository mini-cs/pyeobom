from fastapi import APIRouter

from app.catalog.registry import load_models

PUBLIC_FIELDS = ("id", "display_name", "appliance", "official_url", "model_name_hint")

router = APIRouter()


@router.get("/api/models")
def list_models() -> list[dict]:
    return [{k: m[k] for k in PUBLIC_FIELDS} for m in load_models()]
