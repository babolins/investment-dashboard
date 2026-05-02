"""
Unit tests for the allocation grouping engine.
"""

import pytest

from app.models.config import AllocationConfig
from app.models.schemas import HoldingRow, PortfolioSnapshot
from app.services.allocation import compute_allocation


def make_snapshot(*holdings: tuple) -> PortfolioSnapshot:
    """Helper: create a snapshot from (symbol, value) tuples."""
    rows = [
        HoldingRow(
            symbol=sym,
            description="",
            quantity=1,
            last_price=val,
            current_value=val,
            cost_basis=None,
            total_gain_loss=None,
            percent_of_account=0,
        )
        for sym, val in holdings
    ]
    return PortfolioSnapshot(holdings=rows, total_value=sum(v for _, v in holdings), total_gain_loss=None)


def make_config(**kwargs) -> AllocationConfig:
    defaults = dict(
        direct_mappings={"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"},
        fractional_mappings={},
        exclusions=[],
        primary_symbols={"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"},
    )
    defaults.update(kwargs)
    return AllocationConfig(**defaults)


def test_direct_mapping_basic():
    snap = make_snapshot(("VTI", 6000), ("VXUS", 3000), ("BND", 1000))
    config = make_config()
    result = compute_allocation(snap, config)
    by_bucket = {b.bucket: b for b in result.buckets}
    assert abs(by_bucket["VTI"].percent_of_included - 60.0) < 0.01
    assert abs(by_bucket["VXUS"].percent_of_included - 30.0) < 0.01
    assert abs(by_bucket["BND"].percent_of_included - 10.0) < 0.01


def test_exclusion_removes_from_included():
    snap = make_snapshot(("VTI", 8000), ("SPAXX", 2000))
    config = make_config(exclusions=["SPAXX"])
    result = compute_allocation(snap, config)
    assert abs(result.included_value - 8000) < 0.01
    assert abs(result.excluded_value - 2000) < 0.01
    by_bucket = {b.bucket: b for b in result.buckets}
    assert abs(by_bucket["VTI"].percent_of_included - 100.0) < 0.01


def test_fractional_mapping():
    # XT: 60% VTI, 40% VXUS — value = 1000 => VTI+=600, VXUS+=400
    snap = make_snapshot(("XT", 1000), ("BND", 500))
    config = make_config(
        direct_mappings={"BND": "BND"},
        fractional_mappings={"XT": {"VTI": 0.6, "VXUS": 0.4}},
    )
    result = compute_allocation(snap, config)
    by_bucket = {b.bucket: b for b in result.buckets}
    assert abs(by_bucket["VTI"].current_value - 600) < 0.01
    assert abs(by_bucket["VXUS"].current_value - 400) < 0.01
    assert abs(by_bucket["BND"].current_value - 500) < 0.01


def test_included_value_sums_to_bucket_totals():
    snap = make_snapshot(("VTI", 5000), ("VXUS", 3000), ("BND", 2000))
    config = make_config()
    result = compute_allocation(snap, config)
    bucket_sum = sum(b.current_value for b in result.buckets)
    assert abs(bucket_sum - result.included_value) < 0.01


def test_all_excluded_gives_zero_included():
    snap = make_snapshot(("SPAXX", 5000))
    config = make_config(exclusions=["SPAXX"])
    result = compute_allocation(snap, config)
    assert result.included_value == 0.0
    assert result.excluded_value == 5000.0
