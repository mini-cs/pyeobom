import json
from dataclasses import replace

from app.core.config import Settings
from evaluation.run_config import PRODUCTION, differences, run_settings, write_settings

PROD = Settings(openai_api_key="k", database_url="d", openai_embed_model="text-embedding-3-small", openai_chat_model="gpt-6-luna",
                embed_dim=1536, top_k=5, search_mode="vector", reasoning_effort="low", prompt_version="v1",
                rewrite_model="gpt-6-luna", rewrite_reasoning_effort="none", rewrite_max_output_tokens=300)


def test_run_settings_records_main_fields_without_secrets():
    s = run_settings(PROD)
    assert set(PRODUCTION) <= set(s)
    assert "openai_api_key" not in s and "database_url" not in s


def test_production_settings_have_no_differences():
    assert differences(PROD) == []


def test_top_k_52_is_reported():
    diffs = differences(replace(PROD, top_k=52))
    assert diffs == ["top_k=52 (운영 5)"]


def test_several_differences_are_reported():
    diffs = differences(replace(PROD, search_mode="hybrid", rewrite_reasoning_effort="low"))
    assert "search_mode=hybrid (운영 vector)" in diffs and "rewrite_reasoning_effort=low (운영 none)" in diffs


def test_write_settings_saves_json(tmp_path):
    path = write_settings(tmp_path / "run.csv", replace(PROD, top_k=52), label="v15")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "run.settings.json"
    assert data["label"] == "v15" and data["settings"]["top_k"] == 52 and data["differences"] == ["top_k=52 (운영 5)"]


def test_write_settings_records_experiment(tmp_path):
    # 실험 색인·질문 넓히기를 쓴 실행은 그 사실을 설정 기록에 남긴다(검색 개선 계획 1-5)
    path = write_settings(tmp_path / "r.csv", PROD, "x", experiment={"method": "m1"})
    assert json.loads(path.read_text(encoding="utf-8"))["experiment"] == {"method": "m1"}
