"""
Rebalance / buy-guidance engine.

Algorithm
---------
Given:
  - current allocation breakdown (per category; excluded and unassigned
    holdings are not part of it)
  - investment_amount  (new cash to deploy)
  - target weights     (per category, sum to 100; a category left out counts as 0)

Step 1: Compute new_total = included_value + investment_amount
Step 2: For each configured category (in config order):
          target_value  = new_total * (target_weight / 100)
          raw_buy       = max(0, target_value - current_value)
Step 3: Scale raw_buy amounts so they sum to investment_amount.
        (If a category is overweight no raw_buy is generated for it; the
         remaining categories absorb the full investment proportionally.
         If every raw_buy is 0 -- only possible when the supplied breakdown is
         internally inconsistent -- split the investment by target weights.)
Step 4: Round to whole cents with the largest-remainder method: floor each
        amount, then give the leftover cents to the largest fractional
        remainders (ties -> lowest index), so the buys sum to
        investment_amount to the cent.

The scaling in step 3 handles the edge case where one category is so
overweight that the others need more than the investment_amount in total —
we cap each recommendation at its pro-rata share of available cash rather
than allowing one category to receive more than 100% of investment.
"""

from __future__ import annotations

import math

from app.models.config import AllocationConfig
from app.models.schemas import (
    AllocationBreakdown,
    BuyRecommendation,
    RebalanceRequest,
    RebalanceResult,
)
from app.services.config_store import ConfigError

_CENT_EPS = 1e-6  # absorbs float noise, e.g. 0.29 * 100 == 28.999999999999996


def _largest_remainder_round(values: list[float], total: float) -> list[float]:
    """
    Round `values` to whole cents so they sum exactly to `total` (in cents).

    Works in integer cents: floor each value, then hand the leftover cents to
    the entries with the largest fractional remainder (lowest index wins ties).
    Flooring (not round()) guarantees the leftover is never negative.
    """
    cents = [math.floor(v * 100 + _CENT_EPS) for v in values]
    remainders = [v * 100 - c for v, c in zip(values, cents, strict=True)]
    leftover = round(total * 100) - sum(cents)
    if not 0 <= leftover <= len(values):
        raise ValueError("values do not sum to total within rounding tolerance")
    order = sorted(range(len(values)), key=lambda i: (-remainders[i], i))
    for i in order[:leftover]:
        cents[i] += 1
    return [c / 100 for c in cents]


def compute_rebalance(
    breakdown: AllocationBreakdown,
    request: RebalanceRequest,
    config: AllocationConfig,
) -> RebalanceResult:
    """
    Compute buy guidance for the configured categories given an investment
    amount and target allocation weights.

    Parameters
    ----------
    breakdown:
        Current allocation from compute_allocation().  Categories it lacks count
        as empty; ones the config no longer has are ignored.
    request:
        Investment amount and target weights.
    config:
        Config used for the category order and buy symbols.

    Returns
    -------
    RebalanceResult
        Per-category buy amounts and percentages, in config order.

    Raises
    ------
    ConfigError
        If the target names a category that is not in the config.
    """
    cats = config.category_names
    unknown = sorted(set(request.target) - set(cats))
    if unknown:
        raise ConfigError(f"Unknown categories in target: {unknown}. Defined: {cats}")

    inv = request.investment_amount
    target_map = {c: request.target.get(c, 0.0) for c in cats}

    current_map = {b.category: b.current_value for b in breakdown.categories}
    current_pct_map = {b.category: b.percent_of_included for b in breakdown.categories}
    included = breakdown.included_value
    new_total = included + inv

    # Step 1: raw (unscaled) buy amounts
    raw_buys: dict[str, float] = {}
    for category, target_pct in target_map.items():
        current_val = current_map.get(category, 0.0)
        target_val = new_total * (target_pct / 100)
        raw_buys[category] = max(0.0, target_val - current_val)

    raw_total = sum(raw_buys.values())

    # Step 2: scale so buy amounts sum to exactly investment_amount
    # raw_total == 0 only for inconsistent input (included_value vs categories are
    # client-supplied); fall back to target weights.
    if raw_total == 0:
        scaled = {c: inv * (target_map[c] / 100) for c in cats}
    else:
        scale = inv / raw_total
        scaled = {c: v * scale for c, v in raw_buys.items()}

    # Step 3: largest-remainder rounding so sum == investment_amount
    rounded_list = _largest_remainder_round([scaled[c] for c in cats], inv)
    rounded_buys = dict(zip(cats, rounded_list, strict=True))

    recommendations: list[BuyRecommendation] = []
    for category in cats:
        buy_amt = rounded_buys[category]
        buy_pct = (buy_amt / inv * 100) if inv > 0 else 0.0
        target_val = new_total * (target_map[category] / 100)
        recommendations.append(
            BuyRecommendation(
                category=category,
                symbol=config.buy_symbol_for(category),
                target_percent=round(target_map[category], 4),
                current_percent=round(current_pct_map.get(category, 0.0), 4),
                current_value=round(current_map.get(category, 0.0), 2),
                target_value=round(target_val, 2),
                buy_amount=buy_amt,
                buy_percent_of_investment=round(buy_pct, 4),
            )
        )

    return RebalanceResult(
        recommendations=recommendations,
        investment_amount=round(inv, 2),
        total_buy_amount=round(sum(r.buy_amount for r in recommendations), 2),
    )
