"""
Pydantic schemas for API request/response contracts and internal domain types.
Categories are user-defined (see app.models.config), so they are plain strings here.
All monetary values are in USD. Percentages are expressed as 0-100 (not 0-1).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Portfolio / Holdings
# ---------------------------------------------------------------------------


class HoldingRow(BaseModel):
    """One security row from the parsed Fidelity CSV."""

    symbol: str
    description: str = ""
    quantity: float
    last_price: float
    current_value: float
    cost_basis: float | None  # None when Fidelity reports "n/a"
    total_gain_loss: float | None  # None when cost_basis is unavailable
    percent_of_account: float  # 0-100


class PortfolioSnapshot(BaseModel):
    """Full parsed portfolio ready for the UI table."""

    holdings: list[HoldingRow]
    total_value: float
    total_gain_loss: float | None
    snapshot_date: str | None = None  # ISO date string if present in CSV


# ---------------------------------------------------------------------------
# Allocation grouping
# ---------------------------------------------------------------------------


class CategoryAllocation(BaseModel):
    """One row in the grouped allocation breakdown."""

    category: str
    current_value: float
    percent_of_included: float  # 0-100, excludes excluded and unassigned symbols


class AllocationBreakdown(BaseModel):
    """Result of grouping the portfolio into the configured categories."""

    categories: list[
        CategoryAllocation
    ]  # leaf categories in config order, zero-value ones included
    included_value: float  # Value assigned to categories
    excluded_value: float  # Value of excluded symbols (cash, money-market, etc.)
    unassigned_value: float  # Value of symbols with no category and no exclusion
    total_value: float  # included + excluded + unassigned


class UploadResponse(BaseModel):
    """/api/upload payload: parsed holdings plus allocation breakdown."""

    portfolio: PortfolioSnapshot
    allocation: AllocationBreakdown


# ---------------------------------------------------------------------------
# Rebalance request / response
# ---------------------------------------------------------------------------


def _sum_to_100(target: Mapping[str, float]) -> Mapping[str, float]:
    total = sum(target.values())
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"Target allocation weights must sum to 100, got {total:.2f}")
    return target


# leaf category -> percent (0-100); one left out counts as 0.  Whether the names are leaves
# needs the config, so that check lives in the rebalance service.
Targets = Annotated[
    Mapping[str, Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]],  # Mapping: covariant
    AfterValidator(_sum_to_100),
]


class RebalanceRequest(BaseModel):
    investment_amount: float = Field(
        ..., gt=0, allow_inf_nan=False, description="Cash to invest in USD"
    )
    target: Targets


class RebalanceAPIRequest(BaseModel):
    """Combined rebalance body: RebalanceRequest + AllocationBreakdown fields."""

    investment_amount: float = Field(..., gt=0, allow_inf_nan=False)
    target: Targets
    categories: list[CategoryAllocation]
    included_value: float
    excluded_value: float
    unassigned_value: float
    total_value: float

    def to_request(self) -> RebalanceRequest:
        return RebalanceRequest(investment_amount=self.investment_amount, target=self.target)

    def to_breakdown(self) -> AllocationBreakdown:
        return AllocationBreakdown(
            categories=self.categories,
            included_value=self.included_value,
            excluded_value=self.excluded_value,
            unassigned_value=self.unassigned_value,
            total_value=self.total_value,
        )


class BuyRecommendation(BaseModel):
    """Buy guidance for a single leaf category."""

    category: str
    symbol: str | None  # The category's buy_symbol from config, if it has one
    target_percent: float  # 0-100
    current_percent: float  # 0-100, of included portfolio
    current_value: float
    target_value: float
    buy_amount: float  # USD to invest (>= 0)
    buy_percent_of_investment: float  # 0-100


class RebalanceResult(BaseModel):
    recommendations: list[BuyRecommendation]  # config category order
    investment_amount: float
    total_buy_amount: float  # Should equal investment_amount after rounding correction


# ---------------------------------------------------------------------------
# Config response and edit requests
# ---------------------------------------------------------------------------


class CategorySummary(BaseModel):
    name: str
    parent: str | None  # another category's name; None = top level
    target: float | None  # default % of the parent (of the portfolio at the top level)
    buy_symbol: str | None
    color: str | None  # set for leaves only


class ConfigSummary(BaseModel):
    """The active config as the UI needs it."""

    categories: list[CategorySummary]  # display order (parents and leaves)
    assignments: dict[str, dict[str, float]]  # symbol -> {category: weight 0-1}
    exclusions: list[str]


# Name and buy_symbol format rules live in AllocationConfig (one source of truth); a
# violation surfaces as a ConfigError (422).  Only types and the target range are checked here.
_Target = Annotated[float | None, Field(ge=0, le=100, allow_inf_nan=False)]


class CategoryCreate(BaseModel):
    name: str
    buy_symbol: str | None = None
    target: _Target = None
    parent: str | None = None  # category to create it in; omitted/null = top level


class CategoryUpdate(BaseModel):
    """Partial update: omitted fields stay; ``target: null`` clears the default target,
    ``buy_symbol: null`` clears the buy symbol and ``parent: null`` moves the category to
    the top level (``name: null`` is "omitted")."""

    name: str | None = None
    buy_symbol: str | None = None
    target: _Target = None
    parent: str | None = None


class AssignmentUpdate(BaseModel):
    """Where a symbol belongs: weights (one or more categories), excluded, or neither."""

    weights: dict[str, Annotated[float, Field(gt=0, allow_inf_nan=False)]] | None = None
    excluded: bool = False

    @model_validator(mode="after")
    def _not_both(self) -> AssignmentUpdate:
        if self.excluded and self.weights:
            raise ValueError("A symbol cannot be both excluded and assigned to categories")
        return self
