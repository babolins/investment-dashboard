"""
Read/modify/write access to config.yaml that keeps the user's comments.

File format: see ``app.models.config``.  Every edit follows the same steps, under a
module-wide lock (sync FastAPI routes run in a thread pool):

1. parse the file with ruamel.yaml's round-trip loader (comments, order, quoting kept),
2. upgrade a v1 document to v2 in place,
3. apply the edit to the parsed document,
4. validate the *whole* result with ``AllocationConfig`` (a failure writes nothing),
5. serialise to a string, then write the file in place and fsync.

The write is in place (``open("w")``), not temp-file-plus-rename, because the Docker
setup bind-mounts the single config file and ``rename`` onto a mount point fails
(EBUSY).  Serialising and validating first means a bad edit never truncates the file.

Comment handling
----------------
ruamel stores a comment block on the entry that *precedes* it.  So the blank line and
banner above the next section (``# ---- fractional_mappings ----``) are really the
trailing comment of the *last entry* of the previous section.  Naively deleting that
entry deletes the next banner; appending puts the banner above the new entry, inside the
wrong section; emptying a section drops it.  ``_edit_section`` fixes this: it cuts that
trailing block off before the edit and re-attaches it to the section's new last entry
(or to the section key itself when the section ends up empty).  All edits of the four
sections go through it.  Accepted losses: the comment directly above a deleted entry and
the end-of-line comment of a deleted entry.
"""

from __future__ import annotations

import io
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
from ruamel.yaml.tokens import CommentToken

from app.models.config import (
    MAX_CATEGORIES,
    PALETTE,
    AllocationConfig,
    make_yaml,
    parse_yaml,
    resolve_config_paths,
)

_LOCK = threading.Lock()

_CATEGORIES_BANNER = """\
# ---------------------------------------------------------------------------
# categories
# ---------------------------------------------------------------------------
# Your allocation categories, in display order (at most 8).  Edit them in the
# app or here.  buy_symbol: ETF suggested when buying into the category;
# target: optional default target %; color: assigned automatically.
"""

# Top-level sections that hold collections, and the container type each should have.
_SECTIONS: dict[str, type[CommentedMap] | type[CommentedSeq]] = {
    "categories": CommentedMap,
    "direct_mappings": CommentedMap,
    "fractional_mappings": CommentedMap,
    "exclusions": CommentedSeq,
}


class ConfigError(ValueError):
    """An edit would produce an invalid config (HTTP 422)."""


class NotFoundError(ConfigError):
    """The named category does not exist (HTTP 404)."""


class ConflictError(ConfigError):
    """Duplicate name, category still in use, or too many categories (HTTP 409)."""


class ConfigWriteError(Exception):
    """The edit was valid but the file could not be written, e.g. a read-only mount (HTTP 500)."""


class _Unset:
    """Type of the UNSET sentinel (distinguishes "leave alone" from None = "clear")."""


UNSET = _Unset()


# ---------------------------------------------------------------------------
# Comment plumbing (see module docstring)
# ---------------------------------------------------------------------------


def _trailing_slot(parent: CommentedMap, key: str) -> tuple[Any, Any, int]:
    """Locate where ruamel keeps the comment that follows ``parent[key]``.

    Returns (comment dict, its key, index into the 4-slot comment list).  The comment lives
    on the deepest last entry: the last item of a list, or recursively the last value of a
    mapping; for an empty or flow-style (``{a: 1}`` / ``[a]``) container it hangs on the key
    itself, since the closing bracket ends the value.
    """
    child = parent[key]
    if isinstance(child, CommentedMap | CommentedSeq) and child.fa.flow_style():
        return parent.ca.items, key, 2
    if isinstance(child, CommentedSeq) and child:
        return child.ca.items, len(child) - 1, 0
    if isinstance(child, CommentedMap) and child:
        return _trailing_slot(child, next(reversed(child)))
    return parent.ca.items, key, 2


def _edit_section(doc: CommentedMap, section: str, edit: Callable[[Any], object]) -> None:
    """Apply ``edit`` to ``doc[section]`` and keep the comment block that follows the section.

    The block is everything after the first newline of the last entry's comment token: the
    first line is that entry's own end-of-line comment, the rest belongs to what comes next.
    """
    items, key, index = _trailing_slot(doc, section)
    token = items.get(key, [None] * 4)[index]
    eol, _, tail = token.value.partition("\n") if token else ("", "", "")
    if tail:
        token.value = eol + "\n"  # keep only the entry's own comment

    if not doc[section]:
        doc[section].fa.set_block_style()  # refilling an inline `{}` / `[]` should print a block
    edit(doc[section])
    if not doc[section]:
        _drop_leading_comments(doc, section)

    if tail:
        items, key, index = _trailing_slot(doc, section)
        slots = items.setdefault(key, [None] * 4)
        if slots[index] is None:
            slots[index] = CommentToken("\n" + tail, CommentMark(0), None)
        else:
            slots[index].value = slots[index].value.rstrip("\n") + "\n" + tail


def _drop_leading_comments(doc: CommentedMap, section: str) -> None:
    """Forget comments above the removed first entry of a now-empty section.

    ruamel would print them before the ``{}`` placeholder, which is invalid YAML.
    """
    container = doc[section]
    if container.ca.comment:
        container.ca.comment[1] = None
    doc.ca.items.get(section, [None] * 4)[3:] = [None]


def _blank_emptied_sections(doc: CommentedMap) -> None:
    """Write a section that an edit emptied as a bare ``key:`` rather than ``key: {}``.

    A block container left empty prints its ``{}`` *before* the banner comment that now hangs
    on the key; a null value has nowhere to put anything and keeps the banner below the key.
    Sections that were already inline (``{}`` / ``[]``) in the file are left as they are.
    """
    for section in _SECTIONS:
        container = doc[section]
        if not container and not container.fa.flow_style():
            doc[section] = None


def _rename_key(mapping: CommentedMap, old: str, new: str) -> None:
    """Rename a key keeping its position and end-of-line comment."""
    position = list(mapping).index(old)
    comment = mapping.ca.items.pop(old, None)
    value = mapping.pop(old)
    mapping.insert(position, new, value)
    if comment:
        mapping.ca.items[new] = comment


def _to_commented(value: Any) -> Any:
    return (
        CommentedMap((k, _to_commented(v)) for k, v in value.items())
        if isinstance(value, dict)
        else value
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class ConfigStore:
    """Loads the config and applies validated, comment-preserving edits to it."""

    def __init__(self, read_path: Path, write_path: Path) -> None:
        self.read_path = read_path
        self.write_path = write_path

    # -- reading ----------------------------------------------------------

    def _source(self) -> Path:
        # Once written, the write path is the truth even if we started from the example.
        return self.write_path if self.write_path.exists() else self.read_path

    def _read(self) -> tuple[YAML, CommentedMap]:
        yaml = make_yaml()
        return yaml, parse_yaml(self._source(), yaml)

    def load(self) -> AllocationConfig:
        """Current config (read-only: a v1 file is migrated in memory, not rewritten)."""
        _, doc = self._read()
        return AllocationConfig.model_validate(doc)

    # -- writing ----------------------------------------------------------

    def _mutate(self, edit: Callable[[CommentedMap], None]) -> AllocationConfig:
        with _LOCK:
            yaml, doc = self._read()
            _upgrade_to_v2(doc)
            edit(doc)
            _blank_emptied_sections(doc)
            return self._write(yaml, doc)

    def _write(self, yaml: YAML, doc: CommentedMap) -> AllocationConfig:
        try:
            config = AllocationConfig.model_validate(doc)
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc
        buffer = io.StringIO()
        yaml.dump(doc, buffer)
        try:
            self.write_path.parent.mkdir(parents=True, exist_ok=True)
            with self.write_path.open("w") as fh:
                fh.write(buffer.getvalue())
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise ConfigWriteError(f"Could not save config: {exc}") from exc
        return config

    # -- categories -------------------------------------------------------

    def create_category(self, name: str, buy_symbol: str, target: float | None) -> AllocationConfig:
        name = name.strip()

        def edit(doc: CommentedMap) -> None:
            categories: CommentedMap = doc["categories"]
            if name.lower() in {n.lower() for n in categories}:
                raise ConflictError(f"Category '{name}' already exists")
            if len(categories) >= MAX_CATEGORIES:
                raise ConflictError(f"At most {MAX_CATEGORIES} categories are allowed")
            used = {str(c["color"]).lower() for c in categories.values()}
            color = next(c for c in PALETTE if c not in used)
            entry = CommentedMap(
                buy_symbol=buy_symbol, target=target, color=DoubleQuotedScalarString(color)
            )
            _edit_section(doc, "categories", lambda m: m.__setitem__(name, entry))

        return self._mutate(edit)

    def update_category(
        self,
        name: str,
        *,
        new_name: str | None = None,
        buy_symbol: str | None = None,
        target: float | None | _Unset = UNSET,
    ) -> AllocationConfig:
        """Patch a category; renaming cascades to every mapping that uses it."""

        def edit(doc: CommentedMap) -> None:
            categories: CommentedMap = doc["categories"]
            if name not in categories:
                raise NotFoundError(f"Unknown category '{name}'")
            category = categories[name]
            if buy_symbol is not None:
                category["buy_symbol"] = buy_symbol
            if not isinstance(target, _Unset):
                category["target"] = target
            if new_name is not None and new_name.strip() != name:
                self._rename(doc, name, new_name.strip())

        return self._mutate(edit)

    @staticmethod
    def _rename(doc: CommentedMap, old: str, new: str) -> None:
        # A case-only rename ("bonds" -> "Bonds") collides only with itself, which is fine.
        others = {n.lower() for n in doc["categories"] if n != old}
        if new.lower() in others:
            raise ConflictError(f"Category '{new}' already exists")
        _edit_section(doc, "categories", lambda m: _rename_key(m, old, new))
        direct: CommentedMap = doc["direct_mappings"]
        for symbol, category in direct.items():
            if category == old:
                direct[symbol] = new
        for weights in doc["fractional_mappings"].values():
            if old in weights:
                _rename_key(weights, old, new)

    def delete_category(self, name: str) -> AllocationConfig:
        def edit(doc: CommentedMap) -> None:
            if name not in doc["categories"]:
                raise NotFoundError(f"Unknown category '{name}'")
            users = {s for s, c in doc["direct_mappings"].items() if c == name}
            users |= {s for s, w in doc["fractional_mappings"].items() if name in w}
            if users:
                raise ConflictError(
                    f"Category '{name}' is still used by: {', '.join(sorted(map(str, users)))}"
                )
            _edit_section(doc, "categories", lambda m: m.pop(name))

        return self._mutate(edit)

    # -- assignments ------------------------------------------------------

    def set_assignment(
        self,
        symbol: str,
        *,
        weights: dict[str, float] | None = None,
        excluded: bool = False,
    ) -> AllocationConfig:
        """Place a symbol in exactly one of: a category, a split, exclusions, or nowhere."""
        sym = symbol.strip().upper()
        picked = {} if excluded else dict(weights or {})

        def edit(doc: CommentedMap) -> None:
            if unknown := [c for c in picked if c not in doc["categories"]]:
                raise NotFoundError(f"Unknown categories: {unknown}")
            if picked and min(picked.values()) <= 0:
                raise ConfigError("Assignment weights must be greater than 0")

            # Target section and (for a split) the new value; None means "nowhere".
            if excluded:
                target_section = "exclusions"
            elif len(picked) == 1:
                target_section = "direct_mappings"
            elif picked:
                target_section = "fractional_mappings"
            else:
                target_section = None

            for section in ("direct_mappings", "fractional_mappings", "exclusions"):
                if section != target_section:
                    _remove_symbol(doc, section, sym)
            if target_section == "exclusions":
                self._add_exclusion(doc, sym)
            elif target_section == "direct_mappings":
                _put(doc, "direct_mappings", sym, next(iter(picked)))
            elif target_section == "fractional_mappings":
                _put(doc, "fractional_mappings", sym, _to_commented(_normalise(picked)))

        return self._mutate(edit)

    @staticmethod
    def _add_exclusion(doc: CommentedMap, sym: str) -> None:
        if not any(str(x).upper() == sym for x in doc["exclusions"]):
            _edit_section(doc, "exclusions", lambda s: s.append(sym))


def _normalise(weights: dict[str, float]) -> dict[str, float]:
    """Scale to sum 1.  Not rounded: rounding can push the sum past the 1e-6 check."""
    total = sum(weights.values())
    return {category: w / total for category, w in weights.items()}


def _find_key(mapping: CommentedMap, sym: str) -> Any:
    """The existing key for ``sym`` (hand-edited files may use lower case), or None."""
    return next((k for k in mapping if str(k).upper() == sym), None)


def _put(doc: CommentedMap, section: str, sym: str, value: Any) -> None:
    """Set ``sym`` in a mapping section, in place if present (keeps position and comment)."""
    existing = _find_key(doc[section], sym)
    if existing is not None:
        if existing != sym:
            _edit_section(doc, section, lambda m: _rename_key(m, existing, sym))
        doc[section][sym] = value
    else:
        _edit_section(doc, section, lambda m: m.__setitem__(sym, value))


def _remove_symbol(doc: CommentedMap, section: str, sym: str) -> None:
    container = doc[section]
    if isinstance(container, CommentedSeq):

        def drop_items(seq: CommentedSeq) -> None:
            for item in [x for x in seq if str(x).upper() == sym]:
                seq.remove(item)

        _edit_section(doc, section, drop_items)
    elif (key := _find_key(container, sym)) is not None:
        _edit_section(doc, section, lambda m: m.pop(key))


# ---------------------------------------------------------------------------
# v1 -> v2 upgrade of the parsed document
# ---------------------------------------------------------------------------


def _upgrade_to_v2(doc: CommentedMap) -> None:
    """Make ``doc`` a complete v2 document so edits can assume all four sections exist.

    A v1 file gets ``categories`` in the slot of ``primary_symbols`` (the migration rules
    live in ``AllocationConfig``; we just persist its result) and loses the legacy keys.
    """
    for section, container in _SECTIONS.items():
        if section != "categories" and doc.get(section) is None:
            doc[section] = container()  # missing or blank (`exclusions:`) -> empty
    if "categories" not in doc:
        _persist_migration(doc)
    elif doc["categories"] is None:
        doc["categories"] = CommentedMap()


def _persist_migration(doc: CommentedMap) -> None:
    migrated = AllocationConfig.model_validate(doc)
    categories = CommentedMap(
        (
            name,
            CommentedMap(
                buy_symbol=c.buy_symbol, target=c.target, color=DoubleQuotedScalarString(c.color)
            ),
        )
        for name, c in migrated.categories.items()
    )
    position = list(doc).index("primary_symbols") if "primary_symbols" in doc else len(doc)
    if position:
        _replace_legacy_banner(doc, list(doc)[position - 1])
    doc.insert(position, "categories", categories)
    for legacy in ("primary_symbols", "default_target_allocations"):
        doc.pop(legacy, None)
    doc["version"] = DoubleQuotedScalarString("2")


def _replace_legacy_banner(doc: CommentedMap, previous_key: str) -> None:
    """The old ``primary_symbols`` banner trails the previous section; swap in ours."""
    items, key, index = _trailing_slot(doc, previous_key)
    token = items.get(key, [None] * 4)[index]
    if token is not None and "primary_symbols" in token.value:
        eol = token.value.partition("\n")[0]
        token.value = eol + "\n\n" + _CATEGORIES_BANNER


def get_store() -> ConfigStore:
    """A store for the current config paths (resolved per call, see ``resolve_config_paths``)."""
    return ConfigStore(*resolve_config_paths())
