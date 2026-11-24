"""
Shared fixtures for API integration tests.

The app runs against a real YAML file in tmp_path through a ConfigStore,
injected by overriding the get_store dependency.
"""

import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_store
from app.main import app
from app.services.config_store import ConfigStore

# VTI 12000 + VXUS 6000 + BND 2000 are included; SPAXX (1000) is excluded cash;
# AAPL (3000) has no category yet.
CSV_TEXT = textwrap.dedent("""\
    Account Name: My Brokerage
    Account Number: Z12345678

    Symbol,Description,Quantity,Last Price,Current Value,Total Cost Basis,Total Gain/Loss Dollar,Percentage Of Account
    VTI,Vanguard Total Stock Market ETF,50,240.00,$12000.00,$10000.00,$2000.00,57.14
    VXUS,Vanguard Total International ETF,100,60.00,$6000.00,$5500.00,$500.00,28.57
    BND,Vanguard Total Bond Market ETF,40,50.00,$2000.00,$2100.00,-$100.00,9.52
    SPAXX,Fidelity Government Cash Reserves,1000,1.00,$1000.00,,,4.76
    AAPL,Apple Inc,15,200.00,$3000.00,$2500.00,$500.00,14.29
    Account Total,,,,$24000.00,,,$100.00
""")

CONFIG_YAML = textwrap.dedent("""\
    # keep me: top-of-file comment
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
      Bonds:  # keep me: inline comment
        buy_symbol: BND
        target: 10
        color: "#1baf7a"
    direct_mappings:
      VTI: US Stocks
      VXUS: International
      BND: Bonds
    fractional_mappings:
      VT: {US Stocks: 0.6, International: 0.4}
    exclusions: [SPAXX]
""")

# Same data in the legacy v1 layout (migrated on load).
LEGACY_CONFIG_YAML = textwrap.dedent("""\
    # keep me: legacy comment
    primary_symbols:
      VTI: VTI
      VXUS: VXUS
      BND: BND
    default_target_allocations:
      vti: 60
      vxus: 30
      bnd: 10
    direct_mappings:
      VTI: VTI
      VXUS: VXUS
      BND: BND
    exclusions: [SPAXX]
""")


@pytest.fixture
def csv_bytes() -> bytes:
    return CSV_TEXT.encode()


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG_YAML)
    return path


@pytest.fixture
def store(config_path: Path) -> ConfigStore:
    return ConfigStore(config_path, config_path)


@pytest.fixture
def client(store: ConfigStore) -> Iterator[TestClient]:
    """TestClient with get_store overridden; use TestClient(app) for the real loader."""
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()
