from types import SimpleNamespace

from measure.stage2 import cost_usd, judgment_rows, method_order, summarize_methods, with_search


def test_with_search_replaces_only_search():
    deps = SimpleNamespace(search="base", embed_query="e", complete="c", diagnostic="d")
    import dataclasses

    @dataclasses.dataclass
    class D:
        search: object
        complete: object
    d = with_search(D("base", "c"), "new")
    assert (d.search, d.complete) == ("new", "c")
    assert deps.search == "base"


def test_method_order_rotates_per_case():
    assert method_order(["m0", "m2", "m12"], 0) == ["m0", "m2", "m12"]
    assert method_order(["m0", "m2", "m12"], 1) == ["m2", "m12", "m0"]
    assert method_order(["m0", "m2", "m12"], 3) == ["m0", "m2", "m12"]


def test_cost_uses_answer_model_prices():
    assert cost_usd(1_000_000, 0) == 0.10 and cost_usd(0, 1_000_000) == 0.50


def row(method, latency, inp=1000, out=200, blocked=False, found=True):
    return {"method": method, "latency_ms": latency, "input_tokens": inp, "output_tokens": out, "rule_blocked": blocked,
            "found": found, "cost_usd": cost_usd(inp, out)}


def test_summarize_methods_skips_rule_blocked_latency():
    rows = [row("m0", 4000), row("m0", 0, 0, 0, blocked=True), row("m2", 4600)]
    s = summarize_methods(rows)
    assert s["m0"]["latency_avg_ms"] == 4000 and s["m0"]["n"] == 2 and s["m2"]["latency_avg_ms"] == 4600
    assert s["m0"]["cost_per_q_usd"] == round((cost_usd(1000, 200) + 0) / 2, 7)


def test_judgment_rows_inherit_same_answers():
    rows = [{"id": "p01-1", "method": "m0", "answer": "A", "found": True, "cited_refs": "manual:43"},
            {"id": "p01-1", "method": "m2", "answer": "A", "found": True, "cited_refs": "manual:43"},
            {"id": "p01-1", "method": "m12", "answer": "B", "found": True, "cited_refs": "manual:44"}]
    j = judgment_rows(rows, ["m0", "m2", "m12"])
    assert j == [{"id": "p01-1", "m0": "A", "m2": "A", "m12": "B", "m2_same_as": "m0", "m12_same_as": ""}]


import random  # noqa: E402

from measure.stage2 import blind_sheet  # noqa: E402


def test_blind_sheet_hides_methods_shuffles_and_groups_same_answers():
    rows = [{"id": "p01-1", "method": m, "answer": a} for m, a in (("m0", "A"), ("m2", "B"), ("m12", "A"))] + \
           [{"id": "p02-1", "method": m, "answer": "C"} for m in ("m0", "m2", "m12")]
    sheet, key = blind_sheet(rows, random.Random(7))
    assert [s["id"] for s in sheet] == ["p01-1", "p02-1"]
    assert sorted(a["text"] for a in sheet[0]["answers"]) == ["A", "B"] and len(sheet[1]["answers"]) == 1  # 같은 답은 한 번만
    assert all("method" not in a for s in sheet for a in s["answers"])  # 판정지에는 방법 이름이 없다
    numbers = [a["no"] for s in sheet for a in s["answers"]]
    assert len(set(numbers)) == len(numbers)
    by_no = {a["no"]: a["text"] for s in sheet for a in s["answers"]}
    assert {(k["id"], k["method"]) for k in key} == {(r["id"], r["method"]) for r in rows}  # 대응표는 모든 답을 담는다
    assert all(by_no[k["no"]] == next(r["answer"] for r in rows if (r["id"], r["method"]) == (k["id"], k["method"])) for k in key)


from measure.stage2 import COLUMNS, result_row  # noqa: E402


def test_result_row_keeps_chunk_ids():
    case = {"id": "p08-2", "card": "8", "type": "paraphrase", "question": "q", "expected_ref": "manual:42"}
    resp = {"found": True, "answer": "a", "cited_refs": ["manual:42"], "retrieved_refs": ["manual:42", "guide:g"],
            "retrieved_chunk_ids": [180, 317], "latency_ms": 10, "llm_ms": 5, "embed_ms": 1, "diagnostic_added": False}
    r = result_row(case, "m2", resp, "", {"input_tokens": 100, "output_tokens": 10})
    assert r["retrieved_chunk_ids"] == "180|317" and r["retrieved_refs"] == "manual:42|guide:g"
    assert set(r) == set(COLUMNS)


from measure.stage2 import write_blind  # noqa: E402


def _csv(path, rows):
    import csv as _csv_mod
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = _csv_mod.DictWriter(f, fieldnames=["id", "method", "type", "question", "expected_ref", "answer"])
        w.writeheader()
        w.writerows(rows)


def test_write_blind_merges_runs_into_one_sheet(tmp_path, monkeypatch):  # v1.7 3단계: 두 회차를 한 장에, 같은 답은 묶음
    import json
    import measure.stage2 as s2
    monkeypatch.setattr(s2, "ROOT", tmp_path)
    (tmp_path / "measure" / "out").mkdir(parents=True)
    base = {"type": "paraphrase", "question": "질문", "expected_ref": "manual:1"}
    r1, r2 = tmp_path / "v17-s3-r1-2026-11-17.csv", tmp_path / "v17-s3-r2-2026-11-17.csv"
    _csv(r1, [base | {"id": "p01-1", "method": "m0", "answer": "A"}, base | {"id": "p01-1", "method": "strip_800", "answer": "B"}])
    _csv(r2, [base | {"id": "p01-1", "method": "m0", "answer": "A"}, base | {"id": "p01-1", "method": "strip_800", "answer": "C"}])
    sheet = write_blind([r1, r2], {}, label="v17-s3")
    assert sheet.name == "v17-s3-blind-sheet.md"
    text = sheet.read_text(encoding="utf-8")
    assert text.count("**답 ") == 3  # A는 두 회차가 같아 한 번만
    assert "m0" not in text and "strip_800" not in text and "r1" not in text
    key = json.loads((tmp_path / "measure" / "out" / "v17-s3-blind-key.json").read_text(encoding="utf-8"))
    assert {(k["method"], k["run"]) for k in key} == {("m0", r1.stem), ("strip_800", r1.stem), ("m0", r2.stem), ("strip_800", r2.stem)}
    no = {(k["method"], k["run"]): k["no"] for k in key}
    assert no[("m0", r1.stem)] == no[("m0", r2.stem)] != no[("strip_800", r1.stem)]


def test_write_blind_single_csv_keeps_old_names(tmp_path, monkeypatch):
    import measure.stage2 as s2
    monkeypatch.setattr(s2, "ROOT", tmp_path)
    (tmp_path / "measure" / "out").mkdir(parents=True)
    r = tmp_path / "stage2-pdev-2026-11-10.csv"
    _csv(r, [{"id": "p01-1", "method": "m0", "type": "paraphrase", "question": "q", "expected_ref": "", "answer": "A"}])
    assert write_blind(r, {}).name == "stage2-blind-sheet.md"
