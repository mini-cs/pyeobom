"""v1.97 임베딩 large 다시 해 보기 Task 1: 4단계 코드. 확인용 세트는 읽지 않는다(tmp_path의 가짜 파일만)."""
import hashlib
import json
import subprocess

import pytest

from measure import stage2
from measure.emb_retry import (FU_COLUMNS, b3, build_test_set, cost_summary, load_backup_pages, old_chunk_refs_to_pages,
                               require_open_file, rule17, run_followups_same_run, split_by_method, time_summary,
                               write_open_file)


# ── 열기 파일 ──
def _git(repo, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


ADR041 = "docs/결정기록/041-임베딩-large-다시-측정-전-결정.md"


def _commit(repo, msg, *, with_041=True) -> str:
    if with_041:  # 열기 파일의 커밋에는 결정기록 041이 있어야 한다(검토 지적 6)
        (repo / ADR041).parent.mkdir(parents=True, exist_ok=True)
        (repo / ADR041).write_text(f"가짜 041 {msg}\n", encoding="utf-8")
        _git(repo, "add", ADR041)
    _git(repo, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-q", "--allow-empty", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _opened(tmp_path):
    """041이 든 커밋을 가리키는 열기 파일과 그 저장소."""
    repo = _repo(tmp_path)
    return _open_file(tmp_path / "open.json", _commit(repo, "A")), repo


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    return repo


def _open_file(path, commit):
    path.write_text(json.dumps({"decision_record": "041", "commit": commit, "written_at": "2026-11-24T09:00:00"}), encoding="utf-8")
    return path


def test_require_open_file_missing_stops(tmp_path):
    with pytest.raises(SystemExit):
        require_open_file(tmp_path / "stage4-open.json", repo=_repo(tmp_path))


def test_require_open_file_unknown_commit_stops(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "A")
    with pytest.raises(SystemExit):
        require_open_file(_open_file(tmp_path / "open.json", "f" * 40), repo=repo)


def test_require_open_file_accepts_ancestor_commit(tmp_path):
    repo = _repo(tmp_path)
    a = _commit(repo, "A")
    _commit(repo, "B")
    assert require_open_file(_open_file(tmp_path / "open.json", a), repo=repo)["commit"] == a


def test_require_open_file_non_ancestor_commit_stops(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "A")
    _git(repo, "switch", "-q", "-c", "side")
    side = _commit(repo, "side")
    _git(repo, "switch", "-q", "-")
    with pytest.raises(SystemExit):
        require_open_file(_open_file(tmp_path / "open.json", side), repo=repo)


def test_require_open_file_rev_name_stops(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "A")
    with pytest.raises(SystemExit):
        require_open_file(_open_file(tmp_path / "open.json", "HEAD"), repo=repo)


def test_require_open_file_commit_without_041_stops(tmp_path):
    repo = _repo(tmp_path)
    before = _commit(repo, "041 앞", with_041=False)
    _commit(repo, "041")
    with pytest.raises(SystemExit):
        require_open_file(_open_file(tmp_path / "open.json", before), repo=repo)


def test_write_open_file_refuses_existing(tmp_path):
    path = _open_file(tmp_path / "open.json", "f" * 40)
    with pytest.raises(SystemExit):
        write_open_file("f" * 40, path)
    assert json.loads(path.read_text(encoding="utf-8"))["written_at"] == "2026-11-24T09:00:00"  # 덮어쓰지 않음


# ── 옛 조각 번호 → 쪽 ──
def test_old_chunk_refs_page_conversion():
    backup = {12: ("manual-lg-fx25", 41), 13: ("manual-lg-fx25", 41)}
    assert old_chunk_refs_to_pages("chunk:12|chunk:13|manual:41", backup) == ("manual:41", 2)


def test_old_chunk_refs_keeps_guides_and_pages():
    assert old_chunk_refs_to_pages("chunk:300|guide:guide-lg-drum-errors|manual:7", {}) == ("chunk:300|guide:guide-lg-drum-errors|manual:7", 0)


def test_old_chunk_refs_unknown_id_stops():
    with pytest.raises(SystemExit):
        old_chunk_refs_to_pages("chunk:5", {})


@pytest.mark.parametrize("ref", ["chunk:0", "chunk:336", "chunk: 12", "chunk:x"])
def test_old_chunk_refs_out_of_range_stops(ref):  # 검토 지적 5: 옛 설명서(1~297)·가이드(298~335) 밖 번호는 조용히 두지 않음
    with pytest.raises(SystemExit):
        old_chunk_refs_to_pages(f"manual:1|{ref}", {12: ("manual-x", 41)})


def test_old_chunk_refs_strips_spaces():
    assert old_chunk_refs_to_pages(" chunk:12 | manual:7", {12: ("manual-x", 41)}) == ("manual:41|manual:7", 1)


def test_load_backup_pages_hash_mismatch_stops(tmp_path):
    path = tmp_path / "chunks-manual.jsonl"
    path.write_text(json.dumps({"id": 1, "doc_id": "manual-x", "page": 3, "content": "가짜"}) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_backup_pages(path, sha256="0" * 64)
    assert load_backup_pages(path, sha256=hashlib.sha256(path.read_bytes()).hexdigest()) == {1: ("manual-x", 3)}


# ── 확인용 세트 합치기(가짜 봉인 파일) ──
HEADER = "id,card,type,question,expected_ref,model_id\n"


def _sealed(tmp_path, body="p01-1,1,paraphrase,가짜 질문,chunk:12,washer-x\n"):
    sealed = tmp_path / "paraphrase_test.csv"
    sealed.write_bytes(("# 가짜 머리말\n" + HEADER + body).encode("utf-8"))
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"test_sha256": hashlib.sha256(sealed.read_bytes()).hexdigest()}), encoding="utf-8")
    return sealed, split


NEW = [{"id": "n3-1", "card": "3", "type": "paraphrase", "question": "새 가짜 질문", "expected_ref": "manual:9", "model_id": "washer-x"}]


def _build(tmp_path, sealed, split, new_rows=NEW, out=None, opened=None):
    open_file, repo = opened or _opened(tmp_path)
    return build_test_set(sealed, new_rows, split, {12: ("manual-x", 41)}, out or tmp_path / "out.csv",
                          open_file=open_file, repo=repo)


def test_build_test_set_sealed_hash_mismatch_stops(tmp_path):
    sealed, split = _sealed(tmp_path)
    split.write_text(json.dumps({"test_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(SystemExit):
        _build(tmp_path, sealed, split)
    assert not (tmp_path / "out.csv").exists()


def test_build_test_set_refuses_existing_out(tmp_path):
    sealed, split = _sealed(tmp_path)
    out = tmp_path / "out.csv"
    out.write_text("그대로", encoding="utf-8")
    with pytest.raises(SystemExit):
        _build(tmp_path, sealed, split, out=out)
    assert out.read_text(encoding="utf-8") == "그대로"


def test_build_test_set_merges_and_converts(tmp_path):
    from measure.search_eval import read_cases
    sealed, split = _sealed(tmp_path)
    out = tmp_path / "out.csv"
    got = _build(tmp_path, sealed, split, out=out)
    rows = read_cases(out)
    assert [r["id"] for r in rows] == ["p01-1", "n3-1"] and rows[0]["expected_ref"] == "manual:41"
    assert got == {"rows": 2, "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "converted_rows": 1}
    assert b"\r" not in out.read_bytes()


def test_build_test_set_without_open_file_stops(tmp_path):  # 검토 지적 1: 열기 파일 없이 봉인 파일을 읽지 않음
    sealed, split = _sealed(tmp_path)
    with pytest.raises(SystemExit):
        _build(tmp_path, sealed, split, opened=(tmp_path / "no-open.json", _repo(tmp_path)))
    assert not (tmp_path / "out.csv").exists()


def test_build_test_set_duplicate_new_ids_stops(tmp_path):  # 검토 지적 2가: 새 행끼리 겹쳐도 멈춤
    sealed, split = _sealed(tmp_path)
    with pytest.raises(SystemExit):
        _build(tmp_path, sealed, split, new_rows=NEW + [NEW[0] | {"question": "다른 가짜 질문"}])
    assert not (tmp_path / "out.csv").exists()


def test_build_test_set_trap_with_ref_stops(tmp_path):  # 검토 지적 2나: 함정에 기대 근거가 있으면 5위 안 분모에 들어감
    sealed, split = _sealed(tmp_path)
    with pytest.raises(SystemExit):
        _build(tmp_path, sealed, split, new_rows=[NEW[0] | {"type": "trap"}])
    assert not (tmp_path / "out.csv").exists()


def test_build_test_set_nontrap_empty_ref_stops(tmp_path):  # 사용자 결정: 함정이 아닌데 기대 근거가 비어도 멈춤
    sealed, split = _sealed(tmp_path)
    with pytest.raises(SystemExit):
        _build(tmp_path, sealed, split, new_rows=[NEW[0] | {"expected_ref": ""}])
    assert not (tmp_path / "out.csv").exists()


def test_build_test_set_trap_without_ref_passes(tmp_path):
    sealed, split = _sealed(tmp_path)
    got = _build(tmp_path, sealed, split, new_rows=[NEW[0] | {"type": "trap", "expected_ref": ""}])
    assert got["rows"] == 2


# ── 이어지는 질문: 같은 실행 안에서 방법 번갈아 ──
FU_ROWS = [{"dialog_id": d, "turn": t, "model_id": "washer-x", "question": f"{d}-{t}", "expected_rewrite_intent": "",
            "expected_found": "true", "expected_ref": "manual:1", "type": "base" if t == "1" else "pronoun"}
           for d, t in (("d01", "1"), ("d01", "2"), ("d02", "1"))]


def _fake_client_for(calls, histories=None, **extra):
    def client_for(method):
        def client(model_id, question, history):
            calls.append((method, question))
            if histories is not None:
                histories[(method, question)] = history
            return {"found": True, "answer": f"{method}:{question} 답", "question_masked": question, "cited_refs": ["manual:1"],
                    "retrieved_refs": ["manual:1"], "retrieved_chunk_ids": [7], "latency_ms": 100, "llm_ms": 60, "embed_ms": 3,
                    "rewrite_ms": None, "rewritten_question": None, "input_tokens": 100, "output_tokens": 10} | extra
        return client
    return client_for


def test_followups_same_run_alternates_methods():
    calls = []
    rows = run_followups_same_run(["m0", "emb_large"], "emb-retry-fu-r1", client_for=_fake_client_for(calls), rows=FU_ROWS)
    assert calls == [("m0", "d01-1"), ("m0", "d01-2"), ("emb_large", "d01-1"), ("emb_large", "d01-2"),
                     ("emb_large", "d02-1"), ("m0", "d02-1")]
    assert [list(r) for r in rows] == [FU_COLUMNS] * 6


def test_followups_history_stays_within_method():
    calls, histories = [], {}
    run_followups_same_run(["m0", "emb_large"], "x", client_for=_fake_client_for(calls, histories), rows=FU_ROWS)
    assert [h["answer"] for h in histories[("emb_large", "d01-2")]] == ["emb_large:d01-1 답"]
    assert [h["answer"] for h in histories[("m0", "d01-2")]] == ["m0:d01-1 답"]


def test_followups_cost_includes_rewrite_tokens():
    rows = run_followups_same_run(["m0"], "x", client_for=_fake_client_for([], rewrite_input_tokens=50, rewrite_output_tokens=5),
                                  rows=FU_ROWS[:1])
    assert (rows[0]["input_tokens"], rows[0]["output_tokens"]) == (150, 15)
    assert rows[0]["cost_usd"] == stage2.cost_usd(150, 15)


def test_followups_error_turn_is_recorded():
    def client_for(method):
        return lambda model_id, question, history: {"error_code": "AI_TIMEOUT"}
    rows = run_followups_same_run(["m0"], "x", client_for=client_for, rows=FU_ROWS[:1])
    assert rows[0]["error"] == "AI_TIMEOUT" and rows[0]["latency_ms"] is None and rows[0]["rule_blocked"] is False


# ── 시간·비용 집계 ──
def T(method, latency, llm="", *, run="r1", error="", blocked="False", found="True", cost="0.001"):
    return {"id": "x", "method": method, "latency_ms": str(latency), "llm_ms": str(llm), "run": run, "error": error,
            "rule_blocked": blocked, "found": found, "cost_usd": cost}


def test_time_summary_has_no_found_or_hit_keys():
    got = time_summary({"test": [T("m0", 1000, 600), T("emb_large", 1200, 700)], "q30": [T("m0", 900), T("emb_large", 950)]})
    text = json.dumps(got, ensure_ascii=False)
    assert "found" not in text and "hit" not in text


def test_time_summary_excludes_errors_and_blocked():
    rows = [T("m0", 1000), T("m0", 9000, error="AI_TIMEOUT"), T("m0", 0, blocked="True"), T("m0", ""), T("emb_large", 1500)]
    s = time_summary({"test": rows})["test"]["all"]
    assert s["base_ms"] == 1000.0 and s["cand_ms"] == 1500.0 and s["diff_ms"] == 500.0
    assert s["n"] == {"base": 1, "cand": 1}


def test_time_summary_reports_excluded_counts():  # 검토 지적 4: 뺀 행 수를 결과 CSV를 열지 않고 보고
    rows = [T("m0", 1000), T("m0", 9000, error="AI_TIMEOUT"), T("m0", 0, blocked="True"), T("m0", ""),
            T("emb_large", 1500), T("emb_large", 0, blocked="True", run="r2")]
    got = time_summary({"test": rows})["test"]
    assert got["all"]["excluded"] == {"base": {"error": 1, "rule_blocked": 1, "no_latency": 1},
                                      "cand": {"error": 0, "rule_blocked": 1, "no_latency": 0}}
    assert got["r2"]["excluded"]["cand"]["rule_blocked"] == 1 and got["r1"]["excluded"]["cand"]["rule_blocked"] == 0


def test_time_summary_pools_all_rows_not_set_means():
    # test 세트 1행(m0 1000, cand 2000), q30 3행(m0 1000, cand 1000) → pooled diff_ms == 250.0 (세트 평균의 평균이면 500)
    got = time_summary({"test": [T("m0", 1000), T("emb_large", 2000)],
                        "q30": [T("m0", 1000), T("emb_large", 1000)] * 3})
    assert got["pooled"]["all"]["diff_ms"] == 250.0
    assert got["test"]["all"]["diff_ms"] == 1000.0 and got["q30"]["all"]["diff_ms"] == 0.0


def test_time_summary_non_llm_is_latency_minus_llm():
    got = time_summary({"fu": [T("m0", 3000, 2000), T("emb_large", 3500, 2000, run="r2"), T("emb_large", 2500, "", run="r2")]})
    s = got["fu"]["all"]
    assert (s["base_non_llm_ms"], s["cand_non_llm_ms"], s["diff_non_llm_ms"]) == (1000.0, 1500.0, 500.0)
    assert s["cand_ms"] == 3000.0  # llm_ms가 빈 행은 전체 시간에는 들어가고 답변 AI 밖에서만 빠진다
    assert set(got["fu"]) == {"r1", "r2", "all"} and got["fu"]["r1"]["cand_ms"] is None


def test_cost_summary_ratio_without_errors():
    rows = [T("m0", 1000, cost="0.001"), T("m0", 1000, cost="0.001"),
            T("emb_large", 1000, cost="0.0015"), T("emb_large", "", error="AI_TIMEOUT", cost="0")]
    got = cost_summary({"test": rows})
    assert got["pooled"]["ratio"] == 0.75 and got["pooled"]["ratio_without_errors"] == 1.5
    assert got["test"]["ratio"] == 0.75
    assert "ratio_without_errors" not in cost_summary({"test": rows[:3]})["pooled"]


def test_split_by_method_keys():
    run = "emb-retry-q30-r1-2026-11-24"
    rows = [{"id": "q01", "method": "m0"}, {"id": "q01", "method": "emb_large"}, {"id": "q02", "method": "emb_large"}]
    got = split_by_method({run: rows})
    assert list(got) == [f"{run}-m0", f"{run}-emb_large"]
    assert [r["id"] for r in got[f"{run}-emb_large"]] == ["q01", "q02"]


# ── 판정 집계와 B-3 ──
def test_rule17():
    assert rule17(["정답", "정답(경계)"]) == "정답"; assert rule17(["정답", "환각"]) == "환각"; assert rule17(["정답", "오답"]) == "오답"


def test_rule17_blank_verdict_stops():
    with pytest.raises(ValueError):
        rule17(["정답", ""])


def test_rule17_boundary_labels():  # 사용자 결정: (경계)는 같은 종류로 센다. 환각(경계)도 환각(032 다시 세기와 같음)
    assert rule17(["정답", "환각(경계)"]) == "환각"
    assert rule17(["정답", "오답(경계)"]) == "오답"
    assert rule17(["정답(경계)", "정답(경계)"]) == "정답"


@pytest.mark.parametrize("label", ["경계: 정답", "정답 (경계)", "정담", "맞음", "환각?"])
def test_rule17_unknown_label_stops(label):  # 검토 지적 7: 여섯 이름 밖의 글은 조용히 오답으로 세지 않음
    with pytest.raises(ValueError):
        rule17(["정답", label])


def _b3_args(**over):
    args = {"test_hit5": {"production": {"hit5": 20, "denominator": 46}, "emb_large": {"hit5": 25, "denominator": 46}},
            "test17": {"m0": {"정답": 30, "환각": 0}, "emb_large": {"정답": 31, "환각": 0}},
            "q30_17": {"m0": {"정답": 25, "환각": 0}, "emb_large": {"정답": 23, "환각": 0}},
            "fu17": {"m0": {"정답": 25, "환각": 0}, "emb_large": {"정답": 24, "환각": 0}},
            "cost": {"pooled": {"ratio": 1.2}},
            "time": {"pooled": {"all": {"diff_ms": 1000.0, "diff_non_llm_ms": 400.0}}},
            "line": {"total_ms": 1500, "non_llm_ms": 500}}
    return args | over


def test_b3_all_pass_and_each_line():
    got = b3(**_b3_args())
    assert got["all_ok"] is True
    assert b3(**_b3_args(q30_17={"m0": {"정답": 25, "환각": 0}, "emb_large": {"정답": 22, "환각": 0}}))["q30_verdict"]["ok"] is False
    assert b3(**_b3_args(fu17={"m0": {"정답": 25, "환각": 0}, "emb_large": {"정답": 24, "환각": 1}}))["fu_verdict"]["ok"] is False
    assert b3(**_b3_args(test17={"m0": {"정답": 30, "환각": 0}, "emb_large": {"정답": 30, "환각": 0}}))["test_verdict"]["ok"] is False
    assert b3(**_b3_args(cost={"pooled": {"ratio": 1.2, "ratio_without_errors": 1.6}}))["cost"]["ok"] is False


def test_b3_10pp_rounds_up():
    # 분모 46 → 필요 +5, +4면 실패
    assert b3(**_b3_args())["test_hit5"]["ok"] is True
    got = b3(**_b3_args(test_hit5={"production": {"hit5": 20, "denominator": 46}, "emb_large": {"hit5": 24, "denominator": 46}}))
    assert got["test_hit5"]["ok"] is False and got["all_ok"] is False


def test_b3_time_line_both_parts():
    # line {"total_ms": 1500, "non_llm_ms": 500}: non_llm 600이면 실패
    over = {"time": {"pooled": {"all": {"diff_ms": 1000.0, "diff_non_llm_ms": 600.0}}}}
    assert b3(**_b3_args(**over))["time"]["ok"] is False
    assert b3(**_b3_args(**over, line={"total_ms": 1500, "non_llm_ms": None}))["time"]["ok"] is True
    assert b3(**_b3_args(line={"total_ms": 900, "non_llm_ms": None}))["time"]["ok"] is False


def _six(tmp_path, date="2026-11-24"):
    paths = []
    for s in ("test", "q30", "fu"):
        for r in ("r1", "r2"):
            p = tmp_path / f"emb-retry-{s}-{r}-{date}.csv"
            p.write_text(f"id,method\n{s}{r},m0\n", encoding="utf-8")
            paths.append(p)
    return paths


def test_read_results_adds_run_and_rejects_bad_name(tmp_path):
    from measure.emb_retry import read_results
    paths = _six(tmp_path)
    got = read_results(paths)
    assert set(got) == {"test", "q30", "fu"} and got["q30"] == [{"id": "q30r1", "method": "m0", "run": "r1"},
                                                                 {"id": "q30r2", "method": "m0", "run": "r2"}]
    bad = tmp_path / "emb-retry-test-2026-11-24.csv"
    bad.write_text("id,method\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        read_results(paths[1:] + [bad])


def test_read_results_duplicate_set_run_stops(tmp_path):  # 검토 지적 3: 같은 세트·회차를 두 번 세지 않음
    from measure.emb_retry import read_results
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(SystemExit):
        read_results(_six(tmp_path) + [_six(other, "2026-11-25")[2]])


def test_read_results_missing_file_stops(tmp_path):  # 검토 지적 3: 범위(세 세트 × 두 회차)가 다 있어야 냄
    from measure.emb_retry import read_results
    with pytest.raises(SystemExit):
        read_results(_six(tmp_path)[:5])
