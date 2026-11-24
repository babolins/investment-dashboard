"""
Integration tests: real FastAPI app via TestClient, config injected through
the get_config dependency override.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import UploadResponse

MAX_BYTES = 5 * 1024 * 1024


def upload(client: TestClient, content: bytes, content_type: str = "text/csv"):
    return client.post("/api/upload", files={"file": ("positions.csv", content, content_type)})


def rebalance_body(upload_json: dict, amount: float = 5000, target=(60, 30, 10)) -> dict:
    return {
        "investment_amount": amount,
        "target": dict(zip(("vti", "vxus", "bnd"), target, strict=True)),
        **upload_json["allocation"],
    }


# --- health / config --------------------------------------------------------


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_summary(client: TestClient):
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["direct_mappings"] == {"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"}
    assert body["exclusions"] == ["SPAXX"]
    assert body["primary_symbols"] == {"VTI": "VTI", "VXUS": "VXUS", "BND": "BND"}
    assert body["default_target"] == {"vti": 60, "vxus": 30, "bnd": 10}


# --- upload -----------------------------------------------------------------


def test_upload_happy_path(client: TestClient, csv_bytes: bytes):
    response = upload(client, csv_bytes)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"portfolio", "allocation"}

    assert {h["symbol"] for h in body["portfolio"]["holdings"]} == {"VTI", "VXUS", "BND", "SPAXX"}

    allocation = body["allocation"]
    values = {b["bucket"]: b["current_value"] for b in allocation["buckets"]}
    assert values == pytest.approx({"VTI": 12000, "VXUS": 6000, "BND": 2000})
    assert allocation["included_value"] == pytest.approx(20000)
    assert allocation["excluded_value"] == pytest.approx(1000)
    assert sum(b["percent_of_included"] for b in allocation["buckets"]) == pytest.approx(100)

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
    response = client.post("/api/rebalance", json=rebalance_body(uploaded))
    assert response.status_code == 200
    body = response.json()

    assert [r["bucket"] for r in body["recommendations"]] == ["VTI", "VXUS", "BND"]
    assert [r["symbol"] for r in body["recommendations"]] == ["VTI", "VXUS", "BND"]
    assert body["investment_amount"] == 5000
    buys = [r["buy_amount"] for r in body["recommendations"]]
    assert round(sum(buys) * 100) == 500000
    # New total 25000: targets 15000/7500/2500 vs current 12000/6000/2000.
    assert buys == pytest.approx([3000, 1500, 500])


def test_rebalance_awkward_amount_sums_exactly(client: TestClient, csv_bytes: bytes):
    uploaded = upload(client, csv_bytes).json()
    body = rebalance_body(uploaded, amount=1000.01, target=(33.33, 33.33, 33.34))
    response = client.post("/api/rebalance", json=body)
    assert response.status_code == 200
    buys = [r["buy_amount"] for r in response.json()["recommendations"]]
    assert round(sum(buys) * 100) == 100001


def test_rebalance_targets_must_sum_to_100(client: TestClient, csv_bytes: bytes):
    uploaded = upload(client, csv_bytes).json()
    response = client.post("/api/rebalance", json=rebalance_body(uploaded, target=(50, 30, 10)))
    assert response.status_code == 422


@pytest.mark.parametrize("amount", [0, -5])
def test_rebalance_investment_must_be_positive(client: TestClient, csv_bytes: bytes, amount: float):
    uploaded = upload(client, csv_bytes).json()
    response = client.post("/api/rebalance", json=rebalance_body(uploaded, amount=amount))
    assert response.status_code == 422


def test_rebalance_unknown_bucket_in_body(client: TestClient, csv_bytes: bytes):
    body = rebalance_body(upload(client, csv_bytes).json())
    body["buckets"][0]["bucket"] = "FOO"
    assert client.post("/api/rebalance", json=body).status_code == 422


def test_rebalance_missing_fields(client: TestClient):
    assert client.post("/api/rebalance", json={"investment_amount": 100}).status_code == 422


# --- config failures (real loader, no override) -----------------------------


@pytest.fixture
def bad_config_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request) -> TestClient:
    """TestClient whose real get_config fails: missing file or invalid contents."""
    contents = {
        "invalid": "direct_mappings:\n  AAPL: SPY\n",  # unknown bucket
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
    body = {
        "investment_amount": 100,
        "target": {"vti": 60, "vxus": 30, "bnd": 10},
        "buckets": [],
        "included_value": 0,
        "excluded_value": 0,
        "total_value": 0,
    }
    responses = [
        bad_config_client.get("/api/config"),
        upload(bad_config_client, csv_bytes),
        bad_config_client.post("/api/rebalance", json=body),
    ]
    for response in responses:
        assert response.status_code == 500
        assert response.json()["detail"].startswith("Config error:")


# --- round trip -------------------------------------------------------------


def test_upload_response_feeds_rebalance(client: TestClient, csv_bytes: bytes):
    uploaded = upload(client, csv_bytes).json()
    # The upload response is the rebalance body's allocation, unchanged.
    response = client.post("/api/rebalance", json=rebalance_body(uploaded, amount=2500))
    assert response.status_code == 200
    result = response.json()
    assert result["total_buy_amount"] == pytest.approx(2500)
    assert all(r["buy_amount"] >= 0 for r in result["recommendations"])
