from fastapi import FastAPI

def test_vercel_entrypoint_exposes_app():
    # Vercel은 루트 index.py의 FastAPI 인스턴스 `app`을 자동 감지한다 (결정기록 013)
    import index
    assert isinstance(index.app, FastAPI)


def test_vercel_json_pins_framework_and_region():
    # 설정은 대시보드가 아니라 저장소에 둔다(결정기록 013). 함수 지역은 Neon(ap-southeast-1)과 맞춘 sin1(결정기록 018)
    import json
    from pathlib import Path
    config = json.loads((Path(__file__).resolve().parents[2] / "vercel.json").read_text(encoding="utf-8"))
    assert config["framework"] == "fastapi" and config["regions"] == ["sin1"]
