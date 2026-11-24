"""
Unit tests for ConfigStore: persisted category / assignment edits on config.yaml.

Every test works on files under tmp_path; the real config files are never touched.
"""

import re
import shutil
import threading
from pathlib import Path

import pytest

import app.models.config as config_module
import app.services.config_store as store_module
from app.models.config import MAX_CATEGORIES, PALETTE, AllocationConfig, load_config
from app.services.config_store import (
    UNSET,
    ConfigError,
    ConfigStore,
    ConfigWriteError,
    ConflictError,
    NotFoundError,
    get_store,
)

# A hand-edited v2 file with comments in every position the store must preserve.
COMMENTED_V2 = """\
version: "2"

# ---- CATEGORIES BANNER ----
categories:
  US Stocks:  # core holding
    buy_symbol: VTI
    target: 60
    color: "#2a78d6"
  International:
    buy_symbol: VXUS
    target: 30
    color: "#eb6834"
  Bonds:
    buy_symbol: BND
    target: 10
    color: "#1baf7a"

# ---- DIRECT BANNER ----
direct_mappings:
  # -- US equity --
  VTI: US Stocks       # Vanguard Total Stock Market ETF
  ITOT: US Stocks      # iShares Core S&P Total US Market ETF
  # -- Bonds --
  BND: Bonds           # Vanguard Total Bond Market ETF

# ---- FRACTIONAL BANNER ----
fractional_mappings:
  # XT blends US and international tech
  XT: {US Stocks: 0.6, International: 0.4}   # approximate split

  # VGIT example comment
  # VGIT:
  #   BND: 1.0

# ---- EXCLUSIONS BANNER ----
exclusions:
  - SPAXX    # Fidelity Government Money Market Fund
  - FDRXX    # Fidelity Government Cash Reserves
"""

# Three categories, no mappings: for colour / cap / validation tests.
SIMPLE_V2 = """\
version: "2"
categories:
  US Stocks:
    buy_symbol: VTI
    target: 60
    color: "#2a78d6"
  International:
    buy_symbol: VXUS
    target: 30
    color: "#eb6834"
  Bonds:
    buy_symbol: BND
    target: 10
    color: "#1baf7a"
direct_mappings: {}
fractional_mappings: {}
exclusions: []
"""

# The user's real-world v1 shape (banners, eol comments, whitespace-only line,
# primary_symbols + default_target_allocations after exclusions).
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
# The ETF ticker to recommend when the rebalancer says "buy into this bucket".
primary_symbols:
  VTI: VTI
  VXUS: VXUS
  BND: BND

# ---------------------------------------------------------------------------
# default_target_allocations
# ---------------------------------------------------------------------------
# Optional: pre-fills the rebalance form in the UI.
default_target_allocations:
  VTI: 56.0
  VXUS: 24.0
  BND: 20.0
""".replace("<ws>\n", "  \n")


def make_store(tmp_path: Path, text: str) -> tuple[ConfigStore, Path]:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return ConfigStore(path, path), path


def top_level_keys(text: str) -> list[str]:
    return re.findall(r"^([A-Za-z_]+):", text, flags=re.MULTILINE)


def pos(text: str, needle: str) -> int:
    """Index of the first occurrence of needle; fails loudly when it is missing."""
    assert needle in text, f"{needle!r} not found in:\n{text}"
    return text.index(needle)


def assert_in_order(text: str, *needles: str) -> None:
    positions = [pos(text, n) for n in needles]
    assert positions == sorted(positions), f"{needles} out of order in:\n{text}"


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


def test_error_hierarchy():
    assert issubclass(ConfigError, ValueError)
    assert issubclass(NotFoundError, ConfigError)
    assert issubclass(ConflictError, ConfigError)


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------


def test_load_does_not_modify_a_v1_file(tmp_path: Path):
    store, path = make_store(tmp_path, USER_V1)
    c = store.load()
    assert c.category_names == ["VTI", "VXUS", "BND"]
    assert path.read_text() == USER_V1


# ---------------------------------------------------------------------------
# create_category
# ---------------------------------------------------------------------------


def test_create_category_persists_and_appends(tmp_path: Path):
    store, path = make_store(tmp_path, SIMPLE_V2)
    result = store.create_category("Gold", "gld", 5)
    assert result.category_names == ["US Stocks", "International", "Bonds", "Gold"]
    assert result.categories["Gold"].buy_symbol == "GLD"
    assert result.categories["Gold"].target == 5
    assert load_config(path) == result  # round-trips through the file
    assert store.load() == result


def test_create_category_color_is_first_unused_palette_entry(tmp_path: Path):
    store, _ = make_store(tmp_path, SIMPLE_V2)
    result = store.create_category("Gold", "GLD", None)
    assert result.categories["Gold"].color == PALETTE[3]


def test_create_category_reuses_freed_palette_color(tmp_path: Path):
    store, _ = make_store(tmp_path, SIMPLE_V2)
    store.delete_category("International")  # frees PALETTE[1]
    result = store.create_category("Gold", "GLD", None)
    assert result.categories["Gold"].color == PALETTE[1]
    assert result.category_names == ["US Stocks", "Bonds", "Gold"]


def test_create_category_color_matching_is_case_insensitive(tmp_path: Path):
    store, _ = make_store(tmp_path, SIMPLE_V2.replace("#2a78d6", "#2A78D6"))
    assert store.create_category("Gold", "GLD", None).categories["Gold"].color == PALETTE[3]


def test_create_category_color_skips_hand_picked_colors(tmp_path: Path):
    store, _ = make_store(tmp_path, SIMPLE_V2.replace("#2a78d6", "#123456"))
    # PALETTE[0] is no longer used by anything, so it is the first free entry.
    assert store.create_category("Gold", "GLD", None).categories["Gold"].color == PALETTE[0]


def test_migrated_v1_categories_use_first_palette_entries(tmp_path: Path):
    store, _ = make_store(tmp_path, USER_V1)
    assert [store.load().categories[n].color for n in ("VTI", "VXUS", "BND")] == list(PALETTE[:3])
    assert store.create_category("Gold", "GLD", None).categories["Gold"].color == PALETTE[3]


def test_create_up_to_eight_categories_then_conflict(tmp_path: Path):
    store, path = make_store(tmp_path, SIMPLE_V2)
    for i in range(MAX_CATEGORIES - 3):
        store.create_category(f"Extra {i}", "VTI", None)
    c = store.load()
    assert len(c.categories) == 8
    assert [x.color for x in c.categories.values()] == list(PALETTE)
    before = path.read_bytes()
    with pytest.raises(ConflictError):
        store.create_category("One too many", "VTI", None)
    assert path.read_bytes() == before


@pytest.mark.parametrize("name", ["Bonds", "bonds", "BONDS", "  Bonds "])
def test_create_duplicate_name_is_conflict(tmp_path: Path, name: str):
    store, path = make_store(tmp_path, SIMPLE_V2)
    before = path.read_bytes()
    with pytest.raises(ConflictError):
        store.create_category(name, "AGG", None)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("name", "symbol", "target"),
    [
        ("Excluded", "VTI", None),
        ("Gold", "V TI", None),
        ("Gold", "GLD", 101),
    ],
)
def test_create_invalid_input_is_config_error_and_file_unchanged(
    tmp_path: Path, name: str, symbol: str, target: float | None
):
    store, path = make_store(tmp_path, SIMPLE_V2)
    before = path.read_bytes()
    with pytest.raises(ConfigError) as excinfo:
        store.create_category(name, symbol, target)
    assert not isinstance(excinfo.value, ConflictError | NotFoundError)  # maps to 422, not 409/404
    assert path.read_bytes() == before


def test_validation_errors_are_readable(tmp_path: Path):
    """Users see the message itself, not pydantic's dump of the whole config."""
    store, _ = make_store(tmp_path, SIMPLE_V2)
    with pytest.raises(ConfigError) as excinfo:
        store.create_category("Excluded", "VTI", None)
    message = str(excinfo.value)
    assert "reserved" in message.lower()
    assert "validation error" not in message
    assert "input_value" not in message
    assert "Value error" not in message


def test_create_when_config_is_invalid_raises_and_does_not_write(tmp_path: Path):
    bad = SIMPLE_V2.replace("direct_mappings: {}", "direct_mappings:\n  AAPL: Nowhere")
    store, path = make_store(tmp_path, bad)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        store.create_category("Gold", "GLD", None)
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# update_category
# ---------------------------------------------------------------------------


def test_update_buy_symbol(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.update_category("Bonds", buy_symbol=" agg ")
    assert result.categories["Bonds"].buy_symbol == "AGG"
    assert result.categories["Bonds"].target == 10  # untouched
    assert load_config(path) == result


def test_update_target_set_clear_and_leave_alone(tmp_path: Path):
    store, _ = make_store(tmp_path, SIMPLE_V2)
    assert store.update_category("Bonds", target=25).categories["Bonds"].target == 25
    assert store.update_category("Bonds", buy_symbol="AGG").categories["Bonds"].target == 25
    assert store.update_category("Bonds", target=UNSET).categories["Bonds"].target == 25
    assert store.update_category("Bonds", target=None).categories["Bonds"].target is None
    assert store.load().categories["Bonds"].target is None
    assert store.update_category("Bonds", target=0).categories["Bonds"].target == 0


def test_update_with_no_changes_returns_current_config(tmp_path: Path):
    store, _ = make_store(tmp_path, SIMPLE_V2)
    assert store.update_category("Bonds") == store.load()


def test_update_unknown_category_is_not_found(tmp_path: Path):
    store, path = make_store(tmp_path, SIMPLE_V2)
    before = path.read_bytes()
    with pytest.raises(NotFoundError):
        store.update_category("Nope", buy_symbol="VTI")
    assert path.read_bytes() == before


def test_update_is_case_sensitive_on_the_lookup_name(tmp_path: Path):
    # Names arrive from the URL path exactly as the UI got them from the config.
    store, _ = make_store(tmp_path, SIMPLE_V2)
    with pytest.raises(NotFoundError):
        store.update_category("bonds", buy_symbol="AGG")


def test_update_rename_to_existing_name_is_conflict(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    before = path.read_bytes()
    for clash in ("International", "international", " INTERNATIONAL "):
        with pytest.raises(ConflictError):
            store.update_category("Bonds", new_name=clash)
    assert path.read_bytes() == before


def test_update_rename_conflict_does_not_apply_other_fields(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    before = path.read_bytes()
    with pytest.raises(ConflictError):
        store.update_category("Bonds", new_name="International", buy_symbol="AGG", target=1)
    assert path.read_bytes() == before


def test_update_case_only_rename_is_allowed(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.update_category("Bonds", new_name="BONDS")
    assert result.category_names == ["US Stocks", "International", "BONDS"]
    assert result.weights_for("BND") == {"BONDS": 1.0}


def test_update_identical_name_is_noop(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    before = store.load()
    assert store.update_category("Bonds", new_name="Bonds") == before
    assert store.update_category("Bonds", new_name="  Bonds  ") == before
    assert before == store.load()
    assert "Bonds:" in path.read_text()


def test_update_rename_keeps_position_and_strips_whitespace(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.update_category("International", new_name="  Foreign  ")
    assert result.category_names == ["US Stocks", "Foreign", "Bonds"]
    assert result.categories["Foreign"].buy_symbol == "VXUS"
    assert result.categories["Foreign"].color == PALETTE[1]


@pytest.mark.parametrize(("symbol", "target"), [("V TI", UNSET), ("AGG", 101), ("AGG", -5)])
def test_update_invalid_fields_is_config_error_and_file_unchanged(
    tmp_path: Path, symbol: str, target: float
):
    store, path = make_store(tmp_path, COMMENTED_V2)
    before = path.read_bytes()
    with pytest.raises(ConfigError):
        store.update_category("Bonds", buy_symbol=symbol, target=target)
    assert path.read_bytes() == before


def test_rename_cascades_to_direct_and_fractional_mappings(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.update_category("US Stocks", new_name="Domestic")
    assert result.category_names == ["Domestic", "International", "Bonds"]
    assert result.direct_mappings == {"VTI": "Domestic", "ITOT": "Domestic", "BND": "Bonds"}
    assert result.fractional_mappings == {"XT": {"Domestic": 0.6, "International": 0.4}}
    # key order inside the fractional map is preserved
    assert list(result.fractional_mappings["XT"]) == ["Domestic", "International"]
    assert "US Stocks" not in path.read_text().replace("# core holding", "")
    assert load_config(path) == result


def test_rename_cascade_in_fractional_second_position(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.update_category("International", new_name="Foreign")
    assert list(result.fractional_mappings["XT"]) == ["US Stocks", "Foreign"]
    assert result.direct_mappings["VTI"] == "US Stocks"  # other categories untouched


def test_rename_and_field_changes_in_one_call(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.update_category("Bonds", new_name="Fixed Income", buy_symbol="agg", target=None)
    assert result.categories["Fixed Income"].buy_symbol == "AGG"
    assert result.categories["Fixed Income"].target is None
    assert result.direct_mappings["BND"] == "Fixed Income"


# ---------------------------------------------------------------------------
# delete_category
# ---------------------------------------------------------------------------


def test_delete_unused_category(tmp_path: Path):
    store, path = make_store(tmp_path, SIMPLE_V2)
    result = store.delete_category("Bonds")
    assert result.category_names == ["US Stocks", "International"]
    assert load_config(path) == result


def test_delete_unknown_category_is_not_found(tmp_path: Path):
    store, path = make_store(tmp_path, SIMPLE_V2)
    before = path.read_bytes()
    with pytest.raises(NotFoundError):
        store.delete_category("Nope")
    assert path.read_bytes() == before


def test_delete_category_in_use_lists_direct_and_fractional_symbols(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    before = path.read_bytes()
    with pytest.raises(ConflictError) as excinfo:
        store.delete_category("US Stocks")
    message = str(excinfo.value)
    assert_in_order(message, "ITOT", "VTI", "XT")  # sorted, direct and fractional together
    assert "BND" not in message
    assert path.read_bytes() == before


def test_delete_category_used_only_by_fractional_is_conflict(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    with pytest.raises(ConflictError, match="XT"):
        store.delete_category("International")


def test_delete_succeeds_once_symbols_are_reassigned(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("XT", weights=None)
    result = store.delete_category("International")
    assert result.category_names == ["US Stocks", "Bonds"]


def test_delete_category_used_by_exclusion_only_is_not_in_use(tmp_path: Path):
    # Excluded symbols reference no category; only mappings count.
    store, _ = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("BND", excluded=True)
    assert store.delete_category("Bonds").category_names == ["US Stocks", "International"]


# ---------------------------------------------------------------------------
# set_assignment
# ---------------------------------------------------------------------------


def test_single_category_goes_to_direct_mappings(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("VOO", weights={"US Stocks": 1.0})
    assert result.direct_mappings["VOO"] == "US Stocks"
    assert "VOO" not in result.fractional_mappings
    assert "VOO" not in result.exclusions
    assert load_config(path) == result


def test_several_categories_go_to_fractional_normalised(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("VOO", weights={"US Stocks": 3, "International": 1})
    assert "VOO" not in result.direct_mappings
    weights = result.fractional_mappings["VOO"]
    assert weights["US Stocks"] == pytest.approx(0.75)
    assert weights["International"] == pytest.approx(0.25)
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
    assert load_config(path) == result


def test_normalised_weights_that_do_not_divide_evenly_still_validate(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("VOO", weights={"US Stocks": 1, "International": 1, "Bonds": 1})
    assert sum(result.fractional_mappings["VOO"].values()) == pytest.approx(1.0, abs=1e-6)
    assert load_config(path) == result  # the persisted numbers pass the 1e-6 check on reload


def test_direct_to_fractional_removes_direct_entry(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("VTI", weights={"US Stocks": 1, "Bonds": 1})
    assert "VTI" not in result.direct_mappings
    assert result.fractional_mappings["VTI"] == {
        "US Stocks": pytest.approx(0.5),
        "Bonds": pytest.approx(0.5),
    }


def test_fractional_to_direct_removes_fractional_entry(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("XT", weights={"Bonds": 1})
    assert "XT" not in result.fractional_mappings
    assert result.direct_mappings["XT"] == "Bonds"


@pytest.mark.parametrize("weights", [None, {}], ids=["none", "empty"])
@pytest.mark.parametrize("symbol", ["VTI", "XT", "SPAXX"], ids=["direct", "fractional", "excluded"])
def test_no_weights_and_not_excluded_means_unassigned_everywhere(
    tmp_path: Path, symbol: str, weights: dict[str, float] | None
):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment(symbol, weights=weights)
    assert result.weights_for(symbol) == {}
    assert not result.is_excluded(symbol)
    assert symbol not in result.direct_mappings
    assert symbol not in result.fractional_mappings
    assert symbol not in result.exclusions
    assert load_config(path) == result


def test_unassigning_an_unknown_symbol_is_harmless(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    before = store.load()
    assert store.set_assignment("ZZZZ", weights=None) == before


def test_excluded_goes_to_exclusions_only(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("VTI", excluded=True)
    assert result.is_excluded("VTI")
    assert "VTI" not in result.direct_mappings
    assert "VTI" not in result.fractional_mappings
    assert result.exclusions == ["SPAXX", "FDRXX", "VTI"]
    assert load_config(path) == result


def test_excluding_a_fractional_symbol_removes_it_from_mappings(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("XT", excluded=True)
    assert "XT" not in result.fractional_mappings
    assert result.is_excluded("XT")


def test_excluding_twice_does_not_duplicate(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("SPAXX", excluded=True)
    assert result.exclusions.count("SPAXX") == 1
    assert len(result.exclusions) == 2


def test_mapping_an_excluded_symbol_removes_it_from_exclusions(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment("SPAXX", weights={"Bonds": 1})
    assert not result.is_excluded("SPAXX")
    assert result.exclusions == ["FDRXX"]
    assert result.direct_mappings["SPAXX"] == "Bonds"


@pytest.mark.parametrize("raw", ["voo", "Voo", "  voo  "])
def test_symbol_is_normalised_to_upper_case(tmp_path: Path, raw: str):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.set_assignment(raw, weights={"Bonds": 1})
    assert result.direct_mappings["VOO"] == "Bonds"
    assert "VOO: Bonds" in path.read_text()
    assert "voo" not in path.read_text().lower().replace("voo: bonds", "")


def test_lower_case_hand_edited_key_is_replaced_not_duplicated(tmp_path: Path):
    text = COMMENTED_V2.replace("  ITOT: US Stocks", "  itot: US Stocks")
    store, path = make_store(tmp_path, text)
    result = store.set_assignment("ITOT", weights={"Bonds": 1})
    assert result.direct_mappings["ITOT"] == "Bonds"
    assert len(re.findall(r"(?im)^\s*itot:", path.read_text())) == 1
    assert "itot:" not in path.read_text()


def test_lower_case_hand_edited_exclusion_is_removed(tmp_path: Path):
    text = COMMENTED_V2.replace("  - FDRXX", "  - fdrxx")
    store, _ = make_store(tmp_path, text)
    result = store.set_assignment("FDRXX", weights=None)
    assert result.exclusions == ["SPAXX"]


def test_reassigning_direct_to_direct_updates_in_place(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("VTI", weights={"Bonds": 1})
    text = path.read_text()
    vti_line = next(line for line in text.splitlines() if line.lstrip().startswith("VTI:"))
    assert "Bonds" in vti_line
    assert "# Vanguard Total Stock Market ETF" in vti_line  # eol comment kept
    assert_in_order(text, "# -- US equity --", "VTI:", "ITOT:", "# -- Bonds --", "BND:")


def test_unknown_category_is_not_found_and_file_unchanged(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    before = path.read_bytes()
    with pytest.raises(NotFoundError):
        store.set_assignment("VOO", weights={"Gold": 1})
    with pytest.raises(NotFoundError):
        store.set_assignment("VOO", weights={"Bonds": 1, "Gold": 1})
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "weights",
    [{"Bonds": 0}, {"Bonds": 0, "US Stocks": 0}, {"Bonds": -1}, {"Bonds": 2, "US Stocks": -1}],
    ids=["zero", "all-zero", "negative", "mixed-negative"],
)
def test_non_positive_weights_are_config_error(tmp_path: Path, weights: dict[str, float]):
    store, path = make_store(tmp_path, COMMENTED_V2)
    before = path.read_bytes()
    with pytest.raises(ConfigError) as excinfo:
        store.set_assignment("VTI", weights=weights)
    assert not isinstance(excinfo.value, NotFoundError)
    assert path.read_bytes() == before


def test_returns_updated_config_equal_to_load(tmp_path: Path):
    store, _ = make_store(tmp_path, COMMENTED_V2)
    assert store.set_assignment("VOO", weights={"Bonds": 1}) == store.load()


# ---------------------------------------------------------------------------
# Comment and format preservation
# ---------------------------------------------------------------------------

ALL_COMMENT_LINES = [
    "# ---- CATEGORIES BANNER ----",
    "# ---- DIRECT BANNER ----",
    "# -- US equity --",
    "# -- Bonds --",
    "# ---- FRACTIONAL BANNER ----",
    "# VGIT example comment",
    "#   BND: 1.0",
    "# ---- EXCLUSIONS BANNER ----",
]


def assert_banners_intact(text: str) -> None:
    """Each banner must sit directly above (not inside the previous section of) its own key."""
    assert_in_order(text, "# ---- CATEGORIES BANNER ----", "\ncategories:\n")
    assert_in_order(text, "# ---- DIRECT BANNER ----", "\ndirect_mappings:\n")
    assert_in_order(text, "# ---- FRACTIONAL BANNER ----", "\nfractional_mappings:\n")
    assert_in_order(text, "# ---- EXCLUSIONS BANNER ----", "\nexclusions:\n")
    assert top_level_keys(text) == [
        "version",
        "categories",
        "direct_mappings",
        "fractional_mappings",
        "exclusions",
    ]


def test_create_then_delete_leaves_file_byte_identical(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.create_category("Gold", "GLD", 5)
    store.delete_category("Gold")
    assert path.read_text() == COMMENTED_V2


def test_assign_then_unassign_leaves_banners_and_other_lines(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("NEWSYM", weights={"Bonds": 1})
    store.set_assignment("NEWSYM", weights=None)
    text = path.read_text()
    assert_banners_intact(text)
    for line in ALL_COMMENT_LINES:
        assert line in text


def test_create_category_keeps_following_banner_below_the_new_entry(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.create_category("Gold", "GLD", 5)
    text = path.read_text()
    assert_in_order(text, "  Bonds:", "  Gold:", "# ---- DIRECT BANNER ----", "\ndirect_mappings:")
    assert_banners_intact(text)


def test_delete_last_category_keeps_following_banner(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("BND", weights=None)
    store.delete_category("Bonds")
    text = path.read_text()
    assert "  Bonds:" not in text
    assert_banners_intact(text)


def test_delete_first_category_keeps_banners(tmp_path: Path):
    store, path = make_store(
        tmp_path, SIMPLE_V2.replace("direct_mappings: {}", "# DM\ndirect_mappings: {}")
    )
    store.delete_category("US Stocks")
    assert_in_order(path.read_text(), "categories:", "  International:", "# DM", "direct_mappings:")


def test_append_to_direct_mappings_keeps_fractional_banner_below_it(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("NEWSYM", weights={"Bonds": 1})
    text = path.read_text()
    assert_in_order(
        text, "  BND:", "  NEWSYM: Bonds", "# ---- FRACTIONAL BANNER ----", "\nfractional_mappings:"
    )
    assert_banners_intact(text)


def test_remove_last_direct_mapping_keeps_fractional_banner(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("BND", weights=None)  # last entry of direct_mappings
    text = path.read_text()
    assert "\n  BND:" not in text
    assert "# Vanguard Total Bond Market ETF" not in text
    assert_banners_intact(text)
    assert "# -- US equity --" in text  # earlier comments untouched


def test_append_to_fractional_keeps_exclusions_banner_below_it(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("NEWF", weights={"Bonds": 1, "US Stocks": 1})
    text = path.read_text()
    assert_in_order(text, "  XT:", "  NEWF:", "# ---- EXCLUSIONS BANNER ----", "\nexclusions:")
    assert_banners_intact(text)


def test_remove_last_fractional_mapping_keeps_example_and_exclusions_banner(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("XT", weights=None)
    text = path.read_text()
    assert "  XT:" not in text
    assert_banners_intact(text)
    assert "# VGIT example comment" in text
    assert "#   BND: 1.0" in text


def test_append_to_exclusions_keeps_banner_above_and_entry_below(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("NEWCASH", excluded=True)
    text = path.read_text()
    assert_in_order(
        text, "# ---- EXCLUSIONS BANNER ----", "\nexclusions:", "SPAXX", "FDRXX", "NEWCASH"
    )
    assert_banners_intact(text)


def test_remove_last_exclusion_keeps_banners(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("FDRXX", weights=None)
    text = path.read_text()
    assert "FDRXX" not in text
    assert_banners_intact(text)
    assert "- SPAXX    # Fidelity Government Money Market Fund" in text


def test_remove_middle_exclusion_keeps_neighbours_comment(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("SPAXX", weights=None)
    text = path.read_text()
    assert "- FDRXX    # Fidelity Government Cash Reserves" in text
    assert_banners_intact(text)


def test_emptying_and_refilling_a_section_keeps_following_banner(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    for symbol in ("VTI", "ITOT", "BND"):
        store.set_assignment(symbol, weights=None)
    emptied = path.read_text()
    assert "direct_mappings:" in emptied
    assert_in_order(emptied, "# ---- FRACTIONAL BANNER ----", "\nfractional_mappings:")
    assert store.load().direct_mappings == {}

    store.set_assignment("VOO", weights={"Bonds": 1})
    refilled = path.read_text()
    assert_in_order(refilled, "\ndirect_mappings:", "  VOO: Bonds", "# ---- FRACTIONAL BANNER ----")
    assert_banners_intact(refilled)


def test_emptying_exclusions_and_refilling(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.set_assignment("SPAXX", weights=None)
    store.set_assignment("FDRXX", weights=None)
    assert store.load().exclusions == []
    assert "# ---- EXCLUSIONS BANNER ----" in path.read_text()
    store.set_assignment("CORE", excluded=True)
    text = path.read_text()
    assert_in_order(text, "# ---- EXCLUSIONS BANNER ----", "\nexclusions:", "CORE")
    assert store.load().exclusions == ["CORE"]


def test_end_of_line_comments_survive_value_edits(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.update_category("Bonds", buy_symbol="AGG", target=15)
    store.set_assignment("VTI", weights={"International": 1})
    store.set_assignment("NEWSYM", weights={"Bonds": 1})
    text = path.read_text()
    assert "# Vanguard Total Stock Market ETF" in text
    assert "# iShares Core S&P Total US Market ETF" in text
    assert "# Vanguard Total Bond Market ETF" in text
    assert "# approximate split" in text
    assert "# Fidelity Government Money Market Fund" in text
    assert "# core holding" in text
    for line in ALL_COMMENT_LINES:
        assert line in text


def test_category_rename_keeps_eol_comment_and_updates_mapping_comments(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.update_category("US Stocks", new_name="Domestic")
    text = path.read_text()
    assert re.search(r"^  Domestic:\s+# core holding$", text, flags=re.MULTILINE)
    assert re.search(r"VTI: Domestic\s+# Vanguard Total Stock Market ETF", text)
    assert "# approximate split" in text
    assert_banners_intact(text)


def test_rename_of_last_category_keeps_following_banner(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.update_category("Bonds", new_name="Fixed Income")
    text = path.read_text()
    assert_in_order(text, "  Fixed Income:", "# ---- DIRECT BANNER ----", "\ndirect_mappings:")
    assert_banners_intact(text)


def test_flow_maps_and_lists_stay_flow_style(tmp_path: Path):
    flow_exclusions = COMMENTED_V2.replace(
        "exclusions:\n  - SPAXX    # Fidelity Government Money Market Fund\n"
        "  - FDRXX    # Fidelity Government Cash Reserves\n",
        "exclusions: [SPAXX]\n",
    )
    assert "exclusions: [SPAXX]" in flow_exclusions
    store, path = make_store(tmp_path, flow_exclusions)
    store.update_category("US Stocks", new_name="Domestic")
    store.set_assignment("EXTRA", excluded=True)
    text = path.read_text()
    assert "XT: {Domestic: 0.6, International: 0.4}" in text
    assert "exclusions: [SPAXX, EXTRA]" in text


def test_quoting_of_version_and_colors_is_preserved(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.create_category("Gold", "GLD", 5)
    text = path.read_text()
    assert 'version: "2"' in text
    assert 'color: "#2a78d6"' in text
    assert (
        f'color: "{PALETTE[3]}"' in text
    )  # new colours are quoted too (a bare # starts a comment)


def test_number_formatting_of_untouched_values_is_preserved(tmp_path: Path):
    text = COMMENTED_V2.replace(
        "XT: {US Stocks: 0.6, International: 0.4}", "XT: {US Stocks: 0.60, International: 0.40}"
    )
    store, path = make_store(tmp_path, text)
    store.create_category("Gold", "GLD", 5)
    out = path.read_text()
    assert "{US Stocks: 0.60, International: 0.40}" in out
    assert "    target: 60\n" in out


def test_written_file_is_valid_and_reloads_to_the_returned_config(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    result = store.create_category("Gold", "GLD", 5)
    result = store.update_category("Gold", new_name="Metals")
    result = store.set_assignment("GLDM", weights={"Metals": 1})
    result = store.set_assignment("VT", weights={"Metals": 1, "Bonds": 3})
    assert load_config(path) == result
    assert isinstance(result, AllocationConfig)


def test_untouched_sections_are_byte_identical_after_a_category_edit(tmp_path: Path):
    store, path = make_store(tmp_path, COMMENTED_V2)
    store.update_category("Bonds", buy_symbol="AGG")
    text = path.read_text()
    tail = COMMENTED_V2[COMMENTED_V2.index("# ---- DIRECT BANNER ----") :]
    assert text.endswith(tail)


# ---------------------------------------------------------------------------
# v1 -> v2 migration on first write
# ---------------------------------------------------------------------------


def test_first_write_persists_v2_with_categories_where_primary_symbols_was(tmp_path: Path):
    store, path = make_store(tmp_path, USER_V1)
    result = store.create_category("Gold", "GLD", None)
    text = path.read_text()
    assert 'version: "2"' in text
    assert top_level_keys(text) == [
        "version",
        "direct_mappings",
        "fractional_mappings",
        "exclusions",
        "categories",
    ]
    assert "primary_symbols" not in text
    assert "default_target_allocations" not in text
    assert result.category_names == ["VTI", "VXUS", "BND", "Gold"]
    assert load_config(path) == result


def test_migration_carries_over_targets_symbols_and_colors(tmp_path: Path):
    store, path = make_store(tmp_path, USER_V1)
    store.set_assignment("VOO", weights={"VTI": 1})  # any mutation triggers the upgrade
    c = load_config(path)
    assert [c.categories[n].target for n in ("VTI", "VXUS", "BND")] == [56, 24, 20]
    assert [c.categories[n].buy_symbol for n in ("VTI", "VXUS", "BND")] == ["VTI", "VXUS", "BND"]
    assert [c.categories[n].color for n in ("VTI", "VXUS", "BND")] == list(PALETTE[:3])
    assert c.direct_mappings["VOO"] == "VTI"


def test_migration_preserves_comments_and_leaves_no_stale_banner(tmp_path: Path):
    store, path = make_store(tmp_path, USER_V1)
    store.create_category("Gold", "GLD", None)
    text = path.read_text()
    for line in (
        "# -- US equity --",
        "# -- International / foreign equity --",
        "# -- US bonds --",
        "# XT blends US and international tech",
        "# VGIT is intermediate-term Treasuries",
        "#   BND: 1.0",
        "# Vanguard Total Stock Market ETF",
        "# Fidelity Government Money Market Fund",
        "# Fidelity cash",
    ):
        assert line in text
    # The old primary_symbols / default_target_allocations prose must not survive above categories.
    assert "buy into this bucket" not in text
    assert "pre-fills the rebalance form" not in text
    assert_in_order(text, "\nexclusions:\n", "- FCASH", "\ncategories:\n")


def test_migration_keeps_mappings_valid_and_unchanged(tmp_path: Path):
    store, path = make_store(tmp_path, USER_V1)
    before = store.load()
    store.create_category("Gold", "GLD", None)
    after = load_config(path)
    assert after.direct_mappings == before.direct_mappings
    assert after.fractional_mappings == before.fractional_mappings
    assert after.exclusions == before.exclusions


def test_migrating_a_file_without_primary_symbols_appends_categories(tmp_path: Path):
    store, path = make_store(tmp_path, "version: '1.0'\ndirect_mappings:\n  VTI: VTI\n")
    store.create_category("Gold", "GLD", None)
    text = path.read_text()
    assert top_level_keys(text)[-1] == "categories"
    assert store.load().category_names == ["VTI", "VXUS", "BND", "Gold"]


def test_empty_file_first_write_creates_v2(tmp_path: Path):
    store, path = make_store(tmp_path, "")
    result = store.set_assignment("VOO", weights={"VTI": 1})
    assert result.category_names == ["VTI", "VXUS", "BND"]
    assert result.direct_mappings == {"VOO": "VTI"}
    assert 'version: "2"' in path.read_text()


def test_blank_sections_can_be_edited(tmp_path: Path):
    body = SIMPLE_V2.replace("direct_mappings: {}", "direct_mappings:").replace(
        "exclusions: []", "exclusions:"
    )
    store, _ = make_store(tmp_path, body)
    store.set_assignment("VOO", weights={"Bonds": 1})
    result = store.set_assignment("SPAXX", excluded=True)
    assert result.direct_mappings == {"VOO": "Bonds"}
    assert result.exclusions == ["SPAXX"]


def test_failed_mutation_on_v1_file_does_not_migrate_it(tmp_path: Path):
    store, path = make_store(tmp_path, USER_V1)
    with pytest.raises(NotFoundError):
        store.set_assignment("VOO", weights={"Nope": 1})
    with pytest.raises(ConfigError):
        store.create_category("Excluded", "VTI", None)
    assert path.read_text() == USER_V1


def test_invalid_existing_mapping_is_config_error_on_mutation_and_no_write(tmp_path: Path):
    body = SIMPLE_V2.replace("direct_mappings: {}", "direct_mappings:\n  AAPL: Nowhere")
    store, path = make_store(tmp_path, body)
    before = path.read_bytes()
    with pytest.raises(ConfigError):
        store.set_assignment("VOO", weights={"Bonds": 1})
    assert path.read_bytes() == before


@pytest.mark.parametrize("body", ["direct_mappings: [unclosed\n", "- a\n- list\n"])
def test_unreadable_yaml_mutation_is_value_error_and_file_unchanged(tmp_path: Path, body: str):
    store, path = make_store(tmp_path, body)
    with pytest.raises(ValueError):
        store.create_category("Gold", "GLD", None)
    assert path.read_text() == body


# ---------------------------------------------------------------------------
# Read path vs write path
# ---------------------------------------------------------------------------


def test_reading_example_writes_to_write_path_and_leaves_example_alone(tmp_path: Path):
    example_src = Path(__file__).parent.parent.parent / "config.example.yaml"
    example = tmp_path / "config.example.yaml"
    local = tmp_path / "sub" / "config.yaml"
    shutil.copy(example_src, example)
    before = example.read_bytes()

    store = ConfigStore(example, local)
    assert not local.exists()
    assert store.load().categories  # reading falls through to the example

    result = store.create_category("Gold", "GLD", None)

    assert example.read_bytes() == before
    assert local.exists()  # created (with parent dir) on first write
    assert "Gold" in result.categories
    assert load_config(local) == result
    # the same store now sees its own writes, and so does a fresh one
    assert store.load() == result
    assert ConfigStore(example, local).load() == result


def test_second_write_builds_on_the_write_path_not_the_example(tmp_path: Path):
    example = tmp_path / "config.example.yaml"
    local = tmp_path / "config.yaml"
    example.write_text(SIMPLE_V2)
    store = ConfigStore(example, local)
    store.create_category("Gold", "GLD", None)
    result = store.create_category("Silver", "SLV", None)
    assert result.category_names == ["US Stocks", "International", "Bonds", "Gold", "Silver"]
    assert example.read_text() == SIMPLE_V2


def test_write_is_in_place_not_a_rename(tmp_path: Path):
    # Docker bind-mounts the single config file; replacing it by rename fails (EBUSY).
    store, path = make_store(tmp_path, SIMPLE_V2)
    inode = path.stat().st_ino
    store.create_category("Gold", "GLD", None)
    assert path.stat().st_ino == inode
    assert [p.name for p in tmp_path.iterdir()] == ["config.yaml"]  # no temp files left behind


def test_concurrent_creates_respect_the_cap_and_keep_the_file_valid(tmp_path: Path):
    store, path = make_store(tmp_path, SIMPLE_V2)
    outcomes: list[str] = []
    barrier = threading.Barrier(10)

    def worker(i: int) -> None:
        barrier.wait()
        try:
            store.create_category(f"Cat {i}", "VTI", None)
            outcomes.append("ok")
        except ConflictError:
            outcomes.append("conflict")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("ok") == MAX_CATEGORIES - 3
    assert outcomes.count("conflict") == 10 - (MAX_CATEGORIES - 3)
    loaded = load_config(path)
    assert len(loaded.categories) == MAX_CATEGORIES
    assert len({c.color for c in loaded.categories.values()}) == MAX_CATEGORIES


# ---------------------------------------------------------------------------
# get_store(): path resolution
# ---------------------------------------------------------------------------


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Point every module-level default path at tmp_path; CONFIG_PATH unset."""
    p = {
        "etc": tmp_path / "etc" / "config.yaml",
        "local": tmp_path / "local" / "config.yaml",
        "example": tmp_path / "example" / "config.example.yaml",
    }
    for path in p.values():
        path.parent.mkdir()
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    for module in (config_module, store_module):
        # get_store may read the constants from either module (or import copies of them)
        monkeypatch.setattr(module, "_DEFAULT_CONFIG_PATH", p["etc"], raising=False)
        monkeypatch.setattr(module, "_LOCAL_CONFIG_PATH", p["local"], raising=False)
        monkeypatch.setattr(module, "_EXAMPLE_CONFIG_PATH", p["example"], raising=False)
    return p


def one_category(name: str) -> str:
    return f'categories:\n  {name}:\n    buy_symbol: VTI\n    color: "#2a78d6"\n'


def test_get_store_env_path_is_read_and_write_target(
    paths: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    env_file = tmp_path / "env.yaml"
    env_file.write_text(one_category("FromEnv"))
    for key, path in paths.items():
        path.write_text(one_category(key))
    monkeypatch.setenv("CONFIG_PATH", str(env_file))

    store = get_store()
    assert store.load().category_names == ["FromEnv"]
    store.create_category("Gold", "GLD", None)

    assert load_config(env_file).category_names == ["FromEnv", "Gold"]
    for key, path in paths.items():
        assert path.read_text() == one_category(key)


def test_get_store_reading_example_writes_to_local_config(paths: dict[str, Path]):
    paths["example"].write_text(one_category("example"))
    example_before = paths["example"].read_bytes()
    store = get_store()
    assert store.load().category_names == ["example"]
    assert not paths["local"].exists()

    store.create_category("Gold", "GLD", None)

    assert paths["example"].read_bytes() == example_before  # never written
    assert paths["local"].exists()
    assert load_config(paths["local"]).category_names == ["example", "Gold"]
    # a fresh store (new request) now reads the local file
    assert get_store().load().category_names == ["example", "Gold"]


def test_unwritable_target_raises_config_write_error(tmp_path: Path):
    """Write failures surface as ConfigWriteError (HTTP 500), not a bare OSError."""
    source = tmp_path / "config.yaml"
    source.write_text(COMMENTED_V2)
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")  # a file where the write path needs a directory
    store = ConfigStore(source, blocker / "config.yaml")
    with pytest.raises(ConfigWriteError, match="Could not save config"):
        store.create_category("Gold", "GLD", None)
    assert source.read_text() == COMMENTED_V2
