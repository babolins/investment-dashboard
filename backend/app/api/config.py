"""
/api/config — expose current config summary and default target allocations to the UI.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.config import load_config
from app.models.schemas import ConfigSummary

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigSummary)
def get_config() -> ConfigSummary:
    """Return the active allocation configuration for display in the UI."""
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ConfigSummary(
        direct_mappings=cfg.direct_mappings,
        fractional_mappings=cfg.fractional_mappings,
        exclusions=cfg.exclusions,
        primary_symbols=cfg.primary_symbols,
        default_target=cfg.default_target_allocations,
    )
