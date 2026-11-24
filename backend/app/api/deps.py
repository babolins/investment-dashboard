"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from app.models.config import AllocationConfig, load_config


def get_config() -> AllocationConfig:
    """Load the active config, turning load failures into a uniform HTTP 500."""
    try:
        return load_config()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Config error: {exc}") from exc


ConfigDep = Annotated[AllocationConfig, Depends(get_config)]
