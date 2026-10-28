from fastapi.testclient import TestClient

from app.catalog.registry import load_models, supported_ids
from app.web import create_app


def test_models_file_has_required_fields():
    for m in load_models():
        assert {"id", "brand", "appliance", "model_name", "display_name", "official_url", "model_name_hint"} <= m.keys()
        assert m["appliance"] in {"washer", "aircon"} and m["official_url"].startswith("https://")


def test_models_count_in_scope():
    assert 3 <= len(load_models()) <= 4


def test_supported_ids_are_unique():
    models = load_models()
    assert len(supported_ids(models)) == len(models)


def test_api_models_hides_internal_fields():
    body = TestClient(create_app()).get("/api/models").json()
    assert body and set(body[0]) == {"id", "display_name", "appliance", "official_url", "model_name_hint"}
