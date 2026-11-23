import csv
import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.answer.refine import RefineResult
from app.ask.service import Deps
from measure.refine_eval import (LIMIT_MS, METHOD, PREVIEW, PREVIEW_SHA256, code_tokens, latency_b2, missing_tokens,
                                 new_tokens, refine_rows, run_preview, stage3_report, with_candidate)
from measure.stage2 import PRICE_IN, PRICE_OUT

C = lambda ref, content="": SimpleNamespace(ref=ref, id=ref, content=content)


def test_preview_file_sha_is_fixed():
    data = PREVIEW.read_bytes()
    assert hashlib.sha256(data).hexdigest() == PREVIEW_SHA256 == "10af0c4f2901cf4d4ca7c8b1ea213f75c60e9d5416971be3535af0c9cc70021c"
    assert len(list(csv.DictReader(data.decode("utf-8").splitlines()))) == 20


def test_code_tokens_skip_masked_parts():
    assert code_tokens("문이 안 열려요 010-****-****으로 [이메일] CH 05") == ["CH", "05"]


def test_missing_and_new_tokens():
    assert missing_tokens("4E라고 떠요", "4e 오류 표시") == []
    assert missing_tokens("CH 05가 깜빡여요", "CH 표시 깜빡임") == ["05"]
    assert new_tokens("문이 안 열려요", "LG 세탁기 문 잠김 D3") == ["LG", "D3"]


def _clock(step_s):
    t = [0.0]

    def timer():
        t[0] += step_s  # 부를 때마다 step_s씩: 다듬기 앞뒤 두 번 부르면 그 차이가 step_s
        return t[0]
    return timer


PREVIEW_CASES = [{"id": "r01", "model_id": "aircon-lg-sq06fa1wds", "question": "CH 05가 깜빡여요"},
                 {"id": "r02", "model_id": "washer-lg-fx25", "question": "문이 안 열려요 010-1234-5678"}]


def test_run_preview_stops_on_missing_token_and_slow_avg():
    seen = []

    def refine(q, model_id):
        seen.append(q)
        return RefineResult("CH 표시 깜빡임", True, "ok") if q.startswith("CH") else RefineResult(q, False, "same")

    summary, rows = run_preview(PREVIEW_CASES, refine, timer=_clock(2.0))
    assert summary["missing"] == {"r01": ["05"]} and summary["refine_ms_avg"] == 2000 and summary["refine_ms_max"] == 2000
    assert summary["stop"] == ["missing_tokens", "refine_avg_over_1500ms"]
    assert "1234-5678" not in str(seen) and "1234-5678" not in str(rows)  # 다듬기에는 가린 질문만 간다
    assert rows[0]["refined"] == "CH 표시 깜빡임" and rows[0]["reason"] == "ok"


def test_run_preview_counts_reasons_and_cost():
    results = iter([RefineResult("CH 05 표시 깜빡임 오류", True, "ok", {"input_tokens": 300, "output_tokens": 20}),
                    RefineResult("문이 안 열려요", False, "timeout")])
    summary, _ = run_preview(PREVIEW_CASES, lambda q, m: next(results), timer=_clock(0.5))
    assert summary["n"] == 2 and summary["reasons"] == {"ok": 1, "timeout": 1} and summary["stop"] == []
    assert (summary["input_tokens"], summary["output_tokens"]) == (300, 20)
    assert summary["cost_usd"] == pytest.approx((300 * PRICE_IN + 20 * PRICE_OUT) / 1_000_000)
    assert summary["refine_ms_avg"] == 500 and summary["missing"] == {} and summary["new"] == {}


class Fake:
    def __init__(self, results, diag=()):
        self.results, self.diag = results, list(diag)
        self.refined, self.embedded, self.embedded_many, self.searched, self.searched_many, self.diag_q = [], [], [], [], [], []

    def refine_with(self, result_for):
        def refine(q, model_id):
            self.refined.append(q)
            return result_for(q)
        return refine

    def embed(self, text):
        self.embedded.append(text)
        return [0.0]

    def embed_queries(self, texts):
        self.embedded_many.append(texts)
        return [[0.0], [1.0]]

    def search(self, model_id, vec, text, k):
        self.searched.append((model_id, text, k))
        return self.results

    def search_queries(self, model_id, vecs, k):
        self.searched_many.append((model_id, vecs, k))
        return self.results

    def diagnostic(self, model_id):
        return self.diag

    def rows(self, cases, result_for, brand="LG"):
        return refine_rows(cases, self.refine_with(result_for), self.embed, self.embed_queries, self.search,
                           self.search_queries, self.diagnostic, brand=lambda model_id: brand)


def case(q, id_, ref="manual:42", model="washer-lg-fx25"):
    return {"id": id_, "model_id": model, "question": q, "expected_ref": ref}


def test_refine_rows_dual_search_only_when_used():
    f = Fake([C("manual:7"), C("manual:42")])
    cases = [case("문이 안 열려요", "p01"), case("세제는 어디에", "p02")]
    rows = f.rows(cases, lambda q: RefineResult(q + " 도어 잠김", True, "ok") if q.startswith("문") else RefineResult(q, False, "timeout"))
    assert f.embedded_many == [["문이 안 열려요", "문이 안 열려요 도어 잠김"]]
    assert f.searched_many == [("washer-lg-fx25", [[0.0], [1.0]], 100)]
    assert f.embedded == ["세제는 어디에"] and f.searched == [("washer-lg-fx25", "세제는 어디에", 100)]
    assert [r["rank"] for r in rows] == [2, 2]
    assert (rows[0]["refined"], rows[0]["refine_reason"]) == ("문이 안 열려요 도어 잠김", "ok")
    assert (rows[1]["refined"], rows[1]["refine_reason"]) == ("", "timeout")
    assert {"refine_ms", "input_tokens", "output_tokens", "top5", "hit5_or_diag"} <= rows[0].keys()


def test_refine_rows_refines_each_case_once():
    f = Fake([C("manual:42")])
    cases = [case("문이 안 열려요", "p01"), case("010-1234-5678 세제는 어디에", "p02"), case("함정", "t01", ref="")]
    rows = f.rows(cases, lambda q: RefineResult(q, False, "same"))
    assert len(f.refined) == 2 and len(rows) == 2  # 기대 근거가 없는 행은 run_eval처럼 뺀다
    assert "1234-5678" not in str(f.refined)


def test_refine_rows_diagnostic_uses_original_question():
    # 다듬은 문장에만 있는 코드(OE)로 진단 쪽을 덧붙이지 않는다. 원래 질문엔 코드가 없다
    f = Fake([C("manual:7", "배수 필터 청소")], diag=[C("manual:34", "스마트 진단")])
    rows = f.rows([case("물이 안 빠져요", "p01")], lambda q: RefineResult("물이 안 빠져요 OE 에러 배수", True, "ok"))
    assert rows[0]["diag"] == ""


def _lat_rows(diff, n=12):
    rows = []
    for run in ("r1", "r2"):
        for i in range(n):
            rows.append({"run": run, "id": f"p{i}", "method": "m0", "found": "True", "rule_blocked": "False", "latency_ms": "1000"})
            rows.append({"run": run, "id": f"p{i}", "method": METHOD, "found": "True", "rule_blocked": "False",
                         "latency_ms": str(1000 + diff)})
    return rows


def test_latency_b2_uses_all_answers_and_1500():
    ok = latency_b2(_lat_rows(1500))
    assert ok["pairs"] == 24 and ok["basis"] == "all" and ok["diff_ms"] == ok["all_diff_ms"] == 1500 and ok["pass"] is True
    assert latency_b2(_lat_rows(1501))["pass"] is False and LIMIT_MS == 1500


def test_stage3_report_refuses_same_run_names(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    paths = [tmp_path / "a" / "refine-s3.csv", tmp_path / "b" / "refine-s3.csv"]
    for p in paths:
        p.write_text("id,method,found,rule_blocked,latency_ms,cost_usd,refine_ms,refine_reason\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        stage3_report(paths)


def test_with_candidate_only_replaces_refine(monkeypatch):
    import measure.refine_eval as refine_eval
    calls = []
    monkeypatch.setattr(refine_eval, "refine_question",
                        lambda q, product, model_name, settings: calls.append((q, product, model_name)) or RefineResult(q, False, "same"))
    base = Deps(embed_query=lambda q: [0.0], search=lambda *a: [], complete=lambda m: "", supported_ids={"washer-lg-fx25"},
                official_url=lambda m: "")
    d = with_candidate(base, {"washer-lg-fx25": {"name": "LG 드럼세탁기"}}, settings=None)
    d.refine("문이 안 열려요", "washer-lg-fx25")
    assert calls == [("문이 안 열려요", "LG 드럼세탁기", "gpt-6-luna")]
    assert replace(d, refine=base.refine) == base



def test_refine_rows_other_brand_uses_single_search():
    # 운영 서비스와 같은 검사(guard_message): 다듬은 문장에 다른 브랜드가 섞이면 버리고 원래 질문만으로 검색
    f = Fake([C("manual:42")])
    rows = f.rows([case("문이 안 열려요", "p01")], lambda q: RefineResult("문이 안 열려요 삼성 세탁기 도어", True, "ok"), brand="LG")
    assert f.embedded_many == [] and f.searched_many == []
    assert f.embedded == ["문이 안 열려요"] and f.searched == [("washer-lg-fx25", "문이 안 열려요", 100)]
    assert (rows[0]["refined"], rows[0]["refine_reason"], rows[0]["rank"]) == ("", "other_brand", 1)
