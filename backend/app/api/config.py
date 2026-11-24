"""
/api/config, /api/categories, /api/assignments: read and edit the category config.

Every edit returns the updated ConfigSummary.  Validation lives in the config store;
its errors become 404/409/422 in the app-level handlers (see app.main).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ConfigDep, StoreDep
from app.models.config import AllocationConfig
from app.models.schemas import (
    AssignmentUpdate,
    CategoryCreate,
    CategorySummary,
    CategoryUpdate,
    ConfigSummary,
)
from app.services.config_store import UNSET

router = APIRouter(tags=["config"])


def summarize(cfg: AllocationConfig) -> ConfigSummary:
    """The UI view of a config: categories in order, one weights dict per assigned symbol."""
    excluded = set(cfg.exclusions)
    assignments = {
        symbol: cfg.weights_for(symbol)
        for symbol in (*cfg.direct_mappings, *cfg.fractional_mappings)
        if symbol not in excluded  # an exclusion wins over a mapping
    }
    return ConfigSummary(
        categories=[
            CategorySummary(name=name, buy_symbol=c.buy_symbol, target=c.target, color=c.color)
            for name, c in cfg.categories.items()
        ],
        assignments=assignments,
        exclusions=cfg.exclusions,
    )


@router.get("/config", response_model=ConfigSummary)
def read_config(cfg: ConfigDep) -> ConfigSummary:
    """Return the active allocation configuration for display in the UI."""
    return summarize(cfg)


@router.post("/categories", response_model=ConfigSummary, status_code=201)
def create_category(body: CategoryCreate, store: StoreDep) -> ConfigSummary:
    return summarize(store.create_category(body.name, body.buy_symbol, body.target))


@router.patch("/categories/{name}", response_model=ConfigSummary)
def update_category(name: str, body: CategoryUpdate, store: StoreDep) -> ConfigSummary:
    # An explicit `target: null` clears the target; an omitted one leaves it alone.
    target = body.target if "target" in body.model_fields_set else UNSET
    return summarize(
        store.update_category(name, new_name=body.name, buy_symbol=body.buy_symbol, target=target)
    )


@router.delete("/categories/{name}", response_model=ConfigSummary)
def delete_category(name: str, store: StoreDep) -> ConfigSummary:
    return summarize(store.delete_category(name))


@router.put("/assignments/{symbol}", response_model=ConfigSummary)
def set_assignment(symbol: str, body: AssignmentUpdate, store: StoreDep) -> ConfigSummary:
    """Assign a symbol to categories (several = a split), exclude it, or clear it."""
    return summarize(store.set_assignment(symbol, weights=body.weights, excluded=body.excluded))
