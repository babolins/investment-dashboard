"""
Unit tests for nested categories: model rules (AllocationConfig) and ConfigStore edits.

A category with children is a planning level; one without is a leaf (securities, buy symbol,
colour). Model rules are tested once here; the store tests cover file edits and comments.
"""

from pathlib import Path
from typing import Any

import pytest

from app.models.config import PALETTE, AllocationConfig
from app.services.config_store import UNSET, ConfigStore, ConflictError, NotFoundError

NESTED = """\
version: "2"  # keep version

# ---- CATEGORIES BANNER ----
categories:
  Stocks:  # parent note
    target: 70
  US Stocks:  # core holding
    buy_symbol: VTI
    parent: Stocks
    target: 60
    color: "#2a78d6"
  International:
    buy_symbol: VXUS
    parent: Stocks
    target: 40
    color: "#eb6834"
  Bonds:
    buy_symbol: BND
    target: 30
    color: "#1baf7a"

# ---- DIRECT BANNER ----
direct_mappings:
  VTI: US Stocks       # total market
  BND: Bonds
exclusions: []
"""

# A bare parent (no colour) with a single child: deleting the child turns the parent into a leaf.
PARENT_WITH_ONE_CHILD = """\
version: "2"
categories:
  Stocks:
    target: 100
  Intl:
    buy_symbol: VXUS
    parent: Stocks
    target: 100
    color: "#eb6834"
direct_mappings: {}
exclusions: []
"""


def make_store(tmp_path: Path, text: str) -> tuple[ConfigStore, Path]:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return ConfigStore(path, path), path


def leaf_text(count: int, extra: str = "") -> str:
    """`count` coloured top-level leaves, `extra` appended to the categories block."""
    leaves = "".join(
        f'  L{i}:\n    buy_symbol: S{i}\n    target: 10\n    color: "{PALETTE[i]}"\n'
        for i in range(count)
    )
    return f'version: "2"\ncategories:\n{leaves}{extra}direct_mappings: {{}}\nexclusions: []\n'


def cat(parent: str | None = None, color: str | None = None) -> dict[str, Any]:
    return {"buy_symbol": "VTI", "target": None, "color": color, "parent": parent}


def model(categories: dict[str, Any], **kw: Any) -> AllocationConfig:
    return AllocationConfig.model_validate({"categories": categories, **kw})


def order(text: str, *needles: str) -> None:
    positions = [text.index(n) for n in needles]
    assert positions == sorted(positions), f"{needles} out of order in:\n{text}"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("parent", ["Nope", "stocks", ""])  # lookup is case-sensitive
def test_unknown_parent_rejected(parent: str):
    with pytest.raises(ValueError, match="unknown parent"):
        model({"Stocks": cat(), "C": cat(parent)})


@pytest.mark.parametrize(
    "parents",
    [
        {"A": "A"},
        {"A": "B", "B": "A"},
        {"A": "B", "B": "C", "C": "A"},
        {"T": "A", "A": "B", "B": "A"},  # tail on a cycle
    ],
)
def test_cycles_rejected(parents: dict[str, str]):
    with pytest.raises(ValueError, match="cycle"):
        model({name: cat(parent) for name, parent in parents.items()})


def test_tree_helpers_follow_config_order():
    c = model(
        {
            "Bonds": cat(),
            "Stocks": {"parent": None},  # a bare-ish body: every field is optional
            "US": cat("  Stocks "),  # padding is stripped
            "Intl": cat("Stocks"),
        }
    )
    assert c.category_names == ["Bonds", "Stocks", "US", "Intl"]
    assert c.leaf_names == ["Bonds", "US", "Intl"]
    assert c.children_of("Stocks") == ["US", "Intl"]
    assert c.children_of("Bonds") == []
    assert (c.is_leaf("Stocks"), c.is_leaf("US")) == (False, True)


def test_bare_category_body_loads(tmp_path: Path):
    path = tmp_path / "c.yaml"
    path.write_text('version: "2"\ncategories:\n  Stocks:\n  US:\n    parent: Stocks\n')
    c = ConfigStore(path, path).load()
    assert c.categories["Stocks"].target is None
    assert c.leaf_names == ["US"]


def test_leaf_cap_counts_leaves_not_parents():
    leaves = {f"L{i}": cat() for i in range(7)}
    chain = {"Q": cat(), "P": cat("Q"), "C": cat("P")}  # two parents, one leaf
    assert len(model({**leaves, **chain}).leaf_names) == 8
    with pytest.raises(ValueError):
        model({**leaves, **chain, "Extra": cat()})


@pytest.mark.parametrize(
    "mappings",
    [
        {"direct_mappings": {"VTI": "Stocks"}},
        {"fractional_mappings": {"VT": {"Stocks": 0.5, "Leaf": 0.5}}},
    ],
    ids=["direct", "fractional"],
)
def test_mappings_may_only_reference_leaves(mappings: dict):
    with pytest.raises(ValueError, match="sub-categories"):
        model({"Stocks": cat(), "Leaf": cat("Stocks")}, **mappings)


def test_missing_leaf_colours_take_first_free_palette_entry_in_config_order():
    c = model(
        {
            "A": cat(),
            "B": cat(color=PALETTE[0]),
            "P": cat(color=PALETTE[1]),  # a parent's colour is ignored, not reserved
            "C": cat("P"),
        }
    )
    assert [c.categories[n].color for n in ("A", "B", "C")] == [PALETTE[1], PALETTE[0], PALETTE[2]]
    assert c.categories["P"].color is None


# ---------------------------------------------------------------------------
# Store: create
# ---------------------------------------------------------------------------


def test_create_category_with_parent_and_optional_symbol(tmp_path: Path):
    store, path = make_store(tmp_path, NESTED)
    store.create_category("Gold", "gld", 10, parent="Stocks")
    c = store.create_category("Misc")
    assert (c.categories["Gold"].parent, c.categories["Gold"].target) == ("Stocks", 10)
    assert c.categories["Misc"].buy_symbol is None and c.categories["Misc"].parent is None
    assert store.load() == c
    misc = path.read_text().split("  Misc:")[1].split("direct_mappings")[0]
    assert "buy_symbol" not in misc and "parent" not in misc


@pytest.mark.parametrize(
    ("kwargs", "exc"),
    [
        ({"name": "New", "parent": "Nope"}, NotFoundError),
        ({"name": "New", "parent": "Bonds"}, ConflictError),  # Bonds holds BND
    ],
)
def test_create_category_parent_errors_leave_file_unchanged(tmp_path: Path, kwargs: dict, exc):
    store, path = make_store(tmp_path, NESTED)
    before = path.read_bytes()
    with pytest.raises(exc):
        store.create_category(**kwargs)
    assert path.read_bytes() == before


def test_create_persists_leaf_colour_and_keeps_comments(tmp_path: Path):
    store, path = make_store(tmp_path, NESTED)
    store.create_category("Gold", "GLD")  # appended after the last category, before the banner
    text = path.read_text()
    assert f'color: "{PALETTE[3]}"' in text
    order(text, "  Gold:", f'"{PALETTE[3]}"', "# ---- DIRECT BANNER ----", "direct_mappings:")
    for kept in ("# keep version", "# parent note", "# core holding", "# total market"):
        assert kept in text


def test_parent_turned_leaf_gets_a_colour_on_write(tmp_path: Path):
    store, path = make_store(tmp_path, PARENT_WITH_ONE_CHILD)
    c = store.delete_category("Intl")
    assert c.leaf_names == ["Stocks"]
    assert f'color: "{PALETTE[0]}"' in path.read_text()


@pytest.mark.parametrize("move", [False, True], ids=["create", "move-only-child-out"])
def test_leaf_cap_is_a_conflict_and_leaves_file_unchanged(tmp_path: Path, move: bool):
    # Creating a 9th leaf, or moving a parent's only child to top level (which turns the
    # parent into a leaf as well), would exceed the palette.
    if move:
        text = leaf_text(7, "  P:\n    target: 10\n  Only:\n    parent: P\n    target: 10\n")
    else:
        text = leaf_text(8)
    store, path = make_store(tmp_path, text)
    before = path.read_bytes()
    with pytest.raises(ConflictError):
        if move:
            store.update_category("Only", parent=None)
        else:
            store.create_category("Ninth")
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# Store: update
# ---------------------------------------------------------------------------


def test_update_parent_set_move_clear_and_leave(tmp_path: Path):
    store, path = make_store(tmp_path, NESTED)
    c = store.update_category("Bonds", parent="Stocks")
    assert c.categories["Bonds"].parent == "Stocks"
    bonds_block = path.read_text().split("  Bonds:")[1]  # US Stocks also has "parent: Stocks"
    order(bonds_block, "buy_symbol: BND", "parent: Stocks", "target: 30")  # after buy_symbol
    assert store.update_category("Bonds", parent=UNSET).categories["Bonds"].parent == "Stocks"
    c = store.update_category("Bonds", parent=None)
    assert c.categories["Bonds"].parent is None and c.categories["Bonds"].target == 30
    text = path.read_text()
    assert "parent: null" not in text and text.count("parent:") == 2
    assert "# core holding" in text and "# total market" in text


def test_clearing_a_parent_that_is_the_last_key_keeps_the_banner_below(tmp_path: Path):
    text = NESTED.replace(
        '    buy_symbol: BND\n    target: 30\n    color: "#1baf7a"\n',
        '    buy_symbol: BND\n    target: 30\n    color: "#1baf7a"\n    parent: Stocks\n',
    )
    store, path = make_store(tmp_path, text)
    assert store.update_category("Bonds", parent=None).categories["Bonds"].parent is None
    order(path.read_text(), '"#1baf7a"', "# ---- DIRECT BANNER ----", "direct_mappings:")


@pytest.mark.parametrize(
    ("name", "parent", "exc"),
    [
        ("Stocks", "Stocks", ConflictError),  # itself
        ("Stocks", "International", ConflictError),  # child
        ("Stocks", "Deep", ConflictError),  # grandchild
        ("Stocks", "Nope", NotFoundError),
        ("International", "Bonds", ConflictError),  # a leaf holding securities
    ],
)
def test_update_parent_errors_leave_file_unchanged(tmp_path: Path, name: str, parent: str, exc):
    store, path = make_store(tmp_path, NESTED)
    store.create_category("Deep", parent="International")
    before = path.read_bytes()
    with pytest.raises(exc):
        store.update_category(name, parent=parent)
    assert path.read_bytes() == before


def test_update_buy_symbol_set_clear_and_leave(tmp_path: Path):
    store, path = make_store(tmp_path, NESTED)
    c = store.update_category("Stocks", buy_symbol=" xyz ")  # a parent can carry one
    assert c.categories["Stocks"].buy_symbol == "XYZ"
    order(path.read_text(), "  Stocks:  # parent note", "buy_symbol: XYZ", "target: 70")
    assert (
        store.update_category("Stocks", buy_symbol=UNSET).categories["Stocks"].buy_symbol == "XYZ"
    )
    c = store.update_category("US Stocks", buy_symbol=None)
    assert c.categories["US Stocks"].buy_symbol is None
    assert "VTI\n" not in path.read_text().split("# ---- DIRECT")[0]  # key removed, not nulled
    assert "buy_symbol: null" not in path.read_text()


def test_rename_parent_cascades_to_children_and_keeps_position(tmp_path: Path):
    store, path = make_store(tmp_path, NESTED)
    c = store.update_category("Stocks", new_name="  Equities ")
    assert c.category_names == ["Equities", "US Stocks", "International", "Bonds"]
    assert c.children_of("Equities") == ["US Stocks", "International"]
    assert "  Equities:  # parent note" in path.read_text()


# ---------------------------------------------------------------------------
# Store: delete
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nested", [False, True], ids=["top-level", "nested"])
def test_delete_parent_moves_children_up_keeping_targets(tmp_path: Path, nested: bool):
    store, path = make_store(tmp_path, NESTED)
    doomed, up = "Stocks", None
    if nested:
        store.create_category("Mid", parent="Stocks", target=50)
        store.update_category("International", parent="Mid")
        doomed, up = "Mid", "Stocks"
    c = store.delete_category(doomed)
    assert doomed not in c.categories
    assert c.categories["International"].parent == up
    assert c.categories["International"].target == 40
    if not nested:
        assert c.categories["US Stocks"].parent is None
        assert c.direct_mappings == {"VTI": "US Stocks", "BND": "Bonds"}
    assert "# ---- DIRECT BANNER ----" in path.read_text()
