"""
Unit tests for category groups: model rules (AllocationConfig) and ConfigStore group ops.

Groups are nestable containers; every `target` is a percent of the parent. Flat files
(no `groups:` / `parent:`) must keep working and must never gain a `groups:` section
from unrelated edits.
"""

from pathlib import Path
from typing import Any

import pytest

from app.models.config import PALETTE, AllocationConfig
from app.services.config_store import (
    UNSET,
    ConfigError,
    ConfigStore,
    ConflictError,
    NotFoundError,
)

GROUPED = """\
version: "2"  # keep version

# ---- GROUPS BANNER ----
groups:
  Stocks:  # top group
    target: 60
  Bonds Group:
    target: 40
  Foreign:
    parent: Stocks
    target: 30

# ---- CATEGORIES BANNER ----
categories:
  US Stocks:  # core holding
    buy_symbol: VTI
    parent: Stocks
    target: 70
    color: "#2a78d6"
  International:
    buy_symbol: VXUS
    parent: Foreign
    target: 100
    color: "#eb6834"
  Bonds:
    buy_symbol: BND
    parent: Bonds Group
    target: 100
    color: "#1baf7a"

# ---- DIRECT BANNER ----
direct_mappings:
  VTI: US Stocks       # total market
  BND: Bonds
exclusions: []
"""

FLAT = """\
version: "2"  # keep version

# ---- CATEGORIES BANNER ----
categories:
  US Stocks:  # core holding
    buy_symbol: VTI
    target: 60
    color: "#2a78d6"
  Bonds:
    buy_symbol: BND
    target: 40
    color: "#1baf7a"

# ---- DIRECT BANNER ----
direct_mappings:
  VTI: US Stocks       # total market
exclusions: []
"""

# No banners, no blank lines (like the API integration fixture).
BARE = """\
version: "2"
categories:
  A:
    buy_symbol: VTI
    target: 100
    color: "#2a78d6"
direct_mappings: {}
fractional_mappings: {}
exclusions: []
"""


def make_store(tmp_path: Path, text: str) -> tuple[ConfigStore, Path]:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return ConfigStore(path, path), path


def cat(parent: str | None = None, symbol: str = "VTI") -> dict[str, Any]:
    return {"buy_symbol": symbol, "target": None, "color": PALETTE[0], "parent": parent}


def model(groups: dict | None, categories: dict | None = None, **kw: Any) -> AllocationConfig:
    """Validate raw config data; the default category is named so it can't clash with test groups."""
    return AllocationConfig.model_validate(
        {
            "groups": groups if groups is not None else {},
            "categories": categories if categories is not None else {"Leaf": cat()},
            **kw,
        }
    )


def order(text: str, *needles: str) -> None:
    positions = [text.index(n) for n in needles]
    assert positions == sorted(positions), f"{needles} out of order in:\n{text}"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def test_flat_config_has_no_groups_and_no_parents():
    c = AllocationConfig.model_validate(
        {"categories": {"C": {"buy_symbol": "VTI", "color": PALETTE[0]}}}
    )
    assert c.groups == {}
    assert c.categories["C"].parent is None


def test_bare_groups_section_and_bare_group_entry_load(tmp_path: Path):
    path = tmp_path / "c.yaml"
    path.write_text('version: "2"\ngroups:\ncategories: {}\n')
    assert ConfigStore(path, path).load().groups == {}
    path.write_text('version: "2"\ngroups:\n  Empty:\ncategories: {}\n')
    assert list(ConfigStore(path, path).load().groups) == ["Empty"]


def test_valid_tree_loads_in_order_with_empty_groups_and_many_groups():
    groups = {f"G{i}": {"parent": f"G{i - 1}" if i else None} for i in range(12)}
    c = model(groups, {"C": cat("G11")})
    assert list(c.groups) == [f"G{i}" for i in range(12)]  # >8 groups, 10+ deep, mostly empty
    assert c.categories["C"].parent == "G11"


def test_groups_do_not_count_toward_category_cap():
    cats = {f"C{i}": cat(symbol=f"S{i}") for i in range(8)}
    model({"G": {}}, cats)
    with pytest.raises(ValueError):
        model({"G": {}}, {**cats, "C9": cat()})


@pytest.mark.parametrize("name", ["", "   ", "x" * 41, "a/b", "Excluded", "unassigned"])
def test_invalid_group_names_rejected(name: str):
    with pytest.raises(ValueError):
        model({name: {}})


def test_group_names_stripped_and_forty_chars_ok():
    assert list(model({"  Stocks ": {}, "x" * 40: {}}).groups) == ["Stocks", "x" * 40]


def test_group_names_unique_case_insensitively():
    with pytest.raises(ValueError, match="(?i)group"):
        model({"Stocks": {}, "stocks": {}})


@pytest.mark.parametrize(
    ("groups", "categories"),
    [({"Bonds": {}}, {"bonds": cat()}), ({"bonds": {}}, {"Bonds": cat()})],
)
def test_names_unique_across_groups_and_categories(groups: dict, categories: dict):
    with pytest.raises(ValueError, match="both a group and a category"):
        model(groups, categories)


@pytest.mark.parametrize("target", [-1, 100.5])
def test_group_target_out_of_range_rejected(target: float):
    with pytest.raises(ValueError):
        model({"G": {"target": target}})


def test_group_target_boundaries_and_none_ok():
    c = model({"A": {"target": 0}, "B": {"target": 100}, "C": {"target": None}})
    assert [g.target for g in c.groups.values()] == [0, 100, None]


@pytest.mark.parametrize(
    ("groups", "categories"),
    [
        ({"G": {"parent": "Nope"}}, None),  # group -> unknown group
        ({"Stocks": {}}, {"C": cat("Nope")}),  # category -> unknown group
        ({"Stocks": {}}, {"C": cat("stocks")}),  # lookup is case-sensitive
        ({"Stocks": {}}, {"C": cat(""), "D": cat("Stocks")}),  # blank is not top level
        ({"G": {"parent": "C"}}, {"C": cat()}),  # a category cannot be a parent
        ({"Stocks": {}}, {"C": cat(), "D": cat("C")}),
    ],
)
def test_unknown_parent_rejected(groups: dict, categories: dict | None):
    with pytest.raises(ValueError, match="unknown parent"):
        model(groups, categories)


def test_parent_null_is_top_level_and_padding_is_stripped():
    c = model({"Stocks": {"parent": None}}, {"C": cat("  Stocks ")})
    assert c.categories["C"].parent == "Stocks"


@pytest.mark.parametrize(
    "groups",
    [
        {"A": {"parent": "A"}},
        {"A": {"parent": "B"}, "B": {"parent": "A"}},
        {"A": {"parent": "B"}, "B": {"parent": "C"}, "C": {"parent": "A"}},
        {"T": {"parent": "A"}, "A": {"parent": "B"}, "B": {"parent": "A"}},  # tail on a cycle
    ],
)
def test_group_cycles_rejected(groups: dict):
    with pytest.raises(ValueError, match="cycle"):
        model(groups)


def test_disjoint_trees_ok():
    c = model({"A": {}, "B": {"parent": "A"}, "X": {}, "Y": {"parent": "X"}})
    assert c.groups["Y"].parent == "X"


def test_mapping_to_a_group_name_is_unknown_category():
    with pytest.raises(ValueError, match="(?i)unknown|not a category|categor"):
        model({"Stocks": {}}, direct_mappings={"VTI": "Stocks"})


# ---------------------------------------------------------------------------
# Store: create_group
# ---------------------------------------------------------------------------


def test_create_group_variants_and_persistence(tmp_path: Path):
    store, _ = make_store(tmp_path, GROUPED)
    store.create_group("  New  ")
    store.create_group("Child", parent="Stocks", target=0)
    c = store.create_group("Full", target=100)
    assert list(c.groups) == ["Stocks", "Bonds Group", "Foreign", "New", "Child", "Full"]
    assert c.groups["New"].parent is None and c.groups["New"].target is None
    assert (c.groups["Child"].parent, c.groups["Child"].target) == ("Stocks", 0)
    assert c.groups["Full"].target == 100
    assert store.load() == c


def test_first_group_on_flat_file_creates_section_before_categories(tmp_path: Path):
    store, path = make_store(tmp_path, FLAT)
    c = store.create_group("Stocks", target=60)
    text = path.read_text()
    order(
        text,
        'version: "2"  # keep version',
        "groups:",
        "  Stocks:",
        "# ---- CATEGORIES BANNER ----",
        "\ncategories:",
        "# ---- DIRECT BANNER ----",
    )
    assert text.count("# ---- CATEGORIES BANNER ----") == 1
    assert text.count("# ---- DIRECT BANNER ----") == 1
    assert "# core holding" in text and "# total market" in text
    # The categories block itself is untouched (other sections may be normalised, e.g. `[]` -> bare).
    block = slice(text.index("categories:"), text.index("# ---- DIRECT BANNER ----"))
    flat_block = slice(FLAT.index("categories:"), FLAT.index("# ---- DIRECT BANNER ----"))
    assert text[block] == FLAT[flat_block]
    assert list(c.groups) == ["Stocks"]
    # a second group appends to the section; the categories banner stays below it
    store.create_group("Bonds Group")
    text = path.read_text()
    order(text, "  Stocks:", "  Bonds Group:", "# ---- CATEGORIES BANNER ----", "\ncategories:")


def test_first_group_on_file_without_banners(tmp_path: Path):
    store, path = make_store(tmp_path, BARE)
    store.create_group("G")
    text = path.read_text()
    order(text, 'version: "2"', "groups:", "  G:", "categories:", "direct_mappings:")
    assert store.load().groups.keys() == {"G"}


def test_first_group_keeps_eol_comment_on_previous_key(tmp_path: Path):
    store, path = make_store(tmp_path, FLAT)
    store.create_group("G")
    assert 'version: "2"  # keep version\n' in path.read_text()


def test_first_group_when_categories_is_first_key(tmp_path: Path):
    store, path = make_store(tmp_path, BARE.replace('version: "2"\n', ""))
    store.create_group("G")
    order(path.read_text(), "groups:", "categories:")
    assert store.load().groups.keys() == {"G"}


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: s.create_category("Gold", "GLD", 5),
        lambda s: s.update_category("Bonds", target=5),
        lambda s: s.update_category("Bonds", new_name="Fixed", parent=UNSET),
        lambda s: s.delete_category("Bonds"),
        lambda s: s.set_assignment("BND", weights={"Bonds": 1.0}),
        lambda s: s.set_assignment("VTI", excluded=True),
    ],
)
def test_unrelated_edits_never_add_groups_to_flat_files(tmp_path: Path, edit):
    store, path = make_store(tmp_path, FLAT)
    edit(store)
    assert "groups" not in path.read_text()


@pytest.mark.parametrize(
    ("kwargs", "exc"),
    [
        ({"name": "Stocks"}, ConflictError),
        ({"name": "stocks"}, ConflictError),
        ({"name": " STOCKS "}, ConflictError),
        ({"name": "us stocks"}, ConflictError),  # a category's name
        ({"name": "New", "parent": "Nope"}, NotFoundError),
        ({"name": "New", "parent": "US Stocks"}, NotFoundError),  # categories are not parents
        ({"name": ""}, ConfigError),
        ({"name": "x" * 41}, ConfigError),
        ({"name": "a/b"}, ConfigError),
        ({"name": "Excluded"}, ConfigError),
        ({"name": "New", "target": 101}, ConfigError),
        ({"name": "New", "target": -1}, ConfigError),
    ],
)
def test_create_group_errors_leave_file_unchanged(tmp_path: Path, kwargs: dict, exc: type):
    store, path = make_store(tmp_path, GROUPED)
    before = path.read_bytes()
    with pytest.raises(exc) as info:
        store.create_group(**kwargs)
    if exc is ConfigError:  # validation maps to 422, not 404/409
        assert not isinstance(info.value, ConflictError | NotFoundError)
    assert path.read_bytes() == before


def test_create_category_cannot_reuse_a_group_name(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    before = path.read_bytes()
    for name in ("Stocks", "stocks", "  FOREIGN "):
        with pytest.raises(ConflictError):
            store.create_category(name, "VTI", None)
    assert path.read_bytes() == before


def test_create_category_in_group(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    c = store.create_category("Gold", "GLD", 20, parent="Foreign")
    assert (c.categories["Gold"].parent, c.categories["Gold"].target) == ("Foreign", 20)
    assert store.create_category("Cash", "SGOV", None).categories["Cash"].parent is None
    with pytest.raises(NotFoundError):
        store.create_category("Nope", "X", None, parent="Missing")
    with pytest.raises(NotFoundError):
        store.create_category("Nope", "X", None, parent="Bonds")  # a category
    assert "Nope" not in path.read_text()


def test_create_category_in_group_on_flat_file_needs_existing_group(tmp_path: Path):
    store, path = make_store(tmp_path, FLAT)
    with pytest.raises(NotFoundError):
        store.create_category("Gold", "GLD", None, parent="Stocks")
    assert "groups" not in path.read_text()


# ---------------------------------------------------------------------------
# Store: update_group
# ---------------------------------------------------------------------------


def test_update_group_target_set_clear_leave(tmp_path: Path):
    store, _ = make_store(tmp_path, GROUPED)
    assert store.update_group("Stocks", target=55).groups["Stocks"].target == 55
    assert store.update_group("Stocks", target=UNSET).groups["Stocks"].target == 55
    assert store.update_group("Stocks", target=None).groups["Stocks"].target is None
    assert store.update_group("Stocks", target=0).groups["Stocks"].target == 0


def test_update_group_parent_set_move_and_clear_removes_key(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    assert store.update_group("Bonds Group", parent="Stocks").groups["Bonds Group"].parent == (
        "Stocks"
    )
    assert store.update_group("Foreign", parent="Bonds Group").groups["Foreign"].parent == (
        "Bonds Group"
    )
    assert store.update_group("Foreign", parent=UNSET).groups["Foreign"].parent == "Bonds Group"
    c = store.update_group("Foreign", parent=None)
    assert c.groups["Foreign"].parent is None
    text = path.read_text()
    assert "parent: null" not in text and "parent:\n" not in text
    assert text.count("parent:") == 4  # Bonds Group -> Stocks, plus the three categories' parents
    assert "# ---- CATEGORIES BANNER ----" in text


def test_update_group_moves_into_unrelated_group_or_ancestor(tmp_path: Path):
    store, _ = make_store(tmp_path, GROUPED)
    store.create_group("Deep", parent="Foreign")
    assert store.update_group("Deep", parent="Stocks").groups["Deep"].parent == "Stocks"
    assert store.update_group("Foreign", parent="Stocks").groups["Foreign"].parent == "Stocks"
    assert store.update_group("Stocks", parent="Bonds Group").groups["Stocks"].parent == (
        "Bonds Group"
    )


@pytest.mark.parametrize("parent", ["Stocks", "Foreign", "Deep"])  # self, child, grandchild
def test_update_group_into_self_or_descendant_is_conflict(tmp_path: Path, parent: str):
    store, path = make_store(tmp_path, GROUPED)
    store.create_group("Deep", parent="Foreign")
    before = path.read_bytes()
    with pytest.raises(ConflictError):
        store.update_group("Stocks", parent=parent)
    assert path.read_bytes() == before


def test_update_group_rename_cascades_to_children(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    store.create_group("Deep", parent="Foreign")
    c = store.update_group("Stocks", new_name="  Equities ")
    assert list(c.groups) == ["Equities", "Bonds Group", "Foreign", "Deep"]  # position kept
    assert c.groups["Foreign"].parent == "Equities"
    assert c.categories["US Stocks"].parent == "Equities"
    assert c.groups["Deep"].parent == "Foreign"  # grandchildren untouched
    assert c.categories["International"].parent == "Foreign"
    assert "  Equities:  # top group" in path.read_text()
    assert "Stocks" not in path.read_text().replace("US Stocks", "")


def test_update_group_rename_with_parent_and_target_in_one_call(tmp_path: Path):
    store, _ = make_store(tmp_path, GROUPED)
    c = store.update_group("Foreign", new_name="Intl", parent="Bonds Group", target=10)
    assert (c.groups["Intl"].parent, c.groups["Intl"].target) == ("Bonds Group", 10)
    assert c.categories["International"].parent == "Intl"
    assert "Foreign" not in c.groups


def test_update_group_case_only_rename_allowed_and_noop_returns_config(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    assert "STOCKS" in store.update_group("Stocks", new_name="STOCKS").groups
    before = path.read_bytes()
    assert store.update_group("Bonds Group") == store.load()
    assert path.read_bytes() == before


@pytest.mark.parametrize("new_name", ["Foreign", "foreign", "US Stocks", "bonds"])
def test_update_group_rename_conflict_applies_nothing(tmp_path: Path, new_name: str):
    store, path = make_store(tmp_path, GROUPED)
    before = path.read_bytes()
    with pytest.raises(ConflictError):
        store.update_group("Stocks", new_name=new_name, target=5)
    assert path.read_bytes() == before


def test_update_group_errors(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    before = path.read_bytes()
    with pytest.raises(NotFoundError):
        store.update_group("Nope", target=5)
    with pytest.raises(NotFoundError):
        store.update_group("stocks", target=5)  # lookup is case-sensitive
    with pytest.raises(NotFoundError):
        store.update_group("Stocks", parent="Nope")
    with pytest.raises(NotFoundError):
        store.update_group("Stocks", parent="Bonds")  # a category
    with pytest.raises(ConfigError):
        store.update_group("Stocks", target=101)
    with pytest.raises(ConfigError):
        store.update_group("Stocks", new_name="a/b")
    assert path.read_bytes() == before


def test_group_ops_on_flat_file_are_not_found(tmp_path: Path):
    store, path = make_store(tmp_path, FLAT)
    with pytest.raises(NotFoundError):
        store.update_group("Stocks", target=5)
    with pytest.raises(NotFoundError):
        store.delete_group("Stocks")
    assert path.read_text() == FLAT


# ---------------------------------------------------------------------------
# Store: delete_group
# ---------------------------------------------------------------------------


def test_delete_leaf_group(tmp_path: Path):
    store, _ = make_store(tmp_path, GROUPED)
    store.create_group("Leaf")
    assert list(store.delete_group("Leaf").groups) == ["Stocks", "Bonds Group", "Foreign"]


def test_delete_top_level_group_moves_children_to_top_keeping_targets(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    c = store.delete_group("Stocks")
    assert list(c.groups) == ["Bonds Group", "Foreign"]
    assert c.groups["Foreign"].parent is None and c.groups["Foreign"].target == 30
    assert c.categories["US Stocks"].parent is None and c.categories["US Stocks"].target == 70
    assert "  Stocks:" not in path.read_text()
    assert "# ---- CATEGORIES BANNER ----" in path.read_text()


def test_delete_nested_group_reparents_to_its_parent(tmp_path: Path):
    store, _ = make_store(tmp_path, GROUPED)
    c = store.delete_group("Foreign")
    assert c.categories["International"].parent == "Stocks"
    assert c.categories["International"].target == 100
    assert c.direct_mappings == {"VTI": "US Stocks", "BND": "Bonds"}  # mappings untouched


def test_delete_last_group_keeps_banners_and_loads(tmp_path: Path):
    store, path = make_store(tmp_path, FLAT)
    store.create_group("Only")
    c = store.delete_group("Only")
    text = path.read_text()
    assert c.groups == {}
    order(text, "groups:", "# ---- CATEGORIES BANNER ----", "\ncategories:")
    assert "Only" not in text
    assert "# core holding" in text and "# ---- DIRECT BANNER ----" in text
    assert store.load() == c


def test_delete_group_with_bare_body(tmp_path: Path):
    bare = GROUPED.replace("  Bonds Group:\n    target: 40\n", "  Bonds Group:\n")
    store, _ = make_store(tmp_path, bare)
    assert "Bonds Group" not in store.delete_group("Bonds Group").groups


def test_create_then_delete_group_round_trip_keeps_comments(tmp_path: Path):
    store, path = make_store(tmp_path, FLAT)
    store.create_group("Tmp")
    store.delete_group("Tmp")
    text = path.read_text()
    for kept in ("# keep version", "# core holding", "# total market", "# ---- DIRECT BANNER ----"):
        assert kept in text


# ---------------------------------------------------------------------------
# Store: category parent
# ---------------------------------------------------------------------------


def test_update_category_parent_set_change_clear_leave(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    assert store.update_category("Bonds", parent="Stocks").categories["Bonds"].parent == "Stocks"
    assert store.update_category("Bonds", parent=UNSET).categories["Bonds"].parent == "Stocks"
    c = store.update_category("US Stocks", parent=None)
    assert c.categories["US Stocks"].parent is None
    assert c.categories["US Stocks"].target == 70  # target kept
    text = path.read_text()
    assert "parent: null" not in text
    assert "# core holding" in text and "# total market" in text


def test_update_category_parent_on_flat_file_inserts_key_after_buy_symbol(tmp_path: Path):
    store, path = make_store(tmp_path, FLAT)
    store.create_group("Stocks")
    store.update_category("US Stocks", parent="Stocks")
    text = path.read_text()
    order(text, "  US Stocks:  # core holding", "buy_symbol: VTI", "parent: Stocks", "target: 60")
    # Setting then clearing a parent on the LAST category must not eat the banner below it.
    store.update_category("Bonds", parent="Stocks")
    store.update_category("Bonds", parent=None)
    store.update_category("Bonds", parent="Stocks")
    text = path.read_text()
    order(text, 'color: "#1baf7a"', "# ---- DIRECT BANNER ----", "direct_mappings:")
    assert store.load().categories["Bonds"].parent == "Stocks"


def test_clear_parent_that_is_last_key_of_last_category_keeps_banner(tmp_path: Path):
    shaped = GROUPED.replace(
        '    parent: Bonds Group\n    target: 100\n    color: "#1baf7a"\n',
        '    target: 100\n    color: "#1baf7a"\n    parent: Bonds Group\n',
    )
    store, path = make_store(tmp_path, shaped)
    c = store.update_category("Bonds", parent=None)
    assert c.categories["Bonds"].parent is None
    order(path.read_text(), '"#1baf7a"', "# ---- DIRECT BANNER ----", "direct_mappings:")


@pytest.mark.parametrize("parent", ["Nope", "Bonds", "stocks"])
def test_update_category_unknown_parent_is_not_found(tmp_path: Path, parent: str):
    store, path = make_store(tmp_path, GROUPED)
    before = path.read_bytes()
    with pytest.raises(NotFoundError):
        store.update_category("Bonds", parent=parent)
    assert path.read_bytes() == before


def test_rename_category_keeps_its_parent(tmp_path: Path):
    store, _ = make_store(tmp_path, GROUPED)
    c = store.update_category("US Stocks", new_name="US Equity")
    assert c.categories["US Equity"].parent == "Stocks"
    assert c.direct_mappings["VTI"] == "US Equity"


def test_category_cannot_be_renamed_to_a_group_name(tmp_path: Path):
    store, path = make_store(tmp_path, GROUPED)
    before = path.read_bytes()
    with pytest.raises(ConflictError):
        store.update_category("Bonds", new_name="foreign")
    assert path.read_bytes() == before
