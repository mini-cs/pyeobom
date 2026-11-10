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
