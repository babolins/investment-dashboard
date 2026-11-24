"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from app.models.config import AllocationConfig
from app.services import config_store
from app.services.config_store import ConfigStore


def get_store() -> ConfigStore:
    """The config store, after checking the config file exists and is valid.

    Every endpoint needs a usable config, and the store's edits would otherwise report a
    broken file as a 422; failing here gives all of them the same HTTP 500.  Tests override
    this function with a store on temporary files.
    """
    try:
        store = config_store.get_store()
        store.load()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Config error: {exc}") from exc
    return store


StoreDep = Annotated[ConfigStore, Depends(get_store)]


def get_config(store: StoreDep) -> AllocationConfig:
    """Load the active config (the store already vetted it, see ``get_store``)."""
    try:
        return store.load()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Config error: {exc}") from exc


ConfigDep = Annotated[AllocationConfig, Depends(get_config)]
