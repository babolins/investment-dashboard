"""
Unit tests for the AllocationConfig YAML schema and loader.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.config import AllocationConfig, load_config
from app.models.schemas import AllocationBucket, BuyRecommendation


def cfg(**kwargs) -> AllocationConfig:
    defaults: dict[str, Any] = dict(
        direct_mappings={"VTI": "VTI"},
        fractional_mappings={},
        exclusions=[],
        primary_symbols={"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"},
    )
    defaults.update(kwargs)
    return AllocationConfig(**defaults)


def test_direct_mapping_unknown_bucket_raises():
    with pytest.raises(ValueError, match="unknown bucket"):
        cfg(direct_mappings={"AAPL": "SPY"})


def test_fractional_weights_not_summing_to_1_raises():
    with pytest.raises(ValueError, match="sum to 1.0"):
        cfg(fractional_mappings={"XT": {"VTI": 0.6, "VXUS": 0.3}})  # sums to 0.9


def test_fractional_unknown_bucket_raises():
    with pytest.raises(ValueError, match="unknown bucket"):
        cfg(fractional_mappings={"XT": {"NASDAQ": 1.0}})


def test_symbol_in_both_direct_and_fractional_raises():
    with pytest.raises(ValueError, match="both direct_mappings and fractional_mappings"):
        AllocationConfig(
            direct_mappings={"XT": "VTI"},
            fractional_mappings={"XT": {"VTI": 0.6, "VXUS": 0.4}},
            exclusions=[],
            primary_symbols={"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"},
        )


def test_bucket_weights_for_direct():
    c = cfg(direct_mappings={"VOO": "VTI"})
    assert c.bucket_weights_for("VOO") == {"VTI": 1.0}


def test_bucket_weights_for_fractional():
    c = cfg(
        direct_mappings={},
        fractional_mappings={"XT": {"VTI": 0.6, "VXUS": 0.4}},
    )
    assert c.bucket_weights_for("XT") == {"VTI": 0.6, "VXUS": 0.4}


def test_is_excluded():
    c = cfg(exclusions=["SPAXX", "fdrxx"])
    assert c.is_excluded("SPAXX")
    assert c.is_excluded("spaxx")  # case-insensitive
    assert c.is_excluded("FDRXX")
    assert not c.is_excluded("VTI")


def test_load_config_from_example(tmp_path: Path):
    """load_config() should succeed using the example config."""
    example = Path(__file__).parent.parent.parent / "config.example.yaml"
    if not example.exists():
        pytest.skip("config.example.yaml not found")
    loaded = load_config(example)
    assert "VTI" in loaded.direct_mappings
    assert loaded.primary_symbols["VTI"] == "VTI"


def test_load_config_file_not_found_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# default_target_allocations normalisation (through the real loader)
# ---------------------------------------------------------------------------


def load_yaml(tmp_path: Path, body: str) -> AllocationConfig:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return load_config(path)


@pytest.mark.parametrize(
    "keys",
    [("VTI", "VXUS", "BND"), ("vti", "vxus", "bnd"), ("VTI", "vxus", "Bnd")],
    ids=["upper", "lower", "mixed"],
)
def test_default_target_keys_are_case_insensitive(tmp_path: Path, keys: tuple[str, str, str]):
    body = f"default_target_allocations:\n  {keys[0]}: 60\n  {keys[1]}: 30\n  {keys[2]}: 10\n"
    target = load_yaml(tmp_path, body).default_target_allocations
    assert target is not None
    assert (target.vti, target.vxus, target.bnd) == (60, 30, 10)


def test_default_target_missing_key_defaults_to_zero(tmp_path: Path):
    # A single bucket at 100% is valid: the omitted keys count as 0.
    target = load_yaml(tmp_path, "default_target_allocations:\n  VTI: 100\n")
    assert target.default_target_allocations is not None
    assert target.default_target_allocations.model_dump() == {"vti": 100, "vxus": 0, "bnd": 0}


def test_default_target_missing_key_still_must_sum_to_100(tmp_path: Path):
    # VXUS/BND default to 0, so 60 + 30 = 90 fails the sum-to-100 check.
    with pytest.raises(ValueError, match="sum to 100"):
        load_yaml(tmp_path, "default_target_allocations:\n  VTI: 60\n  VXUS: 30\n")


def test_default_target_wrong_sum_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="sum to 100"):
        load_yaml(tmp_path, "default_target_allocations: {VTI: 50, VXUS: 50, BND: 50}\n")


@pytest.mark.parametrize(
    "body",
    ["", "version: '1.0'\n", "default_target_allocations: {}\n", "default_target_allocations:\n"],
    ids=["empty-file", "omitted", "empty-dict", "null"],
)
def test_default_target_omitted_or_empty_is_none(tmp_path: Path, body: str):
    assert load_yaml(tmp_path, body).default_target_allocations is None


def test_default_target_accepts_kwargs_directly():
    c = cfg(default_target_allocations={"VTI": 70, "bnd": 30})
    assert c.default_target_allocations is not None
    assert c.default_target_allocations.model_dump() == {"vti": 70, "vxus": 0, "bnd": 30}


# ---------------------------------------------------------------------------
# Bucket-typed schemas
# ---------------------------------------------------------------------------


def test_allocation_bucket_rejects_unknown_bucket():
    with pytest.raises(ValidationError):
        AllocationBucket(bucket="FOO", current_value=1, percent_of_included=1)  # type: ignore[arg-type]


def test_buy_recommendation_rejects_unknown_bucket():
    with pytest.raises(ValidationError):
        BuyRecommendation(
            bucket="FOO",  # type: ignore[arg-type]
            symbol="FOO",
            target_percent=0,
            current_percent=0,
            current_value=0,
            target_value=0,
            buy_amount=0,
            buy_percent_of_investment=0,
        )


@pytest.mark.parametrize(
    "body", ["direct_mappings: [unclosed\n", "- just\n- a list\n"], ids=["malformed", "list"]
)
def test_unreadable_yaml_raises_value_error(tmp_path: Path, body: str):
    with pytest.raises(ValueError):
        load_yaml(tmp_path, body)
