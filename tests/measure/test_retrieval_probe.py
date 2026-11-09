from types import SimpleNamespace

from measure.retrieval_probe import expected_rank, compare

C = lambda ref: SimpleNamespace(ref=ref)


def test_expected_rank_is_position_of_expected_chunk():
    assert expected_rank([C("manual:1"), C("manual:2"), C("manual:42")], ["manual:42"]) == 3


def test_expected_rank_none_when_outside_depth():
    results = [C(f"manual:{i}") for i in range(100, 125)] + [C("manual:42")]
    assert expected_rank(results, ["manual:42"]) is None


def test_expected_rank_takes_best_of_several_expected_refs():
    results = [C("manual:9"), C("manual:43"), C("manual:7"), C("manual:42")]
    assert expected_rank(results, ["manual:42", "manual:43"]) == 2


def test_compare_treats_none_as_worse_than_any_rank():
    assert compare(2, 5) == "better" and compare(5, 2) == "worse" and compare(3, 3) == "same"
    assert compare(4, None) == "better" and compare(None, 4) == "worse" and compare(None, None) == "same"
