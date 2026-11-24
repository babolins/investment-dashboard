"""
Unit tests for the rebalance / buy-guidance engine.
"""

import pytest
from pydantic import ValidationError

from app.models.config import PALETTE, AllocationConfig, CategoryConfig
from app.models.schemas import (
    AllocationBreakdown,
    CategoryAllocation,
    RebalanceAPIRequest,
    RebalanceRequest,
)
from app.services.config_store import ConfigError
from app.services.rebalance import _largest_remainder_round, compute_rebalance

US, INTL, BONDS = "US Stocks", "International", "Bonds"


def make_breakdown(
    values: dict[str, float], excluded: float = 0, unassigned: float = 0
) -> AllocationBreakdown:
    included = sum(values.values())

    def pct(v: float) -> float:
        return (v / included * 100) if included else 0.0

    return AllocationBreakdown(
        categories=[
            CategoryAllocation(category=name, current_value=v, percent_of_included=pct(v))
            for name, v in values.items()
        ],
        included_value=included,
        excluded_value=excluded,
        unassigned_value=unassigned,
        total_value=included + excluded + unassigned,
    )


def make_config() -> AllocationConfig:
    return AllocationConfig(
        categories={
            US: CategoryConfig(buy_symbol="VTI", color=PALETTE[0]),
            INTL: CategoryConfig(buy_symbol="VXUS", color=PALETTE[1]),
            BONDS: CategoryConfig(buy_symbol="BND", color=PALETTE[2]),
        },
        direct_mappings={},
        fractional_mappings={},
        exclusions=[],
    )


def make_request(amount: float, us: float, intl: float, bonds: float) -> RebalanceRequest:
    return RebalanceRequest(investment_amount=amount, target={US: us, INTL: intl, BONDS: bonds})


def breakdown3(us: float, intl: float, bonds: float, **kwargs: float) -> AllocationBreakdown:
    return make_breakdown({US: us, INTL: intl, BONDS: bonds}, **kwargs)


def by_category(result) -> dict:
    return {r.category: r for r in result.recommendations}


def test_buy_amounts_sum_to_investment():
    result = compute_rebalance(
        breakdown3(6000, 3000, 1000), make_request(5000, 60, 30, 10), make_config()
    )
    assert abs(result.total_buy_amount - 5000) < 0.02


def test_overweight_category_gets_zero():
    # US Stocks is 80% but target is 60% -- should get $0
    result = compute_rebalance(
        breakdown3(8000, 1000, 1000), make_request(1000, 60, 30, 10), make_config()
    )
    assert by_category(result)[US].buy_amount == 0.0


def test_buy_percent_sums_near_100():
    result = compute_rebalance(
        breakdown3(5000, 3000, 2000), make_request(2000, 50, 30, 20), make_config()
    )
    total_pct = sum(r.buy_percent_of_investment for r in result.recommendations)
    assert abs(total_pct - 100) < 0.01
    assert abs(result.total_buy_amount - 2000) < 0.02


def test_buy_symbols_come_from_config():
    result = compute_rebalance(
        breakdown3(5000, 3000, 2000), make_request(1000, 60, 30, 10), make_config()
    )
    assert {r.category: r.symbol for r in result.recommendations} == {
        US: "VTI",
        INTL: "VXUS",
        BONDS: "BND",
    }


def test_recommendations_follow_config_order():
    # Breakdown order differs from config order; output must use config order.
    bd = make_breakdown({BONDS: 1000, US: 6000, INTL: 3000})
    result = compute_rebalance(bd, make_request(1000, 60, 30, 10), make_config())
    assert [r.category for r in result.recommendations] == [US, INTL, BONDS]


def test_missing_target_category_is_treated_as_zero():
    req = RebalanceRequest(investment_amount=1000, target={US: 70, INTL: 30})
    result = compute_rebalance(breakdown3(1000, 1000, 1000), req, make_config())
    recs = by_category(result)
    assert recs[BONDS].buy_amount == 0.0
    assert recs[BONDS].target_percent == 0.0
    assert cents(result.total_buy_amount) == cents(1000)


def test_unassigned_value_does_not_affect_buys():
    plain = compute_rebalance(
        breakdown3(6000, 3000, 1000), make_request(5000, 60, 30, 10), make_config()
    )
    with_unassigned = compute_rebalance(
        breakdown3(6000, 3000, 1000, unassigned=4000), make_request(5000, 60, 30, 10), make_config()
    )
    assert [r.buy_amount for r in with_unassigned.recommendations] == [
        r.buy_amount for r in plain.recommendations
    ]


def test_four_categories_work():
    config = AllocationConfig(
        categories={
            US: CategoryConfig(buy_symbol="VTI", color=PALETTE[0]),
            INTL: CategoryConfig(buy_symbol="VXUS", color=PALETTE[1]),
            BONDS: CategoryConfig(buy_symbol="BND", color=PALETTE[2]),
            "Gold": CategoryConfig(buy_symbol="GLD", color=PALETTE[3]),
        },
        direct_mappings={},
        fractional_mappings={},
        exclusions=[],
    )
    bd = make_breakdown({US: 5000, INTL: 2000, BONDS: 2000, "Gold": 1000})
    req = RebalanceRequest(investment_amount=1000, target={US: 40, INTL: 20, BONDS: 20, "Gold": 20})
    result = compute_rebalance(bd, req, config)
    assert [r.category for r in result.recommendations] == [US, INTL, BONDS, "Gold"]
    assert cents(sum(r.buy_amount for r in result.recommendations)) == cents(1000)
    assert by_category(result)["Gold"].symbol == "GLD"


def test_unknown_target_category_is_rejected():
    req = RebalanceRequest(investment_amount=1000, target={US: 50, "Nope": 50})
    with pytest.raises(ConfigError, match="Nope"):
        compute_rebalance(breakdown3(1000, 1000, 1000), req, make_config())


def test_parent_category_is_not_a_target_and_buy_symbol_may_be_missing():
    config = AllocationConfig(
        categories={
            "Stocks": CategoryConfig(),
            US: CategoryConfig(buy_symbol="VTI", parent="Stocks"),
            BONDS: CategoryConfig(),
        },
    )
    bd = make_breakdown({US: 1000, BONDS: 1000})
    bad = RebalanceRequest(investment_amount=1000, target={"Stocks": 50, BONDS: 50})
    with pytest.raises(ConfigError, match="Stocks"):
        compute_rebalance(bd, bad, config)
    ok = RebalanceRequest(investment_amount=1000, target={US: 50, BONDS: 50})
    result = compute_rebalance(bd, ok, config)
    assert {r.category: r.symbol for r in result.recommendations} == {US: "VTI", BONDS: None}


def test_zero_portfolio_distributes_by_target():
    """If portfolio is empty (first investment), buy purely by target weights."""
    result = compute_rebalance(breakdown3(0, 0, 0), make_request(9000, 60, 30, 10), make_config())
    recs = by_category(result)
    assert abs(recs[US].buy_amount - 5400) < 0.02
    assert abs(recs[INTL].buy_amount - 2700) < 0.02
    assert abs(recs[BONDS].buy_amount - 900) < 0.02


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def api_body(target, amount: float = 100) -> dict:
    return {
        "investment_amount": amount,
        "target": target,
        "categories": [],
        "included_value": 0,
        "excluded_value": 0,
        "unassigned_value": 0,
        "total_value": 0,
    }


@pytest.mark.parametrize(
    "target",
    [
        {US: 50, INTL: 30, BONDS: 10},  # sums to 90
        {US: 60, INTL: 30, BONDS: 20},  # sums to 110
        {},  # sums to 0
        {US: 150, INTL: -50},  # out of range, sums to 100
        {US: -10, INTL: 110},
    ],
)
def test_target_must_be_in_range_and_sum_to_100(target):
    with pytest.raises(ValidationError):
        RebalanceRequest(investment_amount=100, target=target)
    with pytest.raises(ValidationError):
        RebalanceAPIRequest(**api_body(target))


def test_target_sum_tolerance():
    RebalanceRequest(investment_amount=100, target={US: 33.33, INTL: 33.33, BONDS: 33.34})
    RebalanceRequest(investment_amount=100, target={US: 50.005, INTL: 50})


@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan")])
def test_investment_amount_must_be_finite(amount):
    target = {US: 60, INTL: 30, BONDS: 10}
    with pytest.raises(ValidationError):
        RebalanceRequest(investment_amount=amount, target=target)
    with pytest.raises(ValidationError):
        RebalanceAPIRequest(**api_body(target, amount))


def test_target_values_must_be_finite():
    with pytest.raises(ValidationError):
        RebalanceRequest(investment_amount=100, target={US: float("nan"), INTL: 100})


def test_unassigned_value_is_required_in_api_request():
    body = api_body({US: 100})
    del body["unassigned_value"]
    with pytest.raises(ValidationError):
        RebalanceAPIRequest(**body)


def test_api_request_splits_into_request_and_breakdown():
    body = api_body({US: 60, INTL: 40}, amount=250)
    body["categories"] = [{"category": US, "current_value": 10, "percent_of_included": 100}]
    body.update(included_value=10, unassigned_value=5, total_value=15)
    api = RebalanceAPIRequest(**body)
    assert api.to_request().target == {US: 60, INTL: 40}
    breakdown = api.to_breakdown()
    assert breakdown.unassigned_value == 5
    assert [c.category for c in breakdown.categories] == [US]


# ---------------------------------------------------------------------------
# _largest_remainder_round
# ---------------------------------------------------------------------------


def cents(x: float) -> int:
    return round(x * 100)


def test_largest_remainder_round_sums_correctly():
    values = [333.333, 333.333, 333.334]
    rounded = _largest_remainder_round(values, 1000.0)
    assert abs(sum(rounded) - 1000.0) < 0.001
    assert all(isinstance(v, float) for v in rounded)


@pytest.mark.parametrize(
    ("values", "total", "expected"),
    [
        # Regression: per-value round() used to overshoot, giving a negative
        # cent diff that sliced from the end of the list and summed to 1.03.
        ([0.335, 0.335, 0.33], 1.0, [0.34, 0.33, 0.33]),
        # Already exact: nothing to redistribute.
        ([50.25, 30.25, 19.5], 100.0, [50.25, 30.25, 19.5]),
        ([333.333, 333.333, 333.334], 1000.0, [333.33, 333.33, 333.34]),
        # Equal remainders: lowest index wins, deterministically.
        ([1 / 3, 1 / 3, 1 / 3], 1.0, [0.34, 0.33, 0.33]),
        # Float noise must not shift a value across a cent boundary.
        ([0.1 + 0.2], 0.3, [0.3]),
        ([0.29, 0.57, 0.14], 1.0, [0.29, 0.57, 0.14]),
        # Zeros stay zero.
        ([0.0, 0.0, 0.0], 0.0, [0.0, 0.0, 0.0]),
        ([0.0, 0.0, 100.0], 100.0, [0.0, 0.0, 100.0]),
        # Large amounts keep cent precision.
        ([1e9 / 3] * 3, 1e9, [333333333.34, 333333333.33, 333333333.33]),
    ],
)
def test_largest_remainder_round_values(values, total, expected):
    assert _largest_remainder_round(values, total) == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize(
    ("values", "total"),
    [
        ([0.335, 0.335, 0.33], 1.0),
        ([1 / 3, 1 / 3, 1 / 3], 1.0),
        ([333.333, 333.333, 333.334], 1000.0),
        ([0.1 + 0.2, 0.7], 1.0),
        ([1e9 / 3] * 3, 1e9),
        ([12.345, 67.895, 19.76], 100.0),
        ([0.004, 0.004, 0.002], 0.01),
        # More categories than the old fixed three.
        ([1 / 8] * 8, 1.0),
    ],
)
def test_largest_remainder_round_always_sums_to_total(values, total):
    rounded = _largest_remainder_round(values, total)
    assert cents(sum(rounded)) == cents(total)
    assert all(v >= 0 for v in rounded)
    # Each value moves by less than a cent from its input.
    assert all(abs(r - v) < 0.01 + 1e-9 for r, v in zip(rounded, values, strict=True))


# ---------------------------------------------------------------------------
# compute_rebalance: exact sums and edge paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "holdings", "target"),
    [
        (1000.01, (3000, 3000, 3000), (33.33, 33.33, 33.34)),
        (333.33, (6000, 3000, 1000), (60, 30, 10)),
        (0.07, (123.45, 67.89, 10.11), (1, 1, 98)),
        (9999.99, (0, 0, 0), (34, 33, 33)),
        (100.0, (1234.56, 789.01, 4321.98), (50, 25, 25)),
        (1e9, (1e9 / 7, 2e9 / 7, 3e9 / 7), (45, 35, 20)),
    ],
)
def test_buy_amounts_sum_exactly_to_investment(amount, holdings, target):
    result = compute_rebalance(breakdown3(*holdings), make_request(amount, *target), make_config())
    buys = [r.buy_amount for r in result.recommendations]
    assert cents(sum(buys)) == cents(amount)
    assert all(b >= 0 for b in buys)
    assert result.total_buy_amount == pytest.approx(amount, abs=1e-9)


def test_inconsistent_breakdown_falls_back_to_target_weights():
    """
    The client supplies included_value and the category values independently.
    If included_value is smaller than the category sum, every raw buy is 0 and
    the investment is split by target weight instead.
    """
    bd = AllocationBreakdown(
        categories=[
            CategoryAllocation(category=US, current_value=5000, percent_of_included=50),
            CategoryAllocation(category=INTL, current_value=3000, percent_of_included=30),
            CategoryAllocation(category=BONDS, current_value=2000, percent_of_included=20),
        ],
        included_value=0,
        excluded_value=0,
        unassigned_value=0,
        total_value=0,
    )
    result = compute_rebalance(bd, make_request(1000, 60, 30, 10), make_config())
    buys = {r.category: r.buy_amount for r in result.recommendations}
    assert buys == pytest.approx({US: 600, INTL: 300, BONDS: 100})
