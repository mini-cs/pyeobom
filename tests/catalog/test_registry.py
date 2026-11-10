from fastapi.testclient import TestClient

from app.catalog.registry import load_models, supported_ids
from app.web import create_app


def test_models_file_has_required_fields():
    for m in load_models():
        assert {"id", "brand", "appliance", "model_name", "display_name", "name", "model_codes", "official_url",
                "model_name_hint"} <= m.keys()
        assert m["appliance"] in {"washer", "aircon"} and m["official_url"].startswith("https://")
        # 화면용 이름(name)에는 코드가 없고, 코드(model_codes)는 기존 display_name에 든 값과 같다
        assert m["name"] and "(" not in m["name"] and m["display_name"].startswith(m["name"])
        assert m["model_codes"] and all(code in m["display_name"] for code in m["model_codes"])


def test_models_count_in_scope():
    assert 3 <= len(load_models()) <= 4


def test_supported_ids_are_unique():
    models = load_models()
    assert len(supported_ids(models)) == len(models)


def test_api_models_hides_internal_fields():
    body = TestClient(create_app()).get("/api/models").json()
    assert body and set(body[0]) == {"id", "display_name", "name", "model_codes", "appliance", "official_url",
                                     "model_name_hint"}


def test_diagnostic_refs_point_to_manual_pages():
    import re
    refs = {m["id"]: m["diagnostic_refs"] for m in load_models()}
    assert all(re.fullmatch(r"manual:\d+", r) for rs in refs.values() for r in rs)
    assert refs == {"washer-samsung-wd90h25": [], "washer-lg-fx25": ["manual:54"],
                    "aircon-lg-sq06fa1wds": ["manual:34", "manual:49"]}   # 결정기록 019
