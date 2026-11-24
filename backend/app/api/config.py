"""
/api/config — expose current config summary and default target allocations to the UI.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ConfigDep
from app.models.schemas import ConfigSummary

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigSummary)
def read_config(cfg: ConfigDep) -> ConfigSummary:
    """Return the active allocation configuration for display in the UI."""
    return ConfigSummary(
        direct_mappings=cfg.direct_mappings,
        fractional_mappings=cfg.fractional_mappings,
        exclusions=cfg.exclusions,
        primary_symbols=cfg.primary_symbols,
        default_target=cfg.default_target_allocations,
    )
