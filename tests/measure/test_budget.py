from measure.budget import check_budget


def test_check_budget_allows_within_cap():
    ledger = [{"item": "langfuse", "estimate_usd": 0.5}]
    assert check_budget(ledger, 1.0) is True


def test_check_budget_blocks_over_cap():
    ledger = [{"item": "deepeval", "estimate_usd": 1.8}]
    assert check_budget(ledger, 0.3) is False


def test_check_budget_cap_is_two_dollars_by_default():
    assert check_budget([], 2.0) is True
    assert check_budget([], 2.01) is False
