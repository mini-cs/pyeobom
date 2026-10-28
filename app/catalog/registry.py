import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_models(path: str = "data/models.json") -> list[dict]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def supported_ids(models: list[dict]) -> set[str]:
    return {m["id"] for m in models}
