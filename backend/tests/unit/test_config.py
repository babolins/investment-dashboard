"""
Unit tests for the AllocationConfig YAML schema and loader.
"""

import textwrap
from pathlib import Path

import pytest
import yaml

from app.models.config import AllocationConfig, load_config


def cfg(**kwargs) -> AllocationConfig:
    defaults = dict(
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
