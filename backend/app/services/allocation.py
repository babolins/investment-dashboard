"""
Allocation grouping engine.

Takes a parsed PortfolioSnapshot and an AllocationConfig and produces
an AllocationBreakdown that groups holdings into the user-defined categories
(in config order; categories with no holdings are included with value 0).

Fractional mappings split a single holding's value across multiple categories
proportionally to the configured weights.

Excluded symbols (e.g. SPAXX, FDRXX) are tallied separately and do not
contribute to the category percentages shown in the chart.

Symbols with no mapping that are not excluded are tallied as unassigned (and
logged as a warning) rather than crashing; they are also left out of the
category percentages.
"""

from __future__ import annotations

import logging

from app.models.config import AllocationConfig
from app.models.schemas import AllocationBreakdown, CategoryAllocation, PortfolioSnapshot

logger = logging.getLogger(__name__)


def compute_allocation(
    snapshot: PortfolioSnapshot,
    config: AllocationConfig,
) -> AllocationBreakdown:
    """
    Group portfolio holdings into the configured allocation categories.

    Parameters
    ----------
    snapshot:
        Parsed portfolio from the CSV upload.
    config:
        Validated YAML config with categories, mappings and exclusions.

    Returns
    -------
    AllocationBreakdown
        Per-category values and percentages, plus excluded/unassigned/total summaries.
    """
    category_values = dict.fromkeys(config.category_names, 0.0)
    excluded_value = 0.0
    unassigned_value = 0.0
    unassigned: list[str] = []

    for holding in snapshot.holdings:
        sym = holding.symbol.upper()

        if config.is_excluded(sym):
            excluded_value += holding.current_value
            continue

        weights = config.weights_for(sym)
        if not weights:
            unassigned_value += holding.current_value
            unassigned.append(sym)
            continue

        for category, weight in weights.items():
            category_values[category] += holding.current_value * weight

    if unassigned:
        logger.warning(
            "The following symbols have no category in config.yaml and are counted as "
            "unassigned: %s. Assign them to a category or exclude them.",
            sorted(set(unassigned)),
        )

    included_value = sum(category_values.values())
    total_value = included_value + excluded_value + unassigned_value

    categories = [
        CategoryAllocation(
            category=category,
            current_value=round(value, 2),
            percent_of_included=round(
                value / included_value * 100 if included_value > 0 else 0.0, 4
            ),
        )
        for category, value in category_values.items()
    ]

    return AllocationBreakdown(
        categories=categories,
        included_value=round(included_value, 2),
        excluded_value=round(excluded_value, 2),
        unassigned_value=round(unassigned_value, 2),
        total_value=round(total_value, 2),
    )
