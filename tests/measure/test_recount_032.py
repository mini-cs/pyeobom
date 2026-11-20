import csv

from measure.recount_032 import collect_targets, load_rows, parse_verdict, recount_a3

FIELDS = ["id", "model_id", "question", "answer", "human_verdict"]


def _write(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)


def test_parse_verdict_reads_boundary_tags_and_answer_no():
    assert parse_verdict("정답 [AI 일치] (답 396)") == ("정답", False, "396")
    assert parse_verdict("정답(경계) 메모: 설명 (답 385)") == ("정답", True, "385")
    assert parse_verdict("오답(경계) 메모: 누락 (답 888)") == ("오답", True, "888")
    assert parse_verdict("정답(경계) / 메모: 진짜 없어?") == ("정답", True, "")
    assert parse_verdict("오답 [기준: 찾지 못함]") == ("오답", False, "")


def test_collect_keeps_only_correct_and_boundary_correct(tmp_path):
    _write(tmp_path / "a-r1.csv", [
        {"id": "q01", "model_id": "m", "question": "질문1", "answer": "답1", "human_verdict": "정답 [AI 일치] (답 315)"},
        {"id": "q02", "model_id": "m", "question": "질문2", "answer": "답2", "human_verdict": "정답(경계) 메모: x (답 267)"},
        {"id": "q03", "model_id": "m", "question": "질문3", "answer": "답3", "human_verdict": "오답 [규칙: 찾지 못함] (답 12)"},
        {"id": "q04", "model_id": "m", "question": "질문4", "answer": "답4", "human_verdict": "오답(경계) 메모: y (답 13)"},
        {"id": "q05", "model_id": "m", "question": "질문5", "answer": "답5", "human_verdict": "환각 (답 14)"},
    ])
    runs = [("v17-s4", "a-r1", "m0", "r1", "v17-s4")]
    got = collect_targets(runs=runs, root=tmp_path)
    assert [(t["qid"], t["old_verdict"], t["answer_no"], t["sheet"]) for t in got] == [
        ("q01", "정답", "315", "v17-s4"), ("q02", "정답(경계)", "267", "v17-s4")]
    assert got[0]["run"] == "v17-s4" and got[0]["method"] == "m0" and got[0]["round"] == "r1"
    assert len(load_rows(runs=runs, root=tmp_path)) == 5


def _row(method, qid, rnd, verdict, run="v17-s4"):
    return {"run": run, "method": method, "qid": qid, "round": rnd, "old_verdict": verdict}


def test_recount_applies_17_rule():
    old = [_row("m0", "q1", "r1", "정답"), _row("m0", "q1", "r2", "정답(경계)"),   # 두 회차 정답 → 정답
           _row("m0", "q2", "r1", "정답"), _row("m0", "q2", "r2", "정답"),         # 새 판정으로 한 회차 환각 → 환각, 정답 아님
           _row("m0", "q3", "r1", "정답"), _row("m0", "q3", "r2", "오답"),         # 한 회차 오답 → 정답 아님
           _row("strip_800", "q1", "r1", "정답"), _row("strip_800", "q1", "r2", "정답")]
    new = {("v17-s4", "m0", "q2", "r2"): "환각"}
    got = recount_a3(old, new)
    assert got[("v17-s4", "m0")] == {"correct": 1, "hallucination": 1, "denominator": 3}
    assert got[("v17-s4", "strip_800")] == {"correct": 1, "hallucination": 0, "denominator": 1}
    assert recount_a3(old, {})[("v17-s4", "m0")] == {"correct": 2, "hallucination": 0, "denominator": 3}
