from fastapi import APIRouter

from app.catalog.registry import load_models

PUBLIC_FIELDS = ("id", "display_name", "name", "model_codes", "appliance", "official_url", "model_name_hint")

router = APIRouter()


@router.get("/api/models")
def list_models() -> list[dict]:
    # short_name(위쪽 막대용 짧은 이름)은 선택 항목: 없는 모델은 null, 화면은 short_name ?? name
    return [{**{k: m[k] for k in PUBLIC_FIELDS}, "short_name": m.get("short_name")} for m in load_models()]
