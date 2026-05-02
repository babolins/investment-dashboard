"""
YAML configuration model for security-to-bucket mappings.

Schema summary
--------------
version: "1.0"

# symbol -> "VTI" | "VXUS" | "BND"
direct_mappings:
  VOO: VTI
  VXUS: VXUS

# symbol -> {bucket: weight, ...}  weights must sum to 1.0
fractional_mappings:
  XT:
    VTI: 0.60
    VXUS: 0.40

# symbols to exclude entirely from allocation (cash, money-market, etc.)
exclusions:
  - SPAXX
  - FDRXX

# which ETF to suggest when buying into each bucket
primary_symbols:
  VTI: VTI
  VXUS: VXUS
  BND: BND

# optional: pre-fill the rebalance form in the UI
default_target_allocations:
  VTI: 50.0
  VXUS: 30.0
  BND: 20.0
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.schemas import ALLOWED_BUCKETS, TargetAllocation

_ALLOWED_BUCKETS = ALLOWED_BUCKETS  # {'VTI', 'VXUS', 'BND'}


class AllocationConfig(BaseModel):
    """Validated in-memory representation of config.yaml."""

    version: str = "1.0"

    # symbol -> bucket  (e.g. "VOO" -> "VTI")
    direct_mappings: dict[str, str] = Field(default_factory=dict)

    # symbol -> {bucket: weight}  (weights must sum to 1.0 per symbol)
    fractional_mappings: dict[str, dict[str, float]] = Field(default_factory=dict)

    # symbols to drop from allocation analysis entirely
    exclusions: list[str] = Field(default_factory=list)

    # which ETF ticker to suggest buying for each bucket
    primary_symbols: dict[str, str] = Field(
        default_factory=lambda: {"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"}
    )

    # optional UI pre-fill; will be None if omitted from yaml
    default_target_allocations: TargetAllocation | None = None

    # ------------------------------------------------------------------ #
    # Validators                                                           #
    # ------------------------------------------------------------------ #

    @field_validator("direct_mappings")
    @classmethod
    def validate_direct_buckets(cls, v: dict[str, str]) -> dict[str, str]:
        for symbol, bucket in v.items():
            if bucket not in _ALLOWED_BUCKETS:
                raise ValueError(
                    f"Symbol '{symbol}' maps to unknown bucket '{bucket}'. "
                    f"Allowed: {sorted(_ALLOWED_BUCKETS)}"
                )
        return {s.upper(): b for s, b in v.items()}

    @field_validator("fractional_mappings")
    @classmethod
    def validate_fractional_weights(
        cls, v: dict[str, dict[str, float]]
    ) -> dict[str, dict[str, float]]:
        normalised: dict[str, dict[str, float]] = {}
        for symbol, mapping in v.items():
            for bucket in mapping:
                if bucket not in _ALLOWED_BUCKETS:
                    raise ValueError(
                        f"Fractional mapping for '{symbol}' references unknown "
                        f"bucket '{bucket}'. Allowed: {sorted(_ALLOWED_BUCKETS)}"
                    )
            total = sum(mapping.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(
                    f"Fractional weights for '{symbol}' must sum to 1.0, "
                    f"got {total:.6f}"
                )
            normalised[symbol.upper()] = mapping
        return normalised

    @field_validator("exclusions")
    @classmethod
    def uppercase_exclusions(cls, v: list[str]) -> list[str]:
        return [s.upper() for s in v]

    @field_validator("primary_symbols")
    @classmethod
    def validate_primary_symbols(cls, v: dict[str, str]) -> dict[str, str]:
        for bucket in _ALLOWED_BUCKETS:
            if bucket not in v:
                raise ValueError(
                    f"primary_symbols must include an entry for bucket '{bucket}'"
                )
        return v

    @model_validator(mode="after")
    def no_symbol_in_both_direct_and_fractional(self) -> "AllocationConfig":
        overlap = set(self.direct_mappings) & set(self.fractional_mappings)
        if overlap:
            raise ValueError(
                f"Symbols appear in both direct_mappings and fractional_mappings: "
                f"{sorted(overlap)}. A symbol can only be in one."
            )
        return self

    # ------------------------------------------------------------------ #
    # Helpers used by the allocation engine                               #
    # ------------------------------------------------------------------ #

    def is_excluded(self, symbol: str) -> bool:
        return symbol.upper() in self.exclusions

    def bucket_weights_for(self, symbol: str) -> dict[str, float]:
        """
        Return {bucket: weight} for a symbol.
        For a direct mapping returns the single bucket with weight 1.0.
        For a fractional mapping returns the split.
        Returns an empty dict if the symbol is unknown (treated as unclassified).
        """
        sym = symbol.upper()
        if sym in self.fractional_mappings:
            return self.fractional_mappings[sym]
        if sym in self.direct_mappings:
            return {self.direct_mappings[sym]: 1.0}
        return {}

    def primary_symbol_for(self, bucket: str) -> str:
        return self.primary_symbols.get(bucket, bucket)


# ------------------------------------------------------------------ #
# File loader                                                         #
# ------------------------------------------------------------------ #

_DEFAULT_CONFIG_PATH = Path("/etc/investment-dashboard/config.yaml")
_EXAMPLE_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.example.yaml"


def load_config(path: Path | None = None) -> AllocationConfig:
    """
    Load and validate config.yaml.  Falls back to config.example.yaml when
    config.yaml does not exist (dev-mode convenience).

    Raises FileNotFoundError if neither file is present.
    Raises ValueError (via Pydantic) if the schema is invalid.
    """
    if path is None:
        config_path_from_env = os.getenv("CONFIG_PATH")
        if config_path_from_env:
            env_path = Path(config_path_from_env)
            if not env_path.exists():
                raise FileNotFoundError(
                    f"CONFIG_PATH points to '{env_path}', but the file does not exist."
                )
            path = env_path
        elif _DEFAULT_CONFIG_PATH.exists():
            path = _DEFAULT_CONFIG_PATH
        elif _EXAMPLE_CONFIG_PATH.exists():
            path = _EXAMPLE_CONFIG_PATH
        else:
            raise FileNotFoundError(
                "No config file found. Expected /etc/investment-dashboard/config.yaml "
                "or set CONFIG_PATH to a valid file."
            )

    raw = yaml.safe_load(path.read_text())
    if raw is None:
        raw = {}

    # Flatten default_target_allocations dict into TargetAllocation if present
    dta = raw.pop("default_target_allocations", None)
    config = AllocationConfig(**raw)
    if dta:
        config.default_target_allocations = TargetAllocation(
            vti=dta.get("VTI", dta.get("vti", 0)),
            vxus=dta.get("VXUS", dta.get("vxus", 0)),
            bnd=dta.get("BND", dta.get("bnd", 0)),
        )
    return config
