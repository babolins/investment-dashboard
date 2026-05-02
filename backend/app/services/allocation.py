"""
Allocation grouping engine.

Takes a parsed PortfolioSnapshot and an AllocationConfig and produces
an AllocationBreakdown that groups holdings into VTI / VXUS / BND buckets.

Fractional mappings split a single holding's value across multiple buckets
proportionally to the configured weights.

Excluded symbols (e.g. SPAXX, FDRXX) are tallied separately and do not
contribute to the bucket percentages shown in the chart.

Unknown symbols (not in any mapping and not excluded) are logged as warnings
but are ignored in the allocation breakdown rather than crashing.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.models.config import AllocationConfig
from app.models.schemas import (
    ALLOWED_BUCKETS,
    AllocationBreakdown,
    AllocationBucket,
    PortfolioSnapshot,
)

logger = logging.getLogger(__name__)


def compute_allocation(
    snapshot: PortfolioSnapshot,
    config: AllocationConfig,
) -> AllocationBreakdown:
    """
    Group portfolio holdings into VTI / VXUS / BND allocation buckets.

    Parameters
    ----------
    snapshot:
        Parsed portfolio from the CSV upload.
    config:
        Validated YAML config with direct/fractional/exclusion rules.

    Returns
    -------
    AllocationBreakdown
        Per-bucket values and percentages, plus excluded/total summaries.
    """
    bucket_values: dict[str, float] = defaultdict(float)
    excluded_value = 0.0
    unrecognised: list[str] = []

    for holding in snapshot.holdings:
        sym = holding.symbol.upper()

        if config.is_excluded(sym):
            excluded_value += holding.current_value
            continue

        weights = config.bucket_weights_for(sym)
        if not weights:
            unrecognised.append(sym)
            continue

        for bucket, weight in weights.items():
            bucket_values[bucket] += holding.current_value * weight

    if unrecognised:
        logger.warning(
            "The following symbols have no mapping in config.yaml and were "
            "excluded from the allocation breakdown: %s. "
            "Add them to direct_mappings, fractional_mappings, or exclusions.",
            sorted(set(unrecognised)),
        )

    included_value = sum(bucket_values.values())
    total_value = included_value + excluded_value

    buckets: list[AllocationBucket] = []
    for bucket in sorted(ALLOWED_BUCKETS):  # deterministic order
        value = bucket_values.get(bucket, 0.0)
        pct = (value / included_value * 100) if included_value > 0 else 0.0
        buckets.append(
            AllocationBucket(
                bucket=bucket,
                current_value=round(value, 2),
                percent_of_included=round(pct, 4),
            )
        )

    return AllocationBreakdown(
        buckets=buckets,
        included_value=round(included_value, 2),
        excluded_value=round(excluded_value, 2),
        total_value=round(total_value, 2),
    )
