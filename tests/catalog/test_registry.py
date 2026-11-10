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
        # 위쪽 막대용 짧은 이름(선택)은 name의 앞부분만 쓴다(새 이름을 지어내지 않음)
        if "short_name" in m:
            assert m["short_name"] and m["name"].startswith(m["short_name"]) and m["short_name"] != m["name"]


def test_models_count_in_scope():
    assert 3 <= len(load_models()) <= 4


def test_supported_ids_are_unique():
    models = load_models()
    assert len(supported_ids(models)) == len(models)


def test_api_models_hides_internal_fields():
    body = TestClient(create_app()).get("/api/models").json()
    assert body and all(set(m) == {"id", "display_name", "name", "short_name", "model_codes", "appliance",
                                   "official_url", "model_name_hint"} for m in body)


def test_short_name_only_for_samsung_and_null_elsewhere():
    # 2026-11-10 사용자 결정: 360px 위쪽 막대 한 줄을 위해 삼성만 "세탁건조기"를 뺀 짧은 이름
    models = {m["id"]: m for m in load_models()}
    assert models["washer-samsung-wd90h25"]["short_name"] == "삼성 BESPOKE AI 콤보"
    assert "short_name" not in models["washer-lg-fx25"] and "short_name" not in models["aircon-lg-sq06fa1wds"]
    body = {m["id"]: m["short_name"] for m in TestClient(create_app()).get("/api/models").json()}
    assert body == {"washer-samsung-wd90h25": "삼성 BESPOKE AI 콤보", "washer-lg-fx25": None, "aircon-lg-sq06fa1wds": None}


def test_diagnostic_refs_point_to_manual_pages():
    import re
    refs = {m["id"]: m["diagnostic_refs"] for m in load_models()}
    assert all(re.fullmatch(r"manual:\d+", r) for rs in refs.values() for r in rs)
    assert refs == {"washer-samsung-wd90h25": [], "washer-lg-fx25": ["manual:54"],
                    "aircon-lg-sq06fa1wds": ["manual:34", "manual:49"]}   # 결정기록 019
