from measure.lighthouse import summarize_runs


def _report(score, lcp, cls=0.0, tbt=0, fcp=1000):
    return {
        "categories": {"performance": {"score": score}},
        "audits": {
            "largest-contentful-paint": {"numericValue": lcp},
            "cumulative-layout-shift": {"numericValue": cls},
            "total-blocking-time": {"numericValue": tbt},
            "first-contentful-paint": {"numericValue": fcp},
        },
    }


def test_summarize_runs_takes_median_of_three():
    reports = [_report(0.80, 2000), _report(0.90, 2600), _report(0.85, 2200)]
    summary = summarize_runs(reports)
    assert summary["performance"] == 0.85
    assert summary["lcp_ms"] == 2200
    assert summary["runs"] == 3


def test_summarize_runs_reports_all_metrics():
    reports = [_report(0.9, 2000, cls=0.1, tbt=50, fcp=900), _report(0.9, 2000, cls=0.3, tbt=150, fcp=1100),
               _report(0.9, 2000, cls=0.2, tbt=100, fcp=1000)]
    summary = summarize_runs(reports)
    assert summary["cls"] == 0.2
    assert summary["tbt_ms"] == 100
    assert summary["fcp_ms"] == 1000
