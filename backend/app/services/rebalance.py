"""
Rebalance / buy-guidance engine.

Algorithm
---------
Given:
  - current allocation breakdown (per bucket, post-exclusion)
  - investment_amount  (new cash to deploy)
  - target weights     (VTI / VXUS / BND, sum to 100)

Step 1: Compute new_total = included_value + investment_amount
Step 2: For each bucket:
          target_value  = new_total * (target_weight / 100)
          raw_buy       = max(0, target_value - current_value)
Step 3: Scale raw_buy amounts so they sum to investment_amount.
        (If a bucket is overweight no raw_buy is generated for it; the
         remaining buckets absorb the full investment proportionally.
         If every raw_buy is 0 -- only possible when the supplied breakdown is
         internally inconsistent -- split the investment by target weights.)
Step 4: Round to whole cents with the largest-remainder method: floor each
        amount, then give the leftover cents to the largest fractional
        remainders (ties -> lowest index), so the buys sum to
        investment_amount to the cent.

The scaling in step 3 handles the edge case where one bucket is so
overweight that the others need more than the investment_amount in total —
we cap each recommendation at its pro-rata share of available cash rather
than allowing one bucket to receive more than 100% of investment.
"""

from __future__ import annotations

import math

from app.models.config import AllocationConfig
from app.models.schemas import (
    BUCKETS,
    AllocationBreakdown,
    Bucket,
    BuyRecommendation,
    RebalanceRequest,
    RebalanceResult,
)

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
    Compute buy guidance for VTI / VXUS / BND given an investment amount
    and target allocation weights.

    Parameters
    ----------
    breakdown:
        Current allocation from compute_allocation().
    request:
        Investment amount and target weights.
    config:
        Config used to look up primary purchase symbols.

    Returns
    -------
    RebalanceResult
        Per-bucket buy amounts and percentages.
    """
    inv = request.investment_amount
    target_map: dict[Bucket, float] = {
        "VTI": request.target.vti,
        "VXUS": request.target.vxus,
        "BND": request.target.bnd,
    }

    current_map = {b.bucket: b.current_value for b in breakdown.buckets}
    current_pct_map = {b.bucket: b.percent_of_included for b in breakdown.buckets}
    included = breakdown.included_value
    new_total = included + inv

    # Step 1: raw (unscaled) buy amounts
    raw_buys: dict[Bucket, float] = {}
    for bucket, target_pct in target_map.items():
        current_val = current_map.get(bucket, 0.0)
        target_val = new_total * (target_pct / 100)
        raw_buys[bucket] = max(0.0, target_val - current_val)

    raw_total = sum(raw_buys.values())

    # Step 2: scale so buy amounts sum to exactly investment_amount
    # raw_total == 0 only for inconsistent input (included_value vs buckets are
    # client-supplied); fall back to target weights.
    if raw_total == 0:
        scaled = {b: inv * (target_map[b] / 100) for b in BUCKETS}
    else:
        scale = inv / raw_total
        scaled = {b: v * scale for b, v in raw_buys.items()}

    # Step 3: largest-remainder rounding so sum == investment_amount
    raw_list = [scaled[b] for b in BUCKETS]
    rounded_list = _largest_remainder_round(raw_list, inv)
    rounded_buys = dict(zip(BUCKETS, rounded_list, strict=True))

    recommendations: list[BuyRecommendation] = []
    for bucket in BUCKETS:
        buy_amt = rounded_buys[bucket]
        buy_pct = (buy_amt / inv * 100) if inv > 0 else 0.0
        target_val = new_total * (target_map[bucket] / 100)
        recommendations.append(
            BuyRecommendation(
                bucket=bucket,
                symbol=config.primary_symbol_for(bucket),
                target_percent=round(target_map[bucket], 4),
                current_percent=round(current_pct_map.get(bucket, 0.0), 4),
                current_value=round(current_map.get(bucket, 0.0), 2),
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
