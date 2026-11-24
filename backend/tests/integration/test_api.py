"""
Integration tests: real FastAPI app via TestClient, config on a tmp YAML file
injected through the get_store dependency override.
"""

import os
import stat
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_store
from app.main import app
from app.models.config import PALETTE
from app.models.schemas import UploadResponse
from app.services.config_store import ConfigStore
from tests.integration.conftest import LEGACY_CONFIG_YAML

MAX_BYTES = 5 * 1024 * 1024
CATEGORY_NAMES = ["US Stocks", "International", "Bonds"]


def upload(client: TestClient, content: bytes, content_type: str = "text/csv"):
    return client.post("/api/upload", files={"file": ("positions.csv", content, content_type)})


def rebalance_body(
    allocation: dict,
    amount: float = 5000,
    target: Mapping[str, float] | None = None,
) -> dict:
    if target is None:
        target = {"US Stocks": 60, "International": 30, "Bonds": 10}
    return {"investment_amount": amount, "target": target, **allocation}


def summary_category(summary: dict, name: str) -> dict:
    return next(c for c in summary["categories"] if c["name"] == name)


def names(summary: dict) -> list[str]:
    return [c["name"] for c in summary["categories"]]


# --- config -----------------------------------------------------------------


def test_config_summary(client: TestClient):
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"categories", "assignments", "exclusions"}
    assert body["categories"] == [
        {
            "name": "US Stocks",
            "buy_symbol": "VTI",
            "parent": None,
            "target": 60,
            "color": "#2a78d6",
        },
        {
            "name": "International",
            "buy_symbol": "VXUS",
            "parent": None,
            "target": 30,
            "color": "#eb6834",
        },
        {"name": "Bonds", "buy_symbol": "BND", "parent": None, "target": 10, "color": "#1baf7a"},
    ]
    assert body["assignments"] == {
        "VTI": {"US Stocks": 1.0},
        "VXUS": {"International": 1.0},
        "BND": {"Bonds": 1.0},
        "VT": {"US Stocks": 0.6, "International": 0.4},
    }
    assert body["exclusions"] == ["SPAXX"]


def test_legacy_v1_config_is_served_migrated(tmp_path: Path):
    path = tmp_path / "legacy.yaml"
    path.write_text(LEGACY_CONFIG_YAML)
    app.dependency_overrides[get_store] = lambda: ConfigStore(path, path)
    try:
        body = TestClient(app).get("/api/config").json()
    finally:
        app.dependency_overrides.clear()
    assert names(body) == ["VTI", "VXUS", "BND"]
    assert [c["color"] for c in body["categories"]] == list(PALETTE[:3])
    assert [c["target"] for c in body["categories"]] == [60, 30, 10]
    assert body["assignments"]["VTI"] == {"VTI": 1.0}


def test_legacy_v1_config_is_persisted_as_v2_on_first_write(tmp_path: Path):
    path = tmp_path / "legacy.yaml"
    path.write_text(LEGACY_CONFIG_YAML)
    app.dependency_overrides[get_store] = lambda: ConfigStore(path, path)
    try:
        response = TestClient(app).post(
            "/api/categories", json={"name": "Gold", "buy_symbol": "GLD"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    text = path.read_text()
    assert 'version: "2"' in text or "version: '2'" in text
    assert "categories:" in text
    assert "Gold" in text
    assert "primary_symbols" not in text
    assert "default_target_allocations" not in text
    assert "keep me: legacy comment" in text


def test_empty_config_is_served(client: TestClient, config_path: Path, csv_bytes: bytes):
    config_path.write_text('version: "2"\ncategories: {}\n')
    body = client.get("/api/config").json()
    assert body == {"categories": [], "assignments": {}, "exclusions": []}
    allocation = upload(client, csv_bytes).json()["allocation"]
    assert allocation["categories"] == []
    assert allocation["unassigned_value"] == pytest.approx(24000)


# --- categories: create -----------------------------------------------------


def test_create_category(client: TestClient, store: ConfigStore, config_path: Path):
    response = client.post(
        "/api/categories", json={"name": "Real Estate", "buy_symbol": "VNQ", "target": 5}
    )
    assert response.status_code == 201
    body = response.json()
    assert names(body) == [*CATEGORY_NAMES, "Real Estate"]
    # The first palette colour not used by an existing category.
    assert summary_category(body, "Real Estate") == {
        "name": "Real Estate",
        "buy_symbol": "VNQ",
        "target": 5,
        "color": PALETTE[3],
        "parent": None,
    }
    assert "Real Estate" in store.load().categories
    # Persisted with comments intact.
    text = config_path.read_text()
    assert "Real Estate" in text
    assert "keep me: top-of-file comment" in text
    assert "keep me: inline comment" in text
    assert client.get("/api/config").json() == body


def test_create_category_defaults_target_to_null_and_uppercases_symbol(client: TestClient):
    response = client.post("/api/categories", json={"name": "Gold", "buy_symbol": "gld"})
    assert response.status_code == 201
    created = summary_category(response.json(), "Gold")
    assert created["target"] is None
    assert created["buy_symbol"] == "GLD"


@pytest.mark.parametrize("name", ["us stocks", "BONDS"])
def test_create_duplicate_name_conflicts_case_insensitively(client: TestClient, name: str):
    response = client.post("/api/categories", json={"name": name, "buy_symbol": "XYZ"})
    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Excluded", "buy_symbol": "XYZ"},
        {"name": "Gold", "buy_symbol": "not a symbol"},
        {"name": "Gold", "buy_symbol": "GLD", "target": 101},
        {"name": "Gold", "buy_symbol": "GLD", "target": "abc"},
        {"buy_symbol": "GLD"},
    ],
)
def test_create_invalid_category_is_rejected(client: TestClient, payload: dict):
    response = client.post("/api/categories", json=payload)
    assert response.status_code == 422
    assert names(client.get("/api/config").json()) == CATEGORY_NAMES


# --- categories: update -----------------------------------------------------


def test_rename_unicode_category(client: TestClient):
    created = client.post("/api/categories", json={"name": "Obligations é", "buy_symbol": "AGG"})
    assert created.status_code == 201
    response = client.patch("/api/categories/Obligations é", json={"buy_symbol": "BNDX"})
    assert response.status_code == 200
    assert summary_category(response.json(), "Obligations é")["buy_symbol"] == "BNDX"


def test_update_buy_symbol(client: TestClient):
    response = client.patch("/api/categories/Bonds", json={"buy_symbol": "agg"})
    assert response.status_code == 200
    assert summary_category(response.json(), "Bonds")["buy_symbol"] == "AGG"


def test_patch_buy_symbol_null_clears_but_omitted_leaves_unchanged(client: TestClient):
    body = client.patch("/api/categories/Bonds", json={"target": 5}).json()
    assert summary_category(body, "Bonds")["buy_symbol"] == "BND"
    body = client.patch("/api/categories/Bonds", json={"buy_symbol": None}).json()
    assert summary_category(body, "Bonds")["buy_symbol"] is None


def test_patch_target_null_clears_but_omitted_leaves_unchanged(client: TestClient):
    omitted = client.patch("/api/categories/Bonds", json={"buy_symbol": "AGG"})
    assert summary_category(omitted.json(), "Bonds")["target"] == 10
    cleared = client.patch("/api/categories/Bonds", json={"target": None})
    assert cleared.status_code == 200
    assert summary_category(cleared.json(), "Bonds")["target"] is None
    changed = client.patch("/api/categories/Bonds", json={"target": 25.5})
    assert summary_category(changed.json(), "Bonds")["target"] == 25.5


def test_update_unknown_category_is_404(client: TestClient):
    response = client.patch("/api/categories/Nope", json={"target": 5})
    assert response.status_code == 404
    assert "Nope" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"target": 150},
        {"name": "Excluded"},
    ],
)
def test_update_invalid_values_are_rejected(client: TestClient, payload: dict):
    assert client.patch("/api/categories/Bonds", json=payload).status_code == 422


# --- categories: delete -----------------------------------------------------


def test_delete_unused_category(client: TestClient, store: ConfigStore):
    client.post("/api/categories", json={"name": "Gold", "buy_symbol": "GLD"})
    response = client.delete("/api/categories/Gold")
    assert response.status_code == 200
    assert names(response.json()) == CATEGORY_NAMES
    assert "Gold" not in store.load().categories


def test_delete_category_in_use_conflicts_and_lists_symbols(client: TestClient):
    response = client.delete("/api/categories/International")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "VXUS" in detail
    assert "VT" in detail
    assert "International" in names(client.get("/api/config").json())


def test_delete_unknown_category_is_404(client: TestClient):
    assert client.delete("/api/categories/Nope").status_code == 404


# --- assignments ------------------------------------------------------------


def test_assign_single_category(client: TestClient, store: ConfigStore):
    response = client.put("/api/assignments/AAPL", json={"weights": {"US Stocks": 1}})
    assert response.status_code == 200
    assert response.json()["assignments"]["AAPL"] == {"US Stocks": 1.0}
    assert store.load().direct_mappings["AAPL"] == "US Stocks"


def test_assign_multiple_categories_is_fractional(client: TestClient, store: ConfigStore):
    response = client.put(
        "/api/assignments/AAPL", json={"weights": {"US Stocks": 0.6, "Bonds": 0.4}}
    )
    assert response.status_code == 200
    assert response.json()["assignments"]["AAPL"] == pytest.approx({"US Stocks": 0.6, "Bonds": 0.4})
    config = store.load()
    assert "AAPL" not in config.direct_mappings
    assert config.fractional_mappings["AAPL"] == pytest.approx({"US Stocks": 0.6, "Bonds": 0.4})


def test_assign_excluded(client: TestClient, store: ConfigStore):
    response = client.put("/api/assignments/VTI", json={"excluded": True})
    assert response.status_code == 200
    body = response.json()
    assert "VTI" in body["exclusions"]
    assert "VTI" not in body["assignments"]
    config = store.load()
    assert "VTI" not in config.direct_mappings
    assert "VTI" in config.exclusions


@pytest.mark.parametrize("payload", [{"weights": {}}, {}], ids=["empty-weights", "empty-body"])
def test_unassign_removes_symbol_everywhere(client: TestClient, payload: dict):
    for symbol in ("VTI", "VT", "SPAXX"):
        response = client.put(f"/api/assignments/{symbol}", json=payload)
        assert response.status_code == 200
    body = response.json()
    assert "VTI" not in body["assignments"]
    assert "VT" not in body["assignments"]
    assert "SPAXX" not in body["exclusions"]


def test_assign_unknown_category_is_404(client: TestClient):
    response = client.put("/api/assignments/AAPL", json={"weights": {"Nope": 1}})
    assert response.status_code == 404
    assert "Nope" in response.json()["detail"]
    assert "AAPL" not in client.get("/api/config").json()["assignments"]


@pytest.mark.parametrize(
    "payload",
    [
        {"weights": {"US Stocks": 0}},
        {"weights": {"US Stocks": -1, "Bonds": 2}},
        {"weights": {"US Stocks": "lots"}},
        {"excluded": True, "weights": {"US Stocks": 1}},
        {"weights": ["US Stocks"]},
    ],
)
def test_assign_invalid_body_is_422(client: TestClient, payload: dict):
    assert client.put("/api/assignments/AAPL", json=payload).status_code == 422


# --- allocation -------------------------------------------------------------


def test_allocation_regroups_a_snapshot(client: TestClient, csv_bytes: bytes):
    portfolio = upload(client, csv_bytes).json()["portfolio"]
    response = client.post("/api/allocation", json=portfolio)
    assert response.status_code == 200
    body = response.json()
    assert [c["category"] for c in body["categories"]] == CATEGORY_NAMES
    values = {c["category"]: c["current_value"] for c in body["categories"]}
    assert values == pytest.approx({"US Stocks": 12000, "International": 6000, "Bonds": 2000})
    assert body["included_value"] == pytest.approx(20000)
    assert body["excluded_value"] == pytest.approx(1000)
    assert body["unassigned_value"] == pytest.approx(3000)
    assert body["total_value"] == pytest.approx(24000)


def test_allocation_reflects_config_changes(client: TestClient, csv_bytes: bytes):
    portfolio = upload(client, csv_bytes).json()["portfolio"]
    client.put("/api/assignments/AAPL", json={"weights": {"Bonds": 1}})
    body = client.post("/api/allocation", json=portfolio).json()
    assert body["unassigned_value"] == 0
    assert {c["category"]: c["current_value"] for c in body["categories"]}["Bonds"] == (
        pytest.approx(5000)
    )


def test_allocation_invalid_body_is_422(client: TestClient):
    assert client.post("/api/allocation", json={"holdings": "nope"}).status_code == 422
    assert client.post("/api/allocation").status_code == 422


# --- upload -----------------------------------------------------------------


def test_upload_happy_path(client: TestClient, csv_bytes: bytes):
    response = upload(client, csv_bytes)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"portfolio", "allocation"}

    symbols = {h["symbol"] for h in body["portfolio"]["holdings"]}
    assert symbols == {"VTI", "VXUS", "BND", "SPAXX", "AAPL"}

    allocation = body["allocation"]
    values = {c["category"]: c["current_value"] for c in allocation["categories"]}
    assert values == pytest.approx({"US Stocks": 12000, "International": 6000, "Bonds": 2000})
    assert allocation["included_value"] == pytest.approx(20000)
    assert allocation["excluded_value"] == pytest.approx(1000)
    assert allocation["unassigned_value"] == pytest.approx(3000)
    assert allocation["total_value"] == pytest.approx(body["portfolio"]["total_value"])
    assert sum(c["percent_of_included"] for c in allocation["categories"]) == pytest.approx(100)

    UploadResponse.model_validate(body)


def test_upload_too_large(client: TestClient):
    response = upload(client, b"a" * (MAX_BYTES + 1))
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_upload_at_size_limit_is_not_rejected_for_size(client: TestClient):
    # Exactly at the limit passes the size guard and fails later as unparseable.
    assert upload(client, b"a" * MAX_BYTES).status_code == 422


def test_upload_wrong_content_type(client: TestClient):
    response = upload(client, b"\x89PNG", "image/png")
    assert response.status_code == 415


@pytest.mark.parametrize("content", [b"not,a,fidelity\n1,2,3\n", b""], ids=["garbage", "empty"])
def test_upload_unparseable_csv(client: TestClient, content: bytes):
    response = upload(client, content)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_upload_missing_file_field(client: TestClient):
    assert client.post("/api/upload").status_code == 422


# --- rebalance --------------------------------------------------------------


def test_rebalance_happy_path(client: TestClient, csv_bytes: bytes):
    uploaded = upload(client, csv_bytes).json()
    response = client.post("/api/rebalance", json=rebalance_body(uploaded["allocation"]))
    assert response.status_code == 200
    body = response.json()

    assert [r["category"] for r in body["recommendations"]] == CATEGORY_NAMES
    assert [r["symbol"] for r in body["recommendations"]] == ["VTI", "VXUS", "BND"]
    assert body["investment_amount"] == 5000
    buys = [r["buy_amount"] for r in body["recommendations"]]
    assert round(sum(buys) * 100) == 500000
    # New total 25000: targets 15000/7500/2500 vs current 12000/6000/2000.
    assert buys == pytest.approx([3000, 1500, 500])


def test_rebalance_awkward_amount_sums_exactly(client: TestClient, csv_bytes: bytes):
    allocation = upload(client, csv_bytes).json()["allocation"]
    target = {"US Stocks": 33.33, "International": 33.33, "Bonds": 33.34}
    body = rebalance_body(allocation, amount=1000.01, target=target)
    response = client.post("/api/rebalance", json=body)
    assert response.status_code == 200
    buys = [r["buy_amount"] for r in response.json()["recommendations"]]
    assert round(sum(buys) * 100) == 100001


def test_rebalance_unknown_target_category_is_422(client: TestClient, csv_bytes: bytes):
    allocation = upload(client, csv_bytes).json()["allocation"]
    body = rebalance_body(allocation, target={"US Stocks": 50, "Nope": 50})
    response = client.post("/api/rebalance", json=body)
    assert response.status_code == 422
    assert "Nope" in str(response.json()["detail"])


@pytest.mark.parametrize(
    "target",
    [
        {"US Stocks": 50, "International": 30, "Bonds": 10},  # sums to 90
        {"US Stocks": 60, "International": 30, "Bonds": 20},  # sums to 110
        {"US Stocks": 150, "International": -50},  # out of range
        {},
    ],
    ids=["under", "over", "out-of-range", "empty"],
)
def test_rebalance_invalid_targets_are_422(client: TestClient, csv_bytes: bytes, target: dict):
    allocation = upload(client, csv_bytes).json()["allocation"]
    response = client.post("/api/rebalance", json=rebalance_body(allocation, target=target))
    assert response.status_code == 422


@pytest.mark.parametrize("amount", [0, -5])
def test_rebalance_investment_must_be_positive(client: TestClient, csv_bytes: bytes, amount: float):
    allocation = upload(client, csv_bytes).json()["allocation"]
    response = client.post("/api/rebalance", json=rebalance_body(allocation, amount=amount))
    assert response.status_code == 422


def test_rebalance_missing_fields(client: TestClient, csv_bytes: bytes):
    assert client.post("/api/rebalance", json={"investment_amount": 100}).status_code == 422
    # unassigned_value is required, like the rest of the breakdown.
    allocation = upload(client, csv_bytes).json()["allocation"]
    del allocation["unassigned_value"]
    assert client.post("/api/rebalance", json=rebalance_body(allocation)).status_code == 422


def test_rebalance_follows_edited_categories(client: TestClient, csv_bytes: bytes):
    client.post("/api/categories", json={"name": "Gold", "buy_symbol": "GLD"})
    client.put("/api/assignments/AAPL", json={"weights": {"Gold": 1}})
    allocation = upload(client, csv_bytes).json()["allocation"]
    target = {"US Stocks": 50, "International": 20, "Bonds": 10, "Gold": 20}
    response = client.post("/api/rebalance", json=rebalance_body(allocation, 4000, target))
    assert response.status_code == 200
    recs = response.json()["recommendations"]
    assert [r["category"] for r in recs] == [*CATEGORY_NAMES, "Gold"]
    assert recs[-1]["symbol"] == "GLD"
    assert round(sum(r["buy_amount"] for r in recs) * 100) == 400000

    # After a rename, the old name is no longer a valid target key.
    client.patch("/api/categories/Gold", json={"name": "Commodities"})
    assert (
        client.post("/api/rebalance", json=rebalance_body(allocation, 4000, target)).status_code
        == 422
    )


# --- config failures (real loader, no override) -----------------------------


@pytest.fixture
def bad_config_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request) -> TestClient:
    """TestClient whose real get_store fails: missing file or invalid contents."""
    contents = {
        "invalid": "direct_mappings:\n  AAPL: Nope\n",  # unknown category
        "malformed": "direct_mappings: [unclosed\n",  # YAML syntax error
        "not_a_mapping": "- just\n- a list\n",
    }
    path = tmp_path / "config.yaml"
    if request.param != "missing":
        path.write_text(contents[request.param])
    monkeypatch.setenv("CONFIG_PATH", str(path))
    assert not app.dependency_overrides
    return TestClient(app)


@pytest.mark.parametrize(
    "bad_config_client", ["missing", "invalid", "malformed", "not_a_mapping"], indirect=True
)
def test_config_error_returns_500_on_every_endpoint(
    bad_config_client: TestClient, csv_bytes: bytes
):
    c = bad_config_client
    rebalance = rebalance_body(
        {
            "categories": [],
            "included_value": 0,
            "excluded_value": 0,
            "unassigned_value": 0,
            "total_value": 0,
        },
        amount=100,
        target={"US Stocks": 100},
    )
    portfolio = {"holdings": [], "total_value": 0, "total_gain_loss": None}
    responses = [
        c.get("/api/config"),
        upload(c, csv_bytes),
        c.post("/api/allocation", json=portfolio),
        c.post("/api/rebalance", json=rebalance),
        c.post("/api/categories", json={"name": "Gold", "buy_symbol": "GLD"}),
        c.patch("/api/categories/Gold", json={"target": 5}),
        c.delete("/api/categories/Gold"),
        c.put("/api/assignments/AAPL", json={"weights": {}}),
    ]
    for response in responses:
        assert response.status_code == 500, response.request.url
        assert response.json()["detail"].startswith("Config error:")


# --- unwritable config ------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_unwritable_config_file_returns_500_on_mutations(client: TestClient, config_path: Path):
    config_path.chmod(stat.S_IRUSR)
    try:
        responses = [
            client.post("/api/categories", json={"name": "Gold", "buy_symbol": "GLD"}),
            client.patch("/api/categories/Bonds", json={"target": 5}),
            client.put("/api/assignments/AAPL", json={"weights": {"Bonds": 1}}),
        ]
        # Reads still work, and the failed writes changed nothing.
        assert client.get("/api/config").status_code == 200
    finally:
        config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    for response in responses:
        assert response.status_code == 500
        assert response.json()["detail"].startswith("Could not save config")
    assert names(client.get("/api/config").json()) == CATEGORY_NAMES


# --- nested categories ------------------------------------------------------


@pytest.fixture
def nested(client: TestClient) -> TestClient:
    """CONFIG_YAML plus a parent "Stocks" holding US Stocks and International."""
    assert client.post("/api/categories", json={"name": "Stocks", "target": 70}).status_code == 201
    for name in ("US Stocks", "International"):
        assert client.patch(f"/api/categories/{name}", json={"parent": "Stocks"}).status_code == 200
    return client


def test_nested_summary_has_no_colour_or_buy_symbol_for_parents(nested: TestClient):
    body = nested.get("/api/config").json()
    assert names(body) == [*CATEGORY_NAMES, "Stocks"]  # config order
    assert summary_category(body, "Stocks") == {
        "name": "Stocks",
        "parent": None,
        "target": 70,
        "buy_symbol": None,
        "color": None,
    }
    child = summary_category(body, "US Stocks")
    assert child["parent"] == "Stocks" and child["color"] == "#2a78d6"


def test_category_nesting_over_http(client: TestClient, config_path: Path):
    created = client.post("/api/categories", json={"name": "Stocks"})  # symbol optional
    assert created.status_code == 201
    created = client.post(
        "/api/categories", json={"name": "Gold", "buy_symbol": "GLD", "parent": "Stocks"}
    )
    assert created.status_code == 201
    assert summary_category(created.json(), "Gold")["parent"] == "Stocks"
    # PATCH: omitted leaves the parent alone, null moves to top level.
    body = client.patch("/api/categories/Gold", json={"target": 50}).json()
    assert summary_category(body, "Gold")["parent"] == "Stocks"
    body = client.patch("/api/categories/Gold", json={"parent": None}).json()
    assert summary_category(body, "Gold")["parent"] is None
    # A category holding securities cannot become a parent.
    before = config_path.read_bytes()
    assert client.patch("/api/categories/Gold", json={"parent": "Bonds"}).status_code == 409
    body = {"name": "Sub", "parent": "Bonds"}
    assert client.post("/api/categories", json=body).status_code == 409
    assert config_path.read_bytes() == before


def test_deleting_a_parent_moves_its_children_up(nested: TestClient):
    response = nested.delete("/api/categories/Stocks")
    assert response.status_code == 200
    assert summary_category(response.json(), "US Stocks")["parent"] is None


def test_assigning_onto_a_parent_is_422(nested: TestClient, config_path: Path):
    before = config_path.read_bytes()
    response = nested.put("/api/assignments/AAPL", json={"weights": {"Stocks": 1}})
    assert response.status_code == 422
    assert config_path.read_bytes() == before


def test_parent_names_are_not_rebalance_targets(nested: TestClient, csv_bytes: bytes):
    allocation = upload(nested, csv_bytes).json()["allocation"]
    assert [c["category"] for c in allocation["categories"]] == CATEGORY_NAMES  # leaves only
    ok = nested.post("/api/rebalance", json=rebalance_body(allocation))
    assert ok.status_code == 200
    bad = rebalance_body(allocation, target={"Stocks": 90, "Bonds": 10})
    assert nested.post("/api/rebalance", json=bad).status_code == 422


def test_cycle_in_hand_edited_config_is_500(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "config.yaml"
    path.write_text('version: "2"\ncategories:\n  A: {parent: B}\n  B: {parent: A}\n')
    monkeypatch.setenv("CONFIG_PATH", str(path))
    assert not app.dependency_overrides
    response = TestClient(app).get("/api/config")
    assert response.status_code == 500
    assert response.json()["detail"].startswith("Config error:")


# --- round trip -------------------------------------------------------------


def test_upload_response_feeds_rebalance(client: TestClient, csv_bytes: bytes):
    uploaded = upload(client, csv_bytes).json()
    # The upload response is the rebalance body's allocation, unchanged.
    response = client.post("/api/rebalance", json=rebalance_body(uploaded["allocation"], 2500))
    assert response.status_code == 200
    result = response.json()
    assert result["total_buy_amount"] == pytest.approx(2500)
    assert all(r["buy_amount"] >= 0 for r in result["recommendations"])


def test_assign_then_reallocate_then_rebalance_round_trip(
    client: TestClient, csv_bytes: bytes, config_path: Path
):
    uploaded = upload(client, csv_bytes).json()
    portfolio = uploaded["portfolio"]
    assert uploaded["allocation"]["unassigned_value"] == pytest.approx(3000)

    # Assign the unassigned holding; the config file changes on disk.
    before = config_path.read_text()
    assigned = client.put("/api/assignments/AAPL", json={"weights": {"International": 1}})
    assert assigned.status_code == 200
    text = config_path.read_text()
    assert text != before
    assert "AAPL" in text
    assert "keep me: top-of-file comment" in text
    assert 'version: "2"' in text or "version: '2'" in text

    # Re-group the same snapshot: AAPL moved from unassigned into International.
    allocation = client.post("/api/allocation", json=portfolio).json()
    assert allocation["unassigned_value"] == 0
    values = {c["category"]: c["current_value"] for c in allocation["categories"]}
    assert values["International"] == pytest.approx(9000)
    assert allocation["included_value"] == pytest.approx(23000)

    # The fresh allocation feeds the rebalance.
    response = client.post("/api/rebalance", json=rebalance_body(allocation, amount=3333.33))
    assert response.status_code == 200
    result = response.json()
    assert round(result["total_buy_amount"] * 100) == 333333
    assert round(sum(r["buy_amount"] for r in result["recommendations"]) * 100) == 333333

    # International is in use until its symbols are reassigned.
    assert client.delete("/api/categories/International").status_code == 409
    for symbol in ("VXUS", "VT", "AAPL"):
        client.put(f"/api/assignments/{symbol}", json={"weights": {"Bonds": 1}})
    deleted = client.delete("/api/categories/International")
    assert deleted.status_code == 200
    assert names(deleted.json()) == ["US Stocks", "Bonds"]
