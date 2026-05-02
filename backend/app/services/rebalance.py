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
Step 3: Scale raw_buy amounts so they sum exactly to investment_amount.
        (If a bucket is overweight no raw_buy is generated for it; the
         remaining buckets absorb the full investment proportionally.)
Step 4: Apply largest-remainder rounding so displayed cent values sum
        exactly to investment_amount.

The scaling in step 3 handles the edge case where one bucket is so
overweight that the others need more than the investment_amount in total —
we cap each recommendation at its pro-rata share of available cash rather
than allowing one bucket to receive more than 100% of investment.
"""

from __future__ import annotations

from app.models.config import AllocationConfig
from app.models.schemas import (
    AllocationBreakdown,
    BuyRecommendation,
    RebalanceRequest,
    RebalanceResult,
)


def _largest_remainder_round(values: list[float], total: float) -> list[float]:
    """
    Round a list of floats to 2 decimal places such that they sum to `total`
    (also rounded to 2 dp).
    """
    floored = [round(v, 2) for v in values]
    remainders = [(v - f, i) for i, (v, f) in enumerate(zip(values, floored))]
    diff_cents = round((total - sum(floored)) * 100)
    # Add 1 cent to the entries with largest fractional remainder
    for _, i in sorted(remainders, reverse=True)[: int(diff_cents)]:
        floored[i] = round(floored[i] + 0.01, 2)
    return floored


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
    target_map = {
        "VTI": request.target.vti,
        "VXUS": request.target.vxus,
        "BND": request.target.bnd,
    }

    current_map = {b.bucket: b.current_value for b in breakdown.buckets}
    current_pct_map = {b.bucket: b.percent_of_included for b in breakdown.buckets}
    included = breakdown.included_value
    new_total = included + inv

    # Step 1: raw (unscaled) buy amounts
    raw_buys: dict[str, float] = {}
    for bucket, target_pct in target_map.items():
        current_val = current_map.get(bucket, 0.0)
        target_val = new_total * (target_pct / 100)
        raw_buys[bucket] = max(0.0, target_val - current_val)

    raw_total = sum(raw_buys.values())

    # Step 2: scale so buy amounts sum to exactly investment_amount
    # If raw_total == 0 (everything perfectly balanced), distribute evenly.
    if raw_total == 0:
        buckets_ordered = ["VTI", "VXUS", "BND"]
        scaled = {b: inv * (target_map[b] / 100) for b in buckets_ordered}
    else:
        scale = inv / raw_total
        scaled = {b: v * scale for b, v in raw_buys.items()}

    # Step 3: largest-remainder rounding so sum == investment_amount
    buckets_ordered = ["VTI", "VXUS", "BND"]
    raw_list = [scaled[b] for b in buckets_ordered]
    rounded_list = _largest_remainder_round(raw_list, inv)
    rounded_buys = dict(zip(buckets_ordered, rounded_list))

    recommendations: list[BuyRecommendation] = []
    for bucket in buckets_ordered:
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
