"""
Unit tests for the rebalance / buy-guidance engine.
"""

import pytest
from pydantic import ValidationError

from app.models.config import AllocationConfig
from app.models.schemas import (
    AllocationBreakdown,
    AllocationBucket,
    RebalanceAPIRequest,
    RebalanceRequest,
    TargetAllocation,
)
from app.services.rebalance import _largest_remainder_round, compute_rebalance


def make_breakdown(vti: float, vxus: float, bnd: float, excluded: float = 0) -> AllocationBreakdown:
    included = vti + vxus + bnd
    total = included + excluded

    def pct(v: float) -> float:
        return (v / included * 100) if included else 0.0

    return AllocationBreakdown(
        buckets=[
            AllocationBucket(bucket="VTI", current_value=vti, percent_of_included=pct(vti)),
            AllocationBucket(bucket="VXUS", current_value=vxus, percent_of_included=pct(vxus)),
            AllocationBucket(bucket="BND", current_value=bnd, percent_of_included=pct(bnd)),
        ],
        included_value=included,
        excluded_value=excluded,
        total_value=total,
    )


def make_config() -> AllocationConfig:
    return AllocationConfig(
        direct_mappings={"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"},
        fractional_mappings={},
        exclusions=[],
        primary_symbols={"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"},
    )


def make_request(amount: float, vti: float, vxus: float, bnd: float) -> RebalanceRequest:
    return RebalanceRequest(
        investment_amount=amount,
        target=TargetAllocation(vti=vti, vxus=vxus, bnd=bnd),
    )


def test_buy_amounts_sum_to_investment():
    bd = make_breakdown(6000, 3000, 1000)
    req = make_request(5000, 60, 30, 10)
    result = compute_rebalance(bd, req, make_config())
    assert abs(result.total_buy_amount - 5000) < 0.02


def test_overweight_bucket_gets_zero():
    # VTI is 80% but target is 60% — should get $0
    bd = make_breakdown(8000, 1000, 1000)
    req = make_request(1000, 60, 30, 10)
    result = compute_rebalance(bd, req, make_config())
    vti_rec = next(r for r in result.recommendations if r.bucket == "VTI")
    assert vti_rec.buy_amount == 0.0


def test_buy_percent_sums_near_100():
    bd = make_breakdown(5000, 3000, 2000)
    req = make_request(2000, 50, 30, 20)
    result = compute_rebalance(bd, req, make_config())
    total_pct = sum(r.buy_percent_of_investment for r in result.recommendations)
    assert abs(total_pct - 100) < 0.01
    assert abs(result.total_buy_amount - 2000) < 0.02


def test_primary_symbols_set():
    bd = make_breakdown(5000, 3000, 2000)
    req = make_request(1000, 60, 30, 10)
    result = compute_rebalance(bd, req, make_config())
    for rec in result.recommendations:
        assert rec.symbol == rec.bucket  # default config: VTI->VTI, etc.


def test_largest_remainder_round_sums_correctly():
    values = [333.333, 333.333, 333.334]
    rounded = _largest_remainder_round(values, 1000.0)
    assert abs(sum(rounded) - 1000.0) < 0.001
    assert all(isinstance(v, float) for v in rounded)


def test_target_allocation_must_sum_to_100():
    with pytest.raises(ValueError):
        TargetAllocation(vti=50, vxus=30, bnd=10)  # sums to 90


def test_zero_portfolio_distributes_by_target():
    """If portfolio is empty (first investment), buy purely by target weights."""
    bd = make_breakdown(0, 0, 0)
    req = make_request(9000, 60, 30, 10)
    result = compute_rebalance(bd, req, make_config())
    vti = next(r for r in result.recommendations if r.bucket == "VTI")
    vxus = next(r for r in result.recommendations if r.bucket == "VXUS")
    bnd = next(r for r in result.recommendations if r.bucket == "BND")
    assert abs(vti.buy_amount - 5400) < 0.02
    assert abs(vxus.buy_amount - 2700) < 0.02
    assert abs(bnd.buy_amount - 900) < 0.02


# ---------------------------------------------------------------------------
# _largest_remainder_round
# ---------------------------------------------------------------------------


def cents(x: float) -> int:
    return round(x * 100)


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
    result = compute_rebalance(
        make_breakdown(*holdings), make_request(amount, *target), make_config()
    )
    buys = [r.buy_amount for r in result.recommendations]
    assert cents(sum(buys)) == cents(amount)
    assert all(b >= 0 for b in buys)
    assert result.total_buy_amount == pytest.approx(amount, abs=1e-9)


def test_inconsistent_breakdown_falls_back_to_target_weights():
    """
    The client supplies included_value and the bucket values independently.
    If included_value is smaller than the bucket sum, every raw buy is 0 and
    the investment is split by target weight instead.
    """
    bd = AllocationBreakdown(
        buckets=[
            AllocationBucket(bucket="VTI", current_value=5000, percent_of_included=50),
            AllocationBucket(bucket="VXUS", current_value=3000, percent_of_included=30),
            AllocationBucket(bucket="BND", current_value=2000, percent_of_included=20),
        ],
        included_value=0,
        excluded_value=0,
        total_value=0,
    )
    result = compute_rebalance(bd, make_request(1000, 60, 30, 10), make_config())
    buys = {r.bucket: r.buy_amount for r in result.recommendations}
    assert buys == pytest.approx({"VTI": 600, "VXUS": 300, "BND": 100})


@pytest.mark.parametrize("amount", [float("inf"), float("-inf"), float("nan")])
def test_investment_amount_must_be_finite(amount):
    target = TargetAllocation(vti=60, vxus=30, bnd=10)
    with pytest.raises(ValidationError):
        RebalanceRequest(investment_amount=amount, target=target)
    with pytest.raises(ValidationError):
        RebalanceAPIRequest(
            investment_amount=amount,
            target=target,
            buckets=[],
            included_value=0,
            excluded_value=0,
            total_value=0,
        )
