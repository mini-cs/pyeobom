from types import SimpleNamespace

from measure.cr_investigation import count_relevant_chunks, hit_rate
from measure.run_deepeval import cr_verdicts


def _rec(*contexts):
    return {"contextual_relevancy_verdicts": [[{"statement": f"s{i}", "verdict": v} for i, v in enumerate(c)] for c in contexts]}


def test_count_relevant_chunks_counts_chunks_with_any_yes_statement():
    # 조각 3개 중 1개에만 관련 문장(문장 단위 판정 → 조각 안에 yes가 하나라도 있으면 관련)
    assert count_relevant_chunks(_rec(["no", "no"], ["no", "yes", "no"], ["no"])) == 1


def test_count_relevant_chunks_zero_when_no_relevant_statement():
    assert count_relevant_chunks(_rec(["no"], ["no", "no"])) == 0


def test_hit_rate_counts_rows_whose_expected_ref_is_cited_or_in_top5():
    rows = [
        {"expected_ref": "manual:42", "cited_refs": "manual:42", "retrieved_refs": "manual:42|manual:43"},           # 인용
        {"expected_ref": "manual:41", "cited_refs": "", "retrieved_refs": "a|b|c|d|manual:41|f"},                     # 5위
        {"expected_ref": "manual:41", "cited_refs": "", "retrieved_refs": "a|b|c|d|e|manual:41"},                     # 6위(밖)
        {"expected_ref": "", "cited_refs": "", "retrieved_refs": "a"},                                                 # 기대 근거 없음 → 제외
    ]
    assert hit_rate(rows) == 2 / 3


def test_cr_verdicts_saves_statement_verdicts_per_chunk():
    v = lambda s, y: SimpleNamespace(statement=s, verdict=y)
    metric = SimpleNamespace(verdicts_list=[SimpleNamespace(verdicts=[v("a", "yes"), v("b", "no")]), SimpleNamespace(verdicts=[])])
    assert cr_verdicts(metric) == [[{"statement": "a", "verdict": "yes"}, {"statement": "b", "verdict": "no"}], []]
