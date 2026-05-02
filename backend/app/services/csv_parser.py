"""
Fidelity CSV portfolio export parser.

Fidelity's "Positions" CSV export has a few quirks:
  - Header rows may include account name / number lines before the column headers.
  - The last few rows contain summary totals (e.g. "Account Total") rather than
    individual holdings — these must be stripped.
  - Numeric fields use dollar signs, commas, and may show "--" or "n/a" for
    unavailable values (e.g. cost basis for inherited shares or options).
  - The actual column headers we need are:
      Symbol, Description, Quantity, Last Price, Current Value,
      Total Cost Basis, Total Gain/Loss Dollar, Percentage Of Account

Expected canonical column names (case-insensitive, stripped):
    symbol
    description
    quantity
    last price
    current value
    total cost basis          (may be "cost basis total" in some exports)
    total gain/loss dollar    (may be "total gain/loss ($)")
    percentage of account     (may be "percent of account")
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from app.models.schemas import HoldingRow, PortfolioSnapshot

# ---------------------------------------------------------------------------
# Column name aliases (lower-stripped → canonical field)
# ---------------------------------------------------------------------------

_COL_ALIASES: dict[str, str] = {
    "symbol": "symbol",
    "description": "description",
    "quantity": "quantity",
    "last price": "last_price",
    "shares": "quantity",
    "last price ($)": "last_price",
    "current value": "current_value",
    "current value ($)": "current_value",
    "total cost basis": "cost_basis",
    "cost basis total": "cost_basis",
    "cost basis total ($)": "cost_basis",
    "total gain/loss dollar": "total_gain_loss",
    "total gain/loss ($)": "total_gain_loss",
    "total gain/loss": "total_gain_loss",
    "percentage of account": "percent_of_account",
    "percent of account": "percent_of_account",
    "% of account": "percent_of_account",
}

_REQUIRED_FIELDS = {"symbol", "quantity", "current_value", "percent_of_account"}


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def _parse_number(raw: str) -> float | None:
    """Strip currency symbols, commas, percent signs and convert to float.
    Returns None for '--', 'n/a', or empty strings."""
    cleaned = raw.strip().replace("$", "").replace(",", "").replace("%", "")
    if cleaned in ("", "--", "n/a", "N/A", "**"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _cell_text(value: Any) -> str:
    """Return a safe, stripped string for CSV cells (handles None)."""
    if value is None:
        return ""
    return str(value).strip()


# ---------------------------------------------------------------------------
# Row filtering
# ---------------------------------------------------------------------------

_SKIP_SYMBOL_PREFIXES = (
    "account total",
    "total",
    "pending",
    "beginning",
    "ending",
    "",
)


def _is_data_row(row: dict[str, str]) -> bool:
    """Return True if the row represents an actual security holding."""
    symbol = row.get("symbol", "").strip().lower()
    return symbol not in _SKIP_SYMBOL_PREFIXES and not symbol.startswith("account")


# ---------------------------------------------------------------------------
# Header detection
# ---------------------------------------------------------------------------

def _find_header_row(lines: list[str]) -> int:
    """
    Return the index of the line that contains the CSV column headers.
    Fidelity sometimes prepends account-info lines before the actual headers.
    """
    for i, line in enumerate(lines):
        lower = line.lower()
        if "symbol" in lower and ("quantity" in lower or "shares" in lower or "current value" in lower):
            return i
    raise ValueError(
        "Could not locate CSV header row. "
        "Expected a row containing 'Symbol' and 'Quantity' or 'Current Value'. "
        "Please export your portfolio from Fidelity as a CSV (Positions view) "
        "and try again."
    )


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------

def parse_fidelity_csv(content: bytes | str) -> PortfolioSnapshot:
    """
    Parse a Fidelity positions CSV export and return a PortfolioSnapshot.

    Parameters
    ----------
    content:
        Raw bytes or text of the uploaded CSV file.

    Returns
    -------
    PortfolioSnapshot
        Validated holdings with computed totals.

    Raises
    ------
    ValueError
        If required columns are missing, the file is empty, or the format
        does not match the expected Fidelity export structure.
    """
    if isinstance(content, bytes):
        # Fidelity exports are typically UTF-8 or Latin-1
        try:
            text = content.decode("utf-8-sig")  # strip BOM if present
        except UnicodeDecodeError:
            text = content.decode("latin-1")
    else:
        text = content

    lines = text.splitlines()
    if not lines:
        raise ValueError("Uploaded file is empty.")

    header_idx = _find_header_row(lines)
    csv_text = "\n".join(lines[header_idx:])

    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no headers after header detection.")

    # Build normalised field -> original-header mapping
    field_map: dict[str, str] = {}  # canonical_field -> original_header
    for header in reader.fieldnames:
        key = header.strip().lower()
        if key in _COL_ALIASES:
            canonical = _COL_ALIASES[key]
            field_map[canonical] = header

    missing = _REQUIRED_FIELDS - set(field_map)
    if missing:
        raise ValueError(
            f"CSV is missing required columns: {sorted(missing)}. "
            f"Found headers: {list(reader.fieldnames)}. "
            "Make sure you are uploading the Fidelity Positions CSV export."
        )

    holdings: list[HoldingRow] = []

    for raw_row in reader:
        normalised: dict[str, Any] = {}
        for field, original_header in field_map.items():
            normalised[field] = _cell_text(raw_row.get(original_header, ""))

        if not _is_data_row(normalised):
            continue

        symbol = normalised["symbol"].strip().upper()
        if not symbol:
            continue

        qty = _parse_number(normalised["quantity"])
        if qty is None:
            continue

        current_value = _parse_number(normalised["current_value"])
        if current_value is None:
            continue

        last_price = _parse_number(normalised.get("last_price", "")) or 0.0
        cost_basis = _parse_number(normalised.get("cost_basis", ""))
        total_gain_loss = _parse_number(normalised.get("total_gain_loss", ""))
        pct = _parse_number(normalised["percent_of_account"]) or 0.0

        holdings.append(
            HoldingRow(
                symbol=symbol,
                description=normalised.get("description", ""),
                quantity=qty,
                last_price=last_price,
                current_value=current_value,
                cost_basis=cost_basis,
                total_gain_loss=total_gain_loss,
                percent_of_account=pct,
            )
        )

    if not holdings:
        raise ValueError(
            "No security holdings found in the uploaded CSV. "
            "The file may only contain summary rows or be empty."
        )

    total_value = sum(h.current_value for h in holdings)
    total_gl_parts = [h.total_gain_loss for h in holdings if h.total_gain_loss is not None]
    total_gain_loss = sum(total_gl_parts) if total_gl_parts else None

    return PortfolioSnapshot(
        holdings=holdings,
        total_value=total_value,
        total_gain_loss=total_gain_loss,
    )
