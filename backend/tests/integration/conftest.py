"""
Shared fixtures for API integration tests.
"""

import textwrap
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_config
from app.main import app
from app.models.config import AllocationConfig
from app.models.schemas import TargetAllocation

# VTI 12000 + VXUS 6000 + BND 2000 are included; SPAXX (1000) is excluded cash.
CSV_TEXT = textwrap.dedent("""\
    Account Name: My Brokerage
    Account Number: Z12345678

    Symbol,Description,Quantity,Last Price,Current Value,Total Cost Basis,Total Gain/Loss Dollar,Percentage Of Account
    VTI,Vanguard Total Stock Market ETF,50,240.00,$12000.00,$10000.00,$2000.00,57.14
    VXUS,Vanguard Total International ETF,100,60.00,$6000.00,$5500.00,$500.00,28.57
    BND,Vanguard Total Bond Market ETF,40,50.00,$2000.00,$2100.00,-$100.00,9.52
    SPAXX,Fidelity Government Cash Reserves,1000,1.00,$1000.00,,,4.76
    Account Total,,,,$21000.00,,,$100.00
""")


@pytest.fixture
def csv_bytes() -> bytes:
    return CSV_TEXT.encode()


@pytest.fixture
def config() -> AllocationConfig:
    return AllocationConfig(
        direct_mappings={"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"},
        exclusions=["SPAXX"],
        default_target_allocations=TargetAllocation(vti=60, vxus=30, bnd=10),
    )


@pytest.fixture
def client(config: AllocationConfig) -> Iterator[TestClient]:
    """TestClient with get_config overridden; use TestClient(app) for the real loader."""
    app.dependency_overrides[get_config] = lambda: config
    yield TestClient(app)
    app.dependency_overrides.clear()
