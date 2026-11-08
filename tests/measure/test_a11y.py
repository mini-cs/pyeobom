from measure.a11y import summarize_violations


def test_summarize_violations_counts_by_impact():
    results = {"violations": [
        {"id": "color-contrast", "impact": "serious", "nodes": [{}]},
        {"id": "region", "impact": "minor", "nodes": [{}]},
    ]}
    summary = summarize_violations(results)
    assert summary["total"] == 2
    assert summary["by_impact"] == {"critical": 0, "serious": 1, "moderate": 0, "minor": 1}
    assert summary["rules"] == ["color-contrast", "region"]


def test_summarize_violations_empty():
    summary = summarize_violations({"violations": []})
    assert summary["total"] == 0
    assert summary["rules"] == []
