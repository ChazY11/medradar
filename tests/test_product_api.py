"""HTTP-level tests for the MedRadar 2.0 product API."""
from __future__ import annotations

import pytest

from medradar.product import store

pytest.importorskip("fastapi", reason="install the product extra: pip install -e .[web]")
pytest.importorskip("httpx", reason="install the dev extra for TestClient")

pytestmark = pytest.mark.skipif(
    not store.dataset_signature().get("exists"),
    reason="research store data/medradar.sqlite not built (run: python -m medradar run)",
)

from fastapi.testclient import TestClient  # noqa: E402

from medradar.web.app import app  # noqa: E402

client = TestClient(app)


def test_health_and_meta():
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert "X-Response-Time-ms" in health.headers

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    payload = meta.json()
    assert payload["product"]["version"]
    assert len(payload["featured_companies"]) == 5
    assert len(payload["domains"]) == 8
    assert payload["analyst_examples"]
    assert payload["sources"]
    assert payload["limitations"]


def test_companies_endpoints():
    listing = client.get("/api/companies")
    assert listing.status_code == 200
    payload = listing.json()
    assert len(payload["featured"]) == 5

    profile = client.get("/api/companies/mindray", params={"years": 5})
    assert profile.status_code == 200
    data = profile.json()
    assert data["info"]["name_zh"] == "迈瑞医疗"
    assert data["claims"]
    assert data["milestones"]
    assert data["entity_review"][0]["status"] == "PENDING_HUMAN_REVIEW"

    missing = client.get("/api/companies/does_not_exist")
    assert missing.status_code == 404
    assert missing.json()["error"] == "not_found"


def test_compare_validates_and_returns_warnings():
    response = client.get(
        "/api/compare",
        params={"companies": "medtronic,philips", "metric": "approvals", "years": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["companies"]) == 2
    assert data["warnings"]

    too_few = client.get("/api/compare", params={"companies": "medtronic"})
    assert too_few.status_code == 400
    unknown = client.get("/api/compare", params={"companies": "medtronic,nope"})
    assert unknown.status_code == 400
    bad_metric = client.get("/api/compare", params={"companies": "medtronic,philips", "metric": "nope"})
    assert bad_metric.status_code == 400


def test_radar_endpoints():
    radar = client.get("/api/radar", params={"years": 3})
    assert radar.status_code == 200
    data = radar.json()
    assert len(data["domains"]) == 8
    assert data["catalog"]["domains"]

    track = client.get("/api/radar/respiratory", params={"years": 10})
    assert track.status_code == 200
    assert track.json()["track"]["name_zh"] == "呼吸与麻醉"

    missing = client.get("/api/radar/not_a_track")
    assert missing.status_code == 404


def test_evidence_endpoints_and_claim_recompute():
    listing = client.get("/api/evidence", params={"companies": "draeger", "limit": 5})
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] > 0
    item = data["items"][0]
    assert item["company_match"] == "exact_alias"

    detail = client.get(f"/api/evidence/{item['event_id']}")
    assert detail.status_code == 200
    assert detail.json()["event"]["event_id"] == item["event_id"]

    profile = client.get("/api/companies/philips", params={"years": 5}).json()
    claim = profile["claims"][0]
    recomputed = client.post("/api/evidence/claim", json=claim["evidence_params"])
    assert recomputed.status_code == 200
    assert recomputed.json()["recent_events"]

    assert client.get("/api/evidence/nope").status_code == 404
    assert client.post("/api/evidence/claim", json={}).status_code == 400


def test_lab_endpoints():
    lab = client.get("/api/lab")
    assert lab.status_code == 200
    studies = lab.json()["studies"]
    assert len(studies) >= 4
    by_id = {study["id"]: study for study in studies}
    s027 = by_id["S-027-early-signal-5firms"]
    assert s027["artifacts"]["human_review"]["packets"] == 69
    assert s027["artifacts"]["human_review"]["human_labels_recorded"] == 0
    c43 = by_id["C43-hist-v1"]
    assert len(c43["artifacts"]["five_firm_timeline"]["cases"]) == 5
    assert c43["artifacts"]["provenance"]["merged"] is False

    detail = client.get("/api/lab/C43-hist-v1")
    assert detail.status_code == 200
    assert detail.json()["status_tone"] == "mixed"
    assert client.get("/api/lab/nope").status_code == 404


def test_static_frontend_is_served():
    index_path = __import__("pathlib").Path(__file__).resolve().parents[1] / "web" / "index.html"
    if not index_path.exists():
        pytest.skip("frontend build not present yet")
    index = client.get("/")
    assert index.status_code == 200
    assert "text/html" in index.headers["content-type"]
    assert "MedRadar" in index.text
