"""
Unit tests for the allocation grouping engine.
"""

from typing import Any

import pytest

from app.models.config import PALETTE, AllocationConfig, CategoryConfig
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
    return PortfolioSnapshot(
        holdings=rows, total_value=sum(v for _, v in holdings), total_gain_loss=None
    )


def make_config(**kwargs) -> AllocationConfig:
    defaults: dict[str, Any] = dict(
        categories={
            "US Stocks": CategoryConfig(buy_symbol="VTI", target=60, color=PALETTE[0]),
            "International": CategoryConfig(buy_symbol="VXUS", target=30, color=PALETTE[1]),
            "Bonds": CategoryConfig(buy_symbol="BND", target=10, color=PALETTE[2]),
        },
        direct_mappings={"VTI": "US Stocks", "VXUS": "International", "BND": "Bonds"},
        fractional_mappings={},
        exclusions=[],
    )
    defaults.update(kwargs)
    return AllocationConfig(**defaults)


def test_direct_mapping_basic():
    snap = make_snapshot(("VTI", 6000), ("VXUS", 3000), ("BND", 1000))
    result = compute_allocation(snap, make_config())
    by_cat = {c.category: c for c in result.categories}
    assert abs(by_cat["US Stocks"].percent_of_included - 60.0) < 0.01
    assert abs(by_cat["International"].percent_of_included - 30.0) < 0.01
    assert abs(by_cat["Bonds"].percent_of_included - 10.0) < 0.01
    assert result.unassigned_value == 0.0


def test_categories_follow_config_order_and_include_zero_value():
    # Config order, not alphabetical; a category with no holdings still appears.
    snap = make_snapshot(("VTI", 1000))
    result = compute_allocation(snap, make_config())
    assert [c.category for c in result.categories] == ["US Stocks", "International", "Bonds"]
    by_cat = {c.category: c for c in result.categories}
    assert by_cat["Bonds"].current_value == 0.0
    assert by_cat["Bonds"].percent_of_included == 0.0


def test_breakdown_lists_only_leaf_categories():
    config = make_config(
        categories={
            "Stocks": CategoryConfig(),
            "US Stocks": CategoryConfig(buy_symbol="VTI", parent="Stocks"),
            "Bonds": CategoryConfig(buy_symbol="BND"),
        },
        direct_mappings={"VTI": "US Stocks"},
    )
    result = compute_allocation(make_snapshot(("VTI", 1000)), config)
    assert [c.category for c in result.categories] == ["US Stocks", "Bonds"]


def test_exclusion_removes_from_included():
    snap = make_snapshot(("VTI", 8000), ("SPAXX", 2000))
    result = compute_allocation(snap, make_config(exclusions=["SPAXX"]))
    assert abs(result.included_value - 8000) < 0.01
    assert abs(result.excluded_value - 2000) < 0.01
    by_cat = {c.category: c for c in result.categories}
    assert abs(by_cat["US Stocks"].percent_of_included - 100.0) < 0.01


def test_fractional_mapping():
    # XT: 60% US Stocks, 40% International; value 1000 => 600 / 400
    snap = make_snapshot(("XT", 1000), ("BND", 500))
    config = make_config(
        direct_mappings={"BND": "Bonds"},
        fractional_mappings={"XT": {"US Stocks": 0.6, "International": 0.4}},
    )
    result = compute_allocation(snap, config)
    by_cat = {c.category: c for c in result.categories}
    assert abs(by_cat["US Stocks"].current_value - 600) < 0.01
    assert abs(by_cat["International"].current_value - 400) < 0.01
    assert abs(by_cat["Bonds"].current_value - 500) < 0.01


def test_included_value_sums_to_category_totals():
    snap = make_snapshot(("VTI", 5000), ("VXUS", 3000), ("BND", 2000))
    result = compute_allocation(snap, make_config())
    category_sum = sum(c.current_value for c in result.categories)
    assert abs(category_sum - result.included_value) < 0.01


def test_all_excluded_gives_zero_included():
    snap = make_snapshot(("SPAXX", 5000))
    result = compute_allocation(snap, make_config(exclusions=["SPAXX"]))
    assert result.included_value == 0.0
    assert result.excluded_value == 5000.0
    assert all(c.percent_of_included == 0.0 for c in result.categories)


def test_unassigned_holdings_are_tracked_separately():
    snap = make_snapshot(("VTI", 6000), ("BND", 1000), ("AAPL", 3000), ("SPAXX", 500))
    result = compute_allocation(snap, make_config(exclusions=["SPAXX"]))
    assert result.unassigned_value == pytest.approx(3000)
    # Unassigned value is not part of the included base the percentages use.
    assert result.included_value == pytest.approx(7000)
    assert result.excluded_value == pytest.approx(500)
    assert result.total_value == pytest.approx(10500)
    by_cat = {c.category: c for c in result.categories}
    assert by_cat["US Stocks"].percent_of_included == pytest.approx(6000 / 7000 * 100, abs=1e-3)


def test_total_is_included_plus_excluded_plus_unassigned():
    snap = make_snapshot(("VTI", 100.55), ("XT", 33.33), ("AAPL", 7.77), ("SPAXX", 1.11))
    config = make_config(
        direct_mappings={"VTI": "US Stocks"},
        fractional_mappings={"XT": {"US Stocks": 0.5, "Bonds": 0.5}},
        exclusions=["SPAXX"],
    )
    result = compute_allocation(snap, config)
    parts = result.included_value + result.excluded_value + result.unassigned_value
    assert result.total_value == pytest.approx(parts, abs=0.01)
    assert result.total_value == pytest.approx(snap.total_value, abs=0.01)


def test_config_with_no_categories_leaves_everything_unassigned():
    snap = make_snapshot(("VTI", 1000))
    result = compute_allocation(snap, make_config(categories={}, direct_mappings={}))
    assert result.categories == []
    assert result.included_value == 0.0
    assert result.unassigned_value == 1000.0


def test_custom_category_names_are_used_verbatim():
    config = make_config(
        categories={"Real Estate": CategoryConfig(buy_symbol="VNQ", color=PALETTE[0])},
        direct_mappings={"VNQ": "Real Estate"},
    )
    result = compute_allocation(make_snapshot(("VNQ", 250)), config)
    assert [(c.category, c.current_value) for c in result.categories] == [("Real Estate", 250)]
