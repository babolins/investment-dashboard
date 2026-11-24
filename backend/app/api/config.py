"""
/api/config, /api/categories, /api/groups, /api/assignments: read and edit the category config.

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
    GroupCreate,
    GroupSummary,
    GroupUpdate,
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
        groups=[
            GroupSummary(name=name, parent=g.parent, target=g.target)
            for name, g in cfg.groups.items()
        ],
        categories=[
            CategorySummary(
                name=name, buy_symbol=c.buy_symbol, parent=c.parent, target=c.target, color=c.color
            )
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
    return summarize(store.create_category(body.name, body.buy_symbol, body.target, body.parent))


@router.patch("/categories/{name}", response_model=ConfigSummary)
def update_category(name: str, body: CategoryUpdate, store: StoreDep) -> ConfigSummary:
    # An explicit `target: null` clears the target (`parent: null` = top level); omitted = keep.
    sent = body.model_fields_set
    return summarize(
        store.update_category(
            name,
            new_name=body.name,
            buy_symbol=body.buy_symbol,
            target=body.target if "target" in sent else UNSET,
            parent=body.parent if "parent" in sent else UNSET,
        )
    )


@router.delete("/categories/{name}", response_model=ConfigSummary)
def delete_category(name: str, store: StoreDep) -> ConfigSummary:
    return summarize(store.delete_category(name))


@router.post("/groups", response_model=ConfigSummary, status_code=201)
def create_group(body: GroupCreate, store: StoreDep) -> ConfigSummary:
    return summarize(store.create_group(body.name, body.parent, body.target))


@router.patch("/groups/{name}", response_model=ConfigSummary)
def update_group(name: str, body: GroupUpdate, store: StoreDep) -> ConfigSummary:
    # Explicit nulls clear `target` / move to the top level; omitted fields are left alone.
    sent = body.model_fields_set
    return summarize(
        store.update_group(
            name,
            new_name=body.name,
            parent=body.parent if "parent" in sent else UNSET,
            target=body.target if "target" in sent else UNSET,
        )
    )


@router.delete("/groups/{name}", response_model=ConfigSummary)
def delete_group(name: str, store: StoreDep) -> ConfigSummary:
    """Remove a group; its children move up to its parent."""
    return summarize(store.delete_group(name))


@router.put("/assignments/{symbol}", response_model=ConfigSummary)
def set_assignment(symbol: str, body: AssignmentUpdate, store: StoreDep) -> ConfigSummary:
    """Assign a symbol to categories (several = a split), exclude it, or clear it."""
    return summarize(store.set_assignment(symbol, weights=body.weights, excluded=body.excluded))
