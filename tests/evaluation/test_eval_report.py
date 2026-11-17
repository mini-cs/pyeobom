"""커밋되는 평가 리포트 머리: --bundle 실행이면 명령과 한 벌 이름을 적고, 아니면 예전 글자 그대로."""
from types import SimpleNamespace

from evaluation.__main__ import write_report

SUMMARY = {"accuracy": 0, "ref_hit_rate": 0, "hallucination_rate": 0, "error_rate": 0, "latency_avg_ms": 0,
           "latency_max_ms": 0, "failures": {"retrieval": 0, "answer": 0}}


def head(tmp_path, bundle):
    path = tmp_path / "r.md"
    write_report(path, "lab", SimpleNamespace(label="lab", prompt="v1", search="vector", bundle=bundle), SUMMARY, [])
    return path.read_text(encoding="utf-8").splitlines()[:6]


def test_report_head_without_bundle_unchanged(tmp_path):
    lines = head(tmp_path, None)
    assert lines[2] == "- 실행: `python -m evaluation --label lab --prompt v1 --search vector`"
    assert lines[3] == "- 문항: `evaluation/questions.csv` 30개 (2026-10-28 고정)"
    assert lines[4].startswith("- 실행 설정: ")


def test_report_head_with_bundle(tmp_path):
    lines = head(tmp_path, "v17-a")
    assert lines[2] == "- 실행: `python -m evaluation --label lab --prompt v1 --search vector --bundle v17-a`"
    assert lines[3] == "- 문항: `evaluation/questions.csv` 30개 (2026-10-28 고정)"
    assert lines[4] == "- v1.7 실험 조각 한 벌: v17-a"
    assert lines[5].startswith("- 실행 설정: ")
