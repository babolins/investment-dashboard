"""
YAML configuration model: user-defined categories and symbol assignments (config v2).

File format
-----------
version: "2"

# Ordered; the key is the display name.  Categories nest: one that nobody names as
# `parent` is a leaf (at most MAX_CATEGORIES of them); securities are assigned to leaves only.
categories:
  Stocks:               # a bare body is fine; a category with sub-categories is a planning level
    target: 60          # optional default target, % of the parent (top level: of the portfolio)
  US Stocks:
    buy_symbol: VTI     # optional; ETF suggested when buying into this leaf
    parent: Stocks      # optional name of another category; omitted/null = top level
    target: 60          # optional, pre-fills the rebalance form
    color: "#2a78d6"    # optional; a leaf without one gets the first unused PALETTE entry
                        # (a parent's colour is ignored)

# symbol -> leaf category name
direct_mappings:
  VOO: US Stocks

# symbol -> {leaf category: weight, ...}; weights are > 0 and sum to 1.0
fractional_mappings:
  VT: {US Stocks: 0.6, International: 0.4}

# symbols ignored by the allocation (cash, money-market, ...); wins over any mapping
exclusions: [SPAXX]

Version 1 files (``primary_symbols`` + ``default_target_allocations``, three fixed
VTI/VXUS/BND buckets) are migrated in memory on load by ``AllocationConfig``; the
config store persists the v2 form on its first write.  Targets are *not* required to
sum to 100 here; that is only checked when a rebalance is requested.  Names are unique
(ignoring case); categories with sub-categories do not count towards the cap.

This module only reads: edits (which must keep the user's comments) live in
``app.services.config_store``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

# Validated categorical colours (light mode); a leaf without one takes the first unused one.
PALETTE: tuple[str, ...] = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
)
MAX_CATEGORIES = len(PALETTE)  # max leaf categories (those without sub-categories)
# Names the UI uses for pseudo-categories in charts and tables.
RESERVED_NAMES = frozenset({"excluded", "unassigned"})
MAX_NAME_LENGTH = 40

_LEGACY_KEYS = ("primary_symbols", "default_target_allocations")
_LEGACY_BUCKETS = {"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"}
_WEIGHT_TOLERANCE = 1e-6


def _strip_parent(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


class CategoryConfig(BaseModel):
    """One allocation category (the name is the key in ``AllocationConfig.categories``)."""

    buy_symbol: str | None = Field(default=None, pattern=r"^[A-Z0-9.\-]{1,10}$")
    parent: str | None = None  # another category's name; None = top level
    target: float | None = Field(default=None, ge=0, le=100)  # % of the parent
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("buy_symbol", mode="before")
    @classmethod
    def _normalise_symbol(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v

    _strip_parent = field_validator("parent", mode="before")(_strip_parent)


def _clean_names[T](mapping: dict[str, T]) -> dict[str, T]:
    """Strip keys and enforce the category name rules."""
    names: dict[str, T] = {}
    seen: set[str] = set()
    for raw, item in mapping.items():
        name = raw.strip()
        if not 1 <= len(name) <= MAX_NAME_LENGTH:
            raise ValueError(f"Category name '{raw}' must be 1-{MAX_NAME_LENGTH} characters")
        if "/" in name:
            raise ValueError(f"Category name '{name}' must not contain '/'")
        if name.lower() in RESERVED_NAMES:
            raise ValueError(f"Category name '{name}' is reserved")
        if name.lower() in seen:
            raise ValueError(f"Duplicate category name '{name}' (names are case-insensitive)")
        seen.add(name.lower())
        names[name] = item
    return names


def _migrate_v1(data: dict[str, Any]) -> dict[str, Any]:
    """Turn primary_symbols + default_target_allocations into ``categories``."""
    primary = data.get("primary_symbols") or _LEGACY_BUCKETS
    targets = {str(k).lower(): v for k, v in (data.get("default_target_allocations") or {}).items()}
    categories = {
        str(name): {
            "buy_symbol": symbol,
            "target": targets.get(str(name).lower()),
            # Beyond the palette the 8-category cap rejects the config anyway.
            "color": PALETTE[i % len(PALETTE)],
        }
        for i, (name, symbol) in enumerate(primary.items())
    }
    kept = {k: v for k, v in data.items() if k not in _LEGACY_KEYS}
    return {**kept, "version": "2", "categories": categories}


class AllocationConfig(BaseModel):
    """Validated in-memory representation of config.yaml."""

    version: str = "2"
    categories: dict[str, CategoryConfig] = Field(default_factory=dict)  # insertion-ordered
    direct_mappings: dict[str, str] = Field(default_factory=dict)
    fractional_mappings: dict[str, dict[str, float]] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Validators                                                           #
    # ------------------------------------------------------------------ #

    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data: Any) -> Any:
        # Key presence, not the version string, decides: hand-edited files often lack one.
        if isinstance(data, dict) and "categories" not in data:
            return _migrate_v1(data)
        return data

    @field_validator("categories", "direct_mappings", "fractional_mappings", mode="before")
    @classmethod
    def _blank_map(cls, v: object) -> object:
        return {} if v is None else v  # a bare `exclusions:`-style key loads as None

    @field_validator("categories", mode="before")
    @classmethod
    def _blank_categories(cls, v: object) -> object:
        # A bare entry (`Stocks:`) loads as None.
        if not isinstance(v, dict):
            return v
        return {name: {} if body is None else body for name, body in v.items()}

    @field_validator("exclusions", mode="before")
    @classmethod
    def _blank_list(cls, v: object) -> object:
        return [] if v is None else v

    @field_validator("categories")
    @classmethod
    def _validate_names(cls, v: dict[str, CategoryConfig]) -> dict[str, CategoryConfig]:
        return _clean_names(v)

    @field_validator("direct_mappings")
    @classmethod
    def _uppercase_direct(cls, v: dict[str, str]) -> dict[str, str]:
        return {s.upper(): c for s, c in v.items()}

    @field_validator("fractional_mappings")
    @classmethod
    def _validate_weights(cls, v: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        for symbol, weights in v.items():
            if any(w <= 0 for w in weights.values()):
                raise ValueError(f"Fractional weights for '{symbol}' must be greater than 0")
            total = sum(weights.values())
            if abs(total - 1.0) > _WEIGHT_TOLERANCE:
                raise ValueError(
                    f"Fractional weights for '{symbol}' must sum to 1.0, got {total:.6f}"
                )
        return {s.upper(): w for s, w in v.items()}

    @field_validator("exclusions")
    @classmethod
    def _uppercase_exclusions(cls, v: list[str]) -> list[str]:
        return [s.upper() for s in v]

    @model_validator(mode="after")
    def _check_hierarchy(self) -> AllocationConfig:
        for name, category in self.categories.items():
            if category.parent is not None and category.parent not in self.categories:
                raise ValueError(
                    f"Category '{name}' has unknown parent '{category.parent}'. "
                    f"Defined: {self.category_names}"
                )
        for start in self.categories:
            seen, node = {start}, self.categories[start].parent
            while node is not None:
                if node in seen:
                    raise ValueError(f"Category parents form a cycle through '{node}'")
                seen.add(node)
                node = self.categories[node].parent
        if len(self.leaf_names) > MAX_CATEGORIES:
            raise ValueError(
                f"At most {MAX_CATEGORIES} categories without sub-categories are allowed, "
                f"got {len(self.leaf_names)}"
            )
        return self

    @model_validator(mode="after")
    def _check_references(self) -> AllocationConfig:
        overlap = set(self.direct_mappings) & set(self.fractional_mappings)
        if overlap:
            raise ValueError(
                f"Symbols appear in both direct_mappings and fractional_mappings: "
                f"{sorted(overlap)}. A symbol can only be in one."
            )
        used = set(self.direct_mappings.values())
        used.update(c for weights in self.fractional_mappings.values() for c in weights)
        unknown = used - set(self.categories)
        if unknown:
            raise ValueError(
                f"Mappings reference unknown categories {sorted(unknown)}. "
                f"Defined: {self.category_names}"
            )
        parents = sorted(c for c in used if not self.is_leaf(c))
        if parents:
            raise ValueError(
                f"Mappings reference categories that have sub-categories {parents}; "
                "securities can only be assigned to categories without sub-categories"
            )
        return self

    @model_validator(mode="after")
    def _assign_leaf_colors(self) -> AllocationConfig:
        """Give each leaf a colour (first unused PALETTE entry); a parent's colour is ignored."""
        leaves = self.leaf_names
        used = {c.lower() for n in leaves if (c := self.categories[n].color)}
        for name, category in self.categories.items():
            if name not in leaves:
                category.color = None
            elif category.color is None:
                category.color = next(p for p in PALETTE if p not in used)
                used.add(category.color)
        return self

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @property
    def category_names(self) -> list[str]:
        return list(self.categories)

    @property
    def leaf_names(self) -> list[str]:
        """Categories without sub-categories, in config order: where securities go."""
        parents = {c.parent for c in self.categories.values()}
        return [n for n in self.categories if n not in parents]

    def children_of(self, name: str) -> list[str]:
        return [n for n, c in self.categories.items() if c.parent == name]

    def is_leaf(self, name: str) -> bool:
        return not self.children_of(name)

    def is_excluded(self, symbol: str) -> bool:
        return symbol.upper() in self.exclusions

    def weights_for(self, symbol: str) -> dict[str, float]:
        """{leaf category: weight} for a symbol; a direct mapping is {category: 1.0}.

        Empty when the symbol is unassigned.
        """
        sym = symbol.upper()
        if sym in self.fractional_mappings:
            return self.fractional_mappings[sym]
        if sym in self.direct_mappings:
            return {self.direct_mappings[sym]: 1.0}
        return {}

    def buy_symbol_for(self, category: str) -> str | None:
        return self.categories[category].buy_symbol


# ------------------------------------------------------------------ #
# File loading and path resolution                                    #
# ------------------------------------------------------------------ #

_DEFAULT_CONFIG_PATH = Path("/etc/investment-dashboard/config.yaml")
_BACKEND_DIR = Path(__file__).parent.parent.parent
_LOCAL_CONFIG_PATH = _BACKEND_DIR / "config.yaml"
_EXAMPLE_CONFIG_PATH = _BACKEND_DIR / "config.example.yaml"


def resolve_config_paths() -> tuple[Path, Path]:
    """Return (read_path, write_path), resolved fresh on every call.

    Read order: CONFIG_PATH (must exist) -> /etc/... -> backend/config.yaml -> the example.
    Writes go to the same file, except that the example is never written: edits made while
    reading it create backend/config.yaml instead.

    Raises FileNotFoundError if no config file can be found.
    """
    env_value = os.getenv("CONFIG_PATH")
    if env_value:
        env_path = Path(env_value)
        if not env_path.exists():
            raise FileNotFoundError(
                f"CONFIG_PATH points to '{env_path}', but the file does not exist."
            )
        return env_path, env_path
    for path in (_DEFAULT_CONFIG_PATH, _LOCAL_CONFIG_PATH):
        if path.exists():
            return path, path
    if _EXAMPLE_CONFIG_PATH.exists():
        return _EXAMPLE_CONFIG_PATH, _LOCAL_CONFIG_PATH
    raise FileNotFoundError(
        "No config file found. Expected /etc/investment-dashboard/config.yaml, "
        "backend/config.yaml, or set CONFIG_PATH to a valid file."
    )


def make_yaml() -> YAML:
    """The one ruamel round-trip parser, configured to reproduce config.example.yaml's style."""
    yaml = YAML(typ="rt")
    yaml.indent(mapping=2, sequence=4, offset=2)  # "  - SPAXX" under `exclusions:`
    yaml.preserve_quotes = True  # keep `version: "2"` quoted
    yaml.width = 4096  # never re-wrap long lines or comments
    return yaml


def parse_yaml(path: Path, yaml: YAML | None = None) -> CommentedMap:
    """Parse a config file into a ruamel mapping (empty file -> empty mapping).

    Raises ValueError if the file is not valid YAML or not a mapping.
    """
    try:
        doc = (yaml or make_yaml()).load(path.read_text())
    except YAMLError as exc:
        raise ValueError(f"{path} is not valid YAML: {exc}") from exc
    if doc is None:
        return CommentedMap()
    if not isinstance(doc, CommentedMap):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return doc


def load_config(path: Path | None = None) -> AllocationConfig:
    """
    Load and validate the config (read-only; see ConfigStore for edits).

    Raises FileNotFoundError if no config file is present.
    Raises ValueError if the file is not valid YAML, is not a mapping, or fails
    schema validation (Pydantic's ValidationError is a ValueError).
    """
    if path is None:
        path, _ = resolve_config_paths()
    return AllocationConfig.model_validate(parse_yaml(path))
