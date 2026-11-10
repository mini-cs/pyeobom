from types import SimpleNamespace

import pytest

from measure.search_eval import metrics, read_cases, run_eval

C = lambda ref, content="": SimpleNamespace(ref=ref, id=ref, content=content)


def test_metrics_hit_rates_and_mean_reciprocal_rank():
    m = metrics([1, 3, None, 6])
    assert m["n"] == 4
    assert (m["hit@1"], m["hit@3"], m["hit@5"]) == (0.25, 0.5, 0.5)
    assert m["mrr"] == pytest.approx((1 + 1 / 3 + 0 + 1 / 6) / 4)


def test_metrics_of_nothing():
    assert metrics([]) == {"n": 0, "hit@1": 0.0, "hit@3": 0.0, "hit@5": 0.0, "mrr": 0.0}


class Fake:
    def __init__(self, results, diag=()):
        self.results, self.diag, self.embedded, self.searched = results, list(diag), [], []

    def embed(self, text):
        self.embedded.append(text)
        return [0.0]

    def search(self, model_id, vec, text, k):
        self.searched.append((model_id, text, k))
        return self.results

    def diagnostic(self, model_id):
        return self.diag


def case(q="세탁조 청소는?", ref="manual:42", model="washer-lg-fx25", id_="q01"):
    return {"id": id_, "model_id": model, "question": q, "expected_ref": ref}


def test_masks_pii_before_embedding_and_searches_top20_of_that_model():
    fake = Fake([C("manual:9"), C("manual:42")])
    rows = run_eval([case(q="010-1234-5678로 연락 주세요. 세탁조 청소는?")], fake.embed, fake.search, fake.diagnostic)
    assert "010-1234-5678" not in fake.embedded[0]
    assert fake.searched == [("washer-lg-fx25", fake.embedded[0], 20)]
    assert rows[0]["rank"] == 2 and rows[0]["top5"] == "manual:9|manual:42"


def test_transform_runs_after_masking_and_feeds_search():
    fake = Fake([C("manual:42")])
    seen = []
    def transform(text, model_id):
        seen.append(text)
        return text + " 통살균"
    run_eval([case(q="010-1234-5678 세탁조 청소")], fake.embed, fake.search, fake.diagnostic, transform=transform)
    assert "010-1234-5678" not in seen[0]
    assert fake.embedded == [seen[0] + " 통살균"] and fake.searched[0][1] == seen[0] + " 통살균"


def test_rows_without_expected_ref_are_skipped():
    fake = Fake([C("manual:42")])
    rows = run_eval([case(ref=""), case(id_="q02")], fake.embed, fake.search, fake.diagnostic)
    assert [r["id"] for r in rows] == ["q02"]


def test_diagnostic_pages_follow_the_production_rule():
    fake = Fake([C("manual:9", "필터 청소")] + [C(f"manual:{i}") for i in range(10, 30)], diag=[C("manual:34")])
    row = run_eval([case(q="CH10이 떴어요", ref="manual:34", model="aircon-lg-sq06fa1wds")],
                   fake.embed, fake.search, fake.diagnostic)[0]
    assert row["rank"] is None and row["diag"] == "manual:34" and row["hit5_or_diag"] is True
    plain = run_eval([case()], fake.embed, fake.search, fake.diagnostic)[0]
    assert plain["diag"] == ""  # 코드가 없는 질문은 진단 쪽을 덧붙이지 않음


def test_read_cases_skips_comment_lines(tmp_path):
    p = tmp_path / "cases.csv"
    p.write_text("# 메모\nid,model_id,question,expected_ref\nq1,m,질문,manual:1\n", encoding="utf-8-sig")
    assert read_cases(p) == [{"id": "q1", "model_id": "m", "question": "질문", "expected_ref": "manual:1"}]
