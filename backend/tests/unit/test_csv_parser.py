"""
Unit tests for the Fidelity CSV parser.
"""

import textwrap

import pytest

from app.services.csv_parser import parse_fidelity_csv


MINIMAL_CSV = textwrap.dedent("""\
    Account Name: My Brokerage
    Account Number: Z12345678

    Symbol,Description,Quantity,Last Price,Current Value,Total Cost Basis,Total Gain/Loss Dollar,Percentage Of Account
    VTI,Vanguard Total Stock Market ETF,50,240.00,$12000.00,$10000.00,$2000.00,60.00
    VXUS,Vanguard Total International ETF,100,60.00,$6000.00,$5500.00,$500.00,30.00
    BND,Vanguard Total Bond Market ETF,40,50.00,$2000.00,$2100.00,-$100.00,10.00
    Account Total,,,,$20000.00,,,$100.00
""")


def test_parse_basic_holdings():
    snap = parse_fidelity_csv(MINIMAL_CSV)
    assert len(snap.holdings) == 3
    symbols = {h.symbol for h in snap.holdings}
    assert symbols == {"VTI", "VXUS", "BND"}


def test_total_value():
    snap = parse_fidelity_csv(MINIMAL_CSV)
    assert abs(snap.total_value - 20000.0) < 0.01


def test_total_gain_loss():
    snap = parse_fidelity_csv(MINIMAL_CSV)
    # 2000 + 500 - 100 = 2400
    assert abs(snap.total_gain_loss - 2400.0) < 0.01


def test_percent_of_account():
    snap = parse_fidelity_csv(MINIMAL_CSV)
    vti = next(h for h in snap.holdings if h.symbol == "VTI")
    assert abs(vti.percent_of_account - 60.0) < 0.01


def test_account_total_row_excluded():
    snap = parse_fidelity_csv(MINIMAL_CSV)
    symbols = {h.symbol for h in snap.holdings}
    assert "ACCOUNT TOTAL" not in symbols


def test_empty_file_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_fidelity_csv(b"")


def test_missing_required_column_raises():
    # A CSV with Symbol+Quantity but no Current Value or Percentage triggers the
    # "missing required columns" error (header detection passes but column check fails).
    bad_csv = "Symbol,Description,Quantity\nVTI,Test,10\n"
    with pytest.raises(ValueError, match="missing required columns"):
        parse_fidelity_csv(bad_csv)


def test_na_cost_basis_handled():
    csv = textwrap.dedent("""\
        Symbol,Description,Quantity,Last Price,Current Value,Total Cost Basis,Total Gain/Loss Dollar,Percentage Of Account
        VTI,Vanguard Total Stock Market ETF,50,240.00,$12000.00,--,--,100.00
    """)
    snap = parse_fidelity_csv(csv)
    assert snap.holdings[0].cost_basis is None
    assert snap.holdings[0].total_gain_loss is None


def test_bytes_input():
    snap = parse_fidelity_csv(MINIMAL_CSV.encode("utf-8"))
    assert len(snap.holdings) == 3


def test_bom_stripped():
    bom_csv = "\ufeff" + MINIMAL_CSV
    snap = parse_fidelity_csv(bom_csv.encode("utf-8-sig"))
    assert len(snap.holdings) == 3


def test_fidelity_export_with_footer_disclaimer_rows():
    csv = textwrap.dedent(
        """\
        Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
        Z34832569,Individual - TOD,SPAXX**,HELD IN MONEY MARKET,,,,$250.47,,,,,0.08%,,,Cash,
        Z34832569,Individual - TOD,VTI,VANGUARD INDEX FDS VANGUARD TOTAL STK MKT ETF,170.853,$352.24,+$2.44,$60181.26,+$416.88,+0.69%,+$28590.98,+90.50%,19.81%,$31590.28,$184.90,Cash,
        Z34832569,Individual - TOD,Pending activity,,,,,$53464.98,,,,,,
        "The data and information in this spreadsheet is provided to you solely for your use and is not for distribution."
        "Date downloaded Apr-24-2026 3:33 p.m ET"
        """
    )

    snap = parse_fidelity_csv(csv)

    assert len(snap.holdings) == 1
    symbols = {h.symbol for h in snap.holdings}
    assert symbols == {"VTI"}
