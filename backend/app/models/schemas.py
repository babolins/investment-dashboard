"""
Pydantic schemas for API request/response contracts and internal domain types.
All monetary values are in USD. Percentages are expressed as 0-100 (not 0-1).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


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

ALLOWED_BUCKETS = {"VTI", "VXUS", "BND"}


class AllocationBucket(BaseModel):
    """One row in the grouped allocation breakdown."""

    bucket: str  # 'VTI' | 'VXUS' | 'BND'
    current_value: float
    percent_of_included: float  # 0-100, excludes excluded symbols


class AllocationBreakdown(BaseModel):
    """Result of grouping the portfolio into allocation buckets."""

    buckets: list[AllocationBucket]
    included_value: float  # Total portfolio value after exclusions
    excluded_value: float  # Value of excluded symbols (cash, money-market, etc.)
    total_value: float  # included + excluded


# ---------------------------------------------------------------------------
# Rebalance request / response
# ---------------------------------------------------------------------------


class TargetAllocation(BaseModel):
    """
    Target allocation weights for VTI, VXUS, BND.
    Weights are 0-100 (percent). Must sum to 100.
    """

    vti: float = Field(..., ge=0, le=100)
    vxus: float = Field(..., ge=0, le=100)
    bnd: float = Field(..., ge=0, le=100)

    @model_validator(mode="after")
    def weights_sum_to_100(self) -> "TargetAllocation":
        total = self.vti + self.vxus + self.bnd
        if abs(total - 100.0) > 0.01:
            raise ValueError(
                f"Target allocation weights must sum to 100, got {total:.2f}"
            )
        return self


class RebalanceRequest(BaseModel):
    investment_amount: float = Field(..., gt=0, description="Cash to invest in USD")
    target: TargetAllocation


class RebalanceAPIRequest(BaseModel):
    """Combined rebalance body — merges RebalanceRequest + AllocationBreakdown fields."""

    investment_amount: float = Field(..., gt=0)
    target: TargetAllocation
    buckets: list[AllocationBucket]
    included_value: float
    excluded_value: float
    total_value: float

    def to_request(self) -> RebalanceRequest:
        return RebalanceRequest(investment_amount=self.investment_amount, target=self.target)

    def to_breakdown(self) -> AllocationBreakdown:
        return AllocationBreakdown(
            buckets=self.buckets,
            included_value=self.included_value,
            excluded_value=self.excluded_value,
            total_value=self.total_value,
        )


class BuyRecommendation(BaseModel):
    """Buy guidance for a single ETF bucket."""

    bucket: str  # 'VTI' | 'VXUS' | 'BND'
    symbol: str  # Primary purchase symbol from config
    target_percent: float  # 0-100
    current_percent: float  # 0-100, of included portfolio
    current_value: float
    target_value: float
    buy_amount: float  # USD to invest (>= 0)
    buy_percent_of_investment: float  # 0-100


class RebalanceResult(BaseModel):
    recommendations: list[BuyRecommendation]
    investment_amount: float
    total_buy_amount: float  # Should equal investment_amount after rounding correction


# ---------------------------------------------------------------------------
# Config-related response types
# ---------------------------------------------------------------------------


class ConfigSummary(BaseModel):
    """Summarises the active YAML config for the UI."""

    direct_mappings: dict[str, str]  # symbol -> bucket
    fractional_mappings: dict[str, dict[str, float]]  # symbol -> {bucket: weight}
    exclusions: list[str]
    primary_symbols: dict[str, str]  # bucket -> purchase symbol
    default_target: TargetAllocation | None
