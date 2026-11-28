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


def test_vercel_json_has_three_daily_wake_crons():
    # Hobby는 작업마다 하루 1번(두 번 이상 도는 식은 배포 실패). 2차 Task 11 ③ Supabase 깨우기
    import json
    from pathlib import Path
    config = json.loads((Path(__file__).resolve().parents[2] / "vercel.json").read_text(encoding="utf-8"))
    crons = config["crons"]
    assert [c["path"] for c in crons] == ["/api/wake"] * 3
    hours = []
    for c in crons:
        minute, hour, dom, month, dow = c["schedule"].split()
        assert minute.isdigit() and 1 <= int(minute) <= 59
        assert hour.isdigit() and (dom, month, dow) == ("*", "*", "*")
        hours.append(int(hour))
    assert hours == [1, 9, 17]
