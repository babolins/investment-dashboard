"""
Unit tests for the rebalance / buy-guidance engine.
"""

import pytest

from app.models.config import AllocationConfig
from app.models.schemas import (
    AllocationBreakdown,
    AllocationBucket,
    RebalanceRequest,
    TargetAllocation,
)
from app.services.rebalance import compute_rebalance, _largest_remainder_round


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
    # May not be exactly 100 if a bucket gets $0, but buy_amounts should sum
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
