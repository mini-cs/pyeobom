"""2차 모델 추가 시간 기록지 읽기·합계·개선 판정(설계 9.3-2·3·6). 측정 전에 고정."""
import csv
from datetime import datetime

KINDS = ("사람", "기다림", "질문 쓰기", "판정", "배포 대기", "멈춤")
COLUMNS = ("step", "kind", "start", "end", "note")
TIME_FORMAT = "%Y-%m-%d %H:%M"


def read_timelog(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"시간 기록지에 열이 없음: {', '.join(missing)}")
        rows = []
        for line, r in enumerate(reader, start=2):
            if r["kind"] not in KINDS:
                raise ValueError(f"{line}번째 줄: 모르는 kind {r['kind']!r}")
            try:
                start, end = (datetime.strptime(r[k], TIME_FORMAT) for k in ("start", "end"))
            except ValueError:
                raise ValueError(f"{line}번째 줄: 시각은 YYYY-MM-DD HH:MM") from None
            if end <= start:
                raise ValueError(f"{line}번째 줄: end가 start보다 뒤가 아님")
            rows.append({**r, "start": start, "end": end, "line": line})
    ordered = sorted(rows, key=lambda r: r["start"])
    for prev, cur in zip(ordered, ordered[1:]):
        if cur["start"] < prev["end"]:
            raise ValueError(f"{cur['line']}번째 줄: {prev['line']}번째 줄과 시간이 겹침")
    return rows


def summarize(rows: list[dict]) -> dict:
    minutes = {k: 0 for k in KINDS}
    for r in rows:
        minutes[r["kind"]] += int((r["end"] - r["start"]).total_seconds() // 60)
    return {
        "extra_work_min": minutes["사람"] + minutes["기다림"],
        "total_min": sum(minutes.values()) - minutes["멈춤"],
        "excluded_min": minutes["질문 쓰기"] + minutes["판정"] + minutes["배포 대기"],
        "paused_min": minutes["멈춤"],
        "person_steps": sum(r["kind"] == "사람" for r in rows),
    }


def improved(before: dict, after: dict) -> bool:
    return after["extra_work_min"] <= before["extra_work_min"] / 2 and after["person_steps"] < before["person_steps"]
