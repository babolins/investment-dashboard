"""
Unit tests for the v2 AllocationConfig schema, v1 -> v2 migration and the loader.
"""

import ast
from pathlib import Path
from typing import Any

import pytest

import app.models.config as config_module
from app.models.config import (
    MAX_CATEGORIES,
    PALETTE,
    RESERVED_NAMES,
    AllocationConfig,
    load_config,
)

# The real-world v1 shape: banners, eol comments, a whitespace-only line, flow-free
# mappings, primary_symbols and default_target_allocations at the end.
USER_V1 = """\
version: "1.0"

# ---------------------------------------------------------------------------
# direct_mappings
# ---------------------------------------------------------------------------
# Map each ticker symbol to exactly one bucket: VTI, VXUS, or BND.
direct_mappings:
  # -- US equity --
  VTI: VTI       # Vanguard Total Stock Market ETF
  KOMP: VTI      # tech-heavy, treated as US equity
<ws>
  # -- International / foreign equity --
  VXUS: VXUS     # Vanguard Total International Stock ETF

  # -- US bonds --
  BND: BND       # Vanguard Total Bond Market ETF

# ---------------------------------------------------------------------------
# fractional_mappings
# ---------------------------------------------------------------------------
fractional_mappings:
  # XT blends US and international tech
  XT:
    VTI: 0.60
    VXUS: 0.40

  # VGIT is intermediate-term Treasuries
  # VGIT:
  #   BND: 1.0

# ---------------------------------------------------------------------------
# exclusions
# ---------------------------------------------------------------------------
exclusions:
  - SPAXX    # Fidelity Government Money Market Fund
  - FCASH    # Fidelity cash

# ---------------------------------------------------------------------------
# primary_symbols
# ---------------------------------------------------------------------------
primary_symbols:
  VTI: VTI
  VXUS: VXUS
  BND: BND

# ---------------------------------------------------------------------------
# default_target_allocations
# ---------------------------------------------------------------------------
default_target_allocations:
  VTI: 56.0
  VXUS: 24.0
  BND: 20.0
""".replace("<ws>\n", "  \n")


def category(symbol: str = "VTI", target: float | None = None, color: str = PALETTE[0]) -> dict:
    return {"buy_symbol": symbol, "target": target, "color": color}


def three_categories() -> dict[str, dict]:
    return {
        "US Stocks": category("VTI", 60, PALETTE[0]),
        "International": category("VXUS", 30, PALETTE[1]),
        "Bonds": category("BND", 10, PALETTE[2]),
    }


def cfg(**kwargs: Any) -> AllocationConfig:
    defaults: dict[str, Any] = dict(
        categories=three_categories(),
        direct_mappings={"VTI": "US Stocks"},
        fractional_mappings={},
        exclusions=[],
    )
    defaults.update(kwargs)
    return AllocationConfig(**defaults)


def load_yaml(tmp_path: Path, body: str) -> AllocationConfig:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return load_config(path)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


def test_palette_and_limits():
    assert PALETTE == (
        "#2a78d6",
        "#eb6834",
        "#1baf7a",
        "#eda100",
        "#e87ba4",
        "#008300",
        "#6250d6",
        "#e34948",
    )
    assert MAX_CATEGORIES == 8
    assert {"excluded", "unassigned"} <= set(RESERVED_NAMES)


def test_config_model_does_not_import_schemas():
    # schemas may import config, never the other way round (import-cycle guard).
    tree = ast.parse(Path(config_module.__file__).read_text())
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(name.endswith("schemas") for name in imported)


# ---------------------------------------------------------------------------
# Category validation
# ---------------------------------------------------------------------------


def test_categories_keep_insertion_order():
    c = cfg()
    assert c.category_names == ["US Stocks", "International", "Bonds"]
    assert list(c.categories) == c.category_names


def test_buy_symbol_for():
    c = cfg()
    assert c.buy_symbol_for("International") == "VXUS"


def test_zero_categories_allowed_on_load():
    c = cfg(categories={}, direct_mappings={})
    assert c.categories == {}
    assert c.category_names == []


def test_eight_categories_allowed_nine_rejected():
    eight = {f"Cat{i}": category("VTI", None, PALETTE[i]) for i in range(8)}
    assert len(cfg(categories=eight, direct_mappings={}).categories) == 8
    nine = {**eight, "Cat8": category("VTI", None, PALETTE[0])}
    with pytest.raises(ValueError):
        cfg(categories=nine, direct_mappings={})


def test_category_name_is_stripped():
    c = cfg(
        categories={"  Bonds  ": category("BND")},
        direct_mappings={"BND": "Bonds"},
    )
    assert c.category_names == ["Bonds"]


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
def test_category_name_length_rejected(name: str):
    with pytest.raises(ValueError):
        cfg(categories={name: category()}, direct_mappings={})


def test_category_name_40_chars_accepted():
    name = "x" * 40
    assert cfg(categories={name: category()}, direct_mappings={}).category_names == [name]


@pytest.mark.parametrize("name", ["Excluded", "excluded", "UNASSIGNED", "Unassigned"])
def test_reserved_category_names_rejected(name: str):
    with pytest.raises(ValueError):
        cfg(categories={name: category()}, direct_mappings={})


@pytest.mark.parametrize("name", ["US/Intl", "/", "a/"])
def test_category_name_with_slash_rejected(name: str):
    # Starlette decodes %2F before routing, so such names could never be addressed.
    with pytest.raises(ValueError):
        cfg(categories={name: category()}, direct_mappings={})


def test_category_names_unique_case_insensitively():
    with pytest.raises(ValueError):
        cfg(
            categories={"Bonds": category("BND"), "bonds": category("AGG", None, PALETTE[1])},
            direct_mappings={},
        )


def test_names_equal_after_stripping_are_duplicates():
    with pytest.raises(ValueError):
        cfg(
            categories={"Bonds": category("BND"), " Bonds": category("AGG", None, PALETTE[1])},
            direct_mappings={},
        )


# ---------------------------------------------------------------------------
# buy_symbol / target / color
# ---------------------------------------------------------------------------


def test_buy_symbol_is_stripped_and_uppercased():
    c = cfg(categories={"X": category(" vti ")}, direct_mappings={})
    assert c.categories["X"].buy_symbol == "VTI"


@pytest.mark.parametrize("symbol", ["BRK.B", "BF-B", "A", "ABCDE12345"])
def test_buy_symbol_accepts_valid(symbol: str):
    c = cfg(categories={"X": category(symbol)}, direct_mappings={})
    assert c.categories["X"].buy_symbol == symbol


@pytest.mark.parametrize("symbol", ["", "  ", "V TI", "VTI$", "ABCDEFGHIJK", "VT/I"])
def test_buy_symbol_rejected(symbol: str):
    with pytest.raises(ValueError):
        cfg(categories={"X": category(symbol)}, direct_mappings={})


def test_buy_symbol_required():
    with pytest.raises(ValueError):
        cfg(categories={"X": {"color": PALETTE[0]}}, direct_mappings={})


@pytest.mark.parametrize("target", [None, 0, 0.0, 33.3, 100])
def test_target_accepts_null_and_0_to_100(target: float | None):
    c = cfg(categories={"X": category("VTI", target)}, direct_mappings={})
    assert c.categories["X"].target == target


@pytest.mark.parametrize("target", [-0.1, -1, 100.01, 101])
def test_target_out_of_range_rejected(target: float):
    with pytest.raises(ValueError):
        cfg(categories={"X": category("VTI", target)}, direct_mappings={})


def test_target_defaults_to_none():
    c = cfg(
        categories={"X": {"buy_symbol": "VTI", "color": PALETTE[0]}},
        direct_mappings={},
    )
    assert c.categories["X"].target is None


def test_targets_need_not_sum_to_100():
    c = cfg(
        categories={"A": category("VTI", 60), "B": category("VXUS", 60, PALETTE[1])},
        direct_mappings={},
    )
    assert c.categories["A"].target == 60 and c.categories["B"].target == 60


@pytest.mark.parametrize("color", ["#2a78d6", "#ABCDEF", "#000000"])
def test_color_accepts_hex(color: str):
    c = cfg(categories={"X": category(color=color)}, direct_mappings={})
    assert c.categories["X"].color == color


@pytest.mark.parametrize("color", ["red", "#12345", "#1234567", "#12345g", "2a78d6", ""])
def test_color_rejected(color: str):
    with pytest.raises(ValueError):
        cfg(categories={"X": category(color=color)}, direct_mappings={})


def test_color_required():
    with pytest.raises(ValueError):
        cfg(categories={"X": {"buy_symbol": "VTI"}}, direct_mappings={})


# ---------------------------------------------------------------------------
# Mappings and exclusions
# ---------------------------------------------------------------------------


def test_direct_mapping_unknown_category_raises():
    with pytest.raises(ValueError, match="unknown categor"):
        cfg(direct_mappings={"AAPL": "SPY"})


def test_fractional_weights_not_summing_to_1_raises():
    with pytest.raises(ValueError, match="sum to 1.0"):
        cfg(fractional_mappings={"XT": {"US Stocks": 0.6, "International": 0.3}})


def test_fractional_unknown_category_raises():
    with pytest.raises(ValueError, match="unknown categor"):
        cfg(fractional_mappings={"XT": {"NASDAQ": 1.0}})


@pytest.mark.parametrize(
    "weights", [{"US Stocks": 1.5, "Bonds": -0.5}, {"US Stocks": 1.0, "Bonds": 0}]
)
def test_fractional_weights_must_be_positive(weights: dict[str, float]):
    with pytest.raises(ValueError):
        cfg(fractional_mappings={"XT": weights})


def test_fractional_sum_tolerance():
    c = cfg(fractional_mappings={"XT": {"US Stocks": 0.3333333, "International": 0.6666667}})
    assert c.weights_for("XT") == {"US Stocks": 0.3333333, "International": 0.6666667}


def test_symbol_in_both_direct_and_fractional_raises():
    with pytest.raises(ValueError, match="both direct_mappings and fractional_mappings"):
        cfg(
            direct_mappings={"XT": "US Stocks"},
            fractional_mappings={"XT": {"US Stocks": 0.6, "International": 0.4}},
        )


def test_overlap_detected_case_insensitively():
    with pytest.raises(ValueError, match="both direct_mappings and fractional_mappings"):
        cfg(
            direct_mappings={"xt": "US Stocks"},
            fractional_mappings={"XT": {"US Stocks": 0.6, "International": 0.4}},
        )


def test_symbols_are_uppercased():
    c = cfg(
        direct_mappings={"voo": "US Stocks"},
        fractional_mappings={"xt": {"US Stocks": 0.5, "International": 0.5}},
        exclusions=["spaxx"],
    )
    assert "VOO" in c.direct_mappings
    assert "XT" in c.fractional_mappings
    assert c.exclusions == ["SPAXX"]


def test_mapping_may_use_stripped_category_name():
    c = cfg(
        categories={" Bonds ": category("BND")},
        direct_mappings={"BND": "Bonds"},
    )
    assert c.weights_for("BND") == {"Bonds": 1.0}


def test_weights_for_direct():
    c = cfg(direct_mappings={"VOO": "US Stocks"})
    assert c.weights_for("VOO") == {"US Stocks": 1.0}


def test_weights_for_fractional():
    c = cfg(
        direct_mappings={},
        fractional_mappings={"XT": {"US Stocks": 0.6, "International": 0.4}},
    )
    assert c.weights_for("XT") == {"US Stocks": 0.6, "International": 0.4}


def test_weights_for_unassigned_is_empty():
    assert cfg().weights_for("NOPE") == {}


def test_weights_for_is_case_insensitive():
    assert cfg(direct_mappings={"VOO": "Bonds"}).weights_for("voo") == {"Bonds": 1.0}


def test_is_excluded():
    c = cfg(exclusions=["SPAXX", "fdrxx"])
    assert c.is_excluded("SPAXX")
    assert c.is_excluded("spaxx")  # case-insensitive
    assert c.is_excluded("FDRXX")
    assert not c.is_excluded("VTI")


def test_excluded_symbol_may_also_be_mapped():
    # Legacy precedence: exclusion wins; the store keeps them mutually exclusive on writes.
    c = cfg(direct_mappings={"VTI": "US Stocks"}, exclusions=["VTI"])
    assert c.is_excluded("VTI")


# ---------------------------------------------------------------------------
# v1 -> v2 migration (plain dicts / kwargs)
# ---------------------------------------------------------------------------


def from_raw(**raw: Any) -> AllocationConfig:
    """Validate untyped (e.g. v1-shaped) config data, as load_config does."""
    return AllocationConfig.model_validate(raw)


def test_v1_kwargs_migrate_to_categories():
    c = from_raw(
        direct_mappings={"VOO": "VTI"},
        fractional_mappings={},
        exclusions=[],
        primary_symbols={"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"},
    )
    assert c.version == "2"
    assert c.category_names == ["VTI", "VXUS", "BND"]
    assert [c.categories[n].color for n in c.category_names] == list(PALETTE[:3])
    assert c.weights_for("VOO") == {"VTI": 1.0}


def test_v1_category_name_is_key_and_buy_symbol_is_value():
    c = from_raw(primary_symbols={"US Stocks": "VOO", "Bonds": "AGG"})
    assert c.category_names == ["US Stocks", "Bonds"]
    assert c.buy_symbol_for("US Stocks") == "VOO"
    assert c.buy_symbol_for("Bonds") == "AGG"


def test_v1_defaults_when_primary_symbols_absent():
    c = from_raw()
    assert c.category_names == ["VTI", "VXUS", "BND"]
    assert [c.categories[n].buy_symbol for n in c.category_names] == ["VTI", "VXUS", "BND"]
    assert [c.categories[n].target for n in c.category_names] == [None, None, None]


@pytest.mark.parametrize(
    "keys",
    [("VTI", "VXUS", "BND"), ("vti", "vxus", "bnd"), ("VTI", "vxus", "Bnd")],
    ids=["upper", "lower", "mixed"],
)
def test_v1_default_target_keys_are_case_insensitive(keys: tuple[str, str, str]):
    c = from_raw(
        default_target_allocations={keys[0]: 60, keys[1]: 30, keys[2]: 10},
    )
    assert [c.categories[n].target for n in ("VTI", "VXUS", "BND")] == [60, 30, 10]


def test_v1_missing_default_target_is_none_not_zero():
    c = from_raw(default_target_allocations={"VTI": 100})
    assert c.categories["VTI"].target == 100
    assert c.categories["VXUS"].target is None
    assert c.categories["BND"].target is None


def test_v1_default_targets_need_not_sum_to_100():
    c = from_raw(default_target_allocations={"VTI": 50, "VXUS": 50, "BND": 50})
    assert [c.categories[n].target for n in ("VTI", "VXUS", "BND")] == [50, 50, 50]


def test_v1_default_targets_keyed_by_custom_category_names():
    c = from_raw(
        primary_symbols={"US Stocks": "VTI", "Bonds": "BND"},
        default_target_allocations={"us stocks": 70, "BONDS": 30, "Gold": 5},
    )
    assert c.categories["US Stocks"].target == 70
    assert c.categories["Bonds"].target == 30
    assert "Gold" not in c.categories


def test_v1_legacy_fields_are_dropped():
    dumped = from_raw(default_target_allocations={"VTI": 100}).model_dump()
    assert "primary_symbols" not in dumped
    assert "default_target_allocations" not in dumped
    assert set(dumped) >= {"version", "categories", "direct_mappings", "exclusions"}


def test_migration_is_keyed_on_categories_presence_not_version():
    c = from_raw(version="1.0", categories={"X": category("VTI")})
    assert list(c.categories) == ["X"]


def test_v1_invalid_reference_still_fails_after_migration():
    with pytest.raises(ValueError, match="unknown categor"):
        from_raw(direct_mappings={"AAPL": "SPY"})


def test_v1_more_than_eight_buckets_rejected():
    primary = {f"B{i}": f"S{i}" for i in range(9)}
    with pytest.raises(ValueError):
        from_raw(primary_symbols=primary)


# ---------------------------------------------------------------------------
# Loading from YAML
# ---------------------------------------------------------------------------


def test_load_real_world_v1_file(tmp_path: Path):
    c = load_yaml(tmp_path, USER_V1)
    assert c.version == "2"
    assert c.category_names == ["VTI", "VXUS", "BND"]
    assert [c.categories[n].target for n in c.category_names] == [56, 24, 20]
    assert [c.categories[n].color for n in c.category_names] == list(PALETTE[:3])
    assert [c.categories[n].buy_symbol for n in c.category_names] == ["VTI", "VXUS", "BND"]
    assert c.weights_for("KOMP") == {"VTI": 1.0}
    assert c.weights_for("XT") == {"VTI": 0.6, "VXUS": 0.4}
    assert c.exclusions == ["SPAXX", "FCASH"]


def test_load_v2_file(tmp_path: Path):
    body = """\
version: "2"
categories:
  US Stocks:
    buy_symbol: VTI
    target: 60
    color: "#2a78d6"
  Bonds:
    buy_symbol: BND
    color: "#eb6834"
direct_mappings:
  VOO: US Stocks
fractional_mappings:
  VT: {US Stocks: 0.6, Bonds: 0.4}
exclusions: [SPAXX]
"""
    c = load_yaml(tmp_path, body)
    assert c.category_names == ["US Stocks", "Bonds"]
    assert c.categories["US Stocks"].target == 60
    assert c.categories["Bonds"].target is None
    assert c.weights_for("VT") == {"US Stocks": 0.6, "Bonds": 0.4}
    assert c.exclusions == ["SPAXX"]


def test_tickers_that_look_like_yaml_1_1_booleans_stay_strings(tmp_path: Path):
    body = """\
categories:
  Stocks:
    buy_symbol: VTI
    color: "#2a78d6"
direct_mappings:
  ON: Stocks
  NO: Stocks
exclusions: [Y, N]
"""
    c = load_yaml(tmp_path, body)
    assert set(c.direct_mappings) == {"ON", "NO"}
    assert c.exclusions == ["Y", "N"]


@pytest.mark.parametrize("body", ["", "# only a comment\n"], ids=["empty", "comment-only"])
def test_empty_file_migrates_to_default_categories(tmp_path: Path, body: str):
    c = load_yaml(tmp_path, body)
    assert c.category_names == ["VTI", "VXUS", "BND"]
    assert [c.categories[n].target for n in c.category_names] == [None, None, None]
    assert c.direct_mappings == {} and c.fractional_mappings == {} and c.exclusions == []


@pytest.mark.parametrize(
    "body",
    [
        "exclusions:\n",
        "direct_mappings:\nfractional_mappings:\nexclusions:\n",
        "categories:\ndirect_mappings:\nexclusions:\n",
    ],
    ids=["blank-exclusions", "blank-v1-sections", "blank-categories"],
)
def test_blank_sections_load_as_empty(tmp_path: Path, body: str):
    c = load_yaml(tmp_path, body)
    assert c.direct_mappings == {}
    assert c.fractional_mappings == {}
    assert c.exclusions == []


def test_load_config_from_example():
    """The shipped example is a valid v2 config."""
    example = Path(__file__).parent.parent.parent / "config.example.yaml"
    if not example.exists():
        pytest.skip("config.example.yaml not found")
    assert "categories:" in example.read_text()
    assert "primary_symbols:" not in example.read_text()
    loaded = load_config(example)
    assert loaded.version == "2"
    assert "VTI" in loaded.categories
    assert loaded.categories["VTI"].buy_symbol == "VTI"
    assert "VTI" in loaded.direct_mappings


def test_load_config_file_not_found_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nonexistent.yaml")


@pytest.mark.parametrize(
    "body",
    ["direct_mappings: [unclosed\n", "- just\n- a list\n", "just a scalar\n"],
    ids=["malformed", "list", "scalar"],
)
def test_unreadable_yaml_raises_value_error(tmp_path: Path, body: str):
    with pytest.raises(ValueError):
        load_yaml(tmp_path, body)


def test_invalid_reference_in_file_raises_value_error(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown categor"):
        load_yaml(tmp_path, "direct_mappings:\n  AAPL: SPY\n")


# ---------------------------------------------------------------------------
# Path resolution: CONFIG_PATH -> /etc -> backend/config.yaml -> example
# ---------------------------------------------------------------------------

V2_ONE = 'categories:\n  {name}:\n    buy_symbol: VTI\n    color: "#2a78d6"\n'


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    p = {
        "etc": tmp_path / "etc" / "config.yaml",
        "local": tmp_path / "local" / "config.yaml",
        "example": tmp_path / "example" / "config.example.yaml",
    }
    for path in p.values():
        path.parent.mkdir()
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.setattr(config_module, "_DEFAULT_CONFIG_PATH", p["etc"])
    monkeypatch.setattr(config_module, "_LOCAL_CONFIG_PATH", p["local"])
    monkeypatch.setattr(config_module, "_EXAMPLE_CONFIG_PATH", p["example"])
    return p


def test_resolution_env_path_wins(
    paths: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    env_file = tmp_path / "env.yaml"
    env_file.write_text(V2_ONE.format(name="FromEnv"))
    for key in paths:
        paths[key].write_text(V2_ONE.format(name=key))
    monkeypatch.setenv("CONFIG_PATH", str(env_file))
    assert load_config().category_names == ["FromEnv"]


def test_resolution_env_path_missing_raises(
    paths: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    paths["local"].write_text(V2_ONE.format(name="local"))
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "missing.yaml"))
    with pytest.raises(FileNotFoundError, match="CONFIG_PATH"):
        load_config()


def test_resolution_etc_before_local_and_example(paths: dict[str, Path]):
    for key in paths:
        paths[key].write_text(V2_ONE.format(name=key))
    assert load_config().category_names == ["etc"]


def test_resolution_local_config_before_example(paths: dict[str, Path]):
    # Dev mode used to skip backend/config.yaml entirely; it must now win over the example.
    paths["local"].write_text(V2_ONE.format(name="local"))
    paths["example"].write_text(V2_ONE.format(name="example"))
    assert load_config().category_names == ["local"]


def test_resolution_falls_back_to_example(paths: dict[str, Path]):
    paths["example"].write_text(V2_ONE.format(name="example"))
    assert load_config().category_names == ["example"]


def test_resolution_nothing_found_raises(paths: dict[str, Path]):
    with pytest.raises(FileNotFoundError, match="No config file found"):
        load_config()
