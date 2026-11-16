"""The read-only radar API: honest 503s, real filters, and the two time modes over HTTP."""

from __future__ import annotations

import unittest
from pathlib import Path

try:  # the repository's `medradar selftest` runs under unittest without pytest installed
    import pytest
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("pytest is not installed; run these tests with pytest")

try:  # an optional extra: the offline selftest environment has no fastapi
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover
    raise unittest.SkipTest("fastapi is not installed (optional 'product' extra)")

from medradar.product.api import create_app
from medradar.radar.graph import TechnologyGraph
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MAPPING_VERSION, RawRecord
from medradar.radar.taxonomy import load_taxonomy
from medradar.tkg import TKGStore

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "radar"


def _seed(radar_dir: Path) -> None:
    radar_dir.mkdir(parents=True, exist_ok=True)
    taxonomy = load_taxonomy(str(CONFIG_DIR))
    from medradar.radar.classify import RuleMapper

    mapper = RuleMapper(taxonomy)
    ledger = ObservationLedger(radar_dir / "radar.db")
    ledger.ensure_source("openfda_device", label="FDA", adapter_version="a1", cadence_hours=24)
    ledger.ensure_source("philips_official", label="Philips", adapter_version="a1", cadence_hours=12)
    fda = RawRecord(
        source="openfda_device", source_record_id="510k:K240001", official_identifier="K240001",
        record_type="regulatory_record", title="INTELLIVUE MX800 PATIENT MONITOR",
        url="https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID=K240001",
        event_at="2026-03-04", event_at_precision="date",
        payload={"k_number": "K240001", "device_name": "INTELLIVUE MX800 PATIENT MONITOR",
                 "applicant": "Philips Medical Systems", "product_code": "MHX",
                 "decision_date": "2026-03-04"},
        text="INTELLIVUE MX800 PATIENT MONITOR",
        extra={"organization_hint": "Philips Medical Systems",
               "organization_role": "regulatory_applicant", "product_codes": ["MHX"],
               "product_hint": "INTELLIVUE MX800 PATIENT MONITOR", "product_identifier": "K240001"},
    )
    ledger.record_observation(fda, mapper.map(fda), run_id="r1", adapter_version="a1",
                              mapping_version=MAPPING_VERSION)
    press = RawRecord(
        source="philips_official", source_record_id="philips:2026:modular",
        official_identifier="https://www.philips.com/press/modular",
        record_type="press_release", title="Philips introduces modular monitor with SpO2",
        url="https://www.philips.com/press/modular",
        published_at="2026-04-01T09:00:00+00:00", published_at_precision="datetime",
        payload={"title": "Philips introduces modular monitor with SpO2"},
        text="Philips introduces modular monitor with SpO2",
        extra={"organization_hint": "Royal Philips", "organization_role": "official_publisher",
               "publisher_hint": "Royal Philips", "product_hint": "Modular Monitor 9000"},
    )
    ledger.record_observation(press, mapper.map(press), run_id="r2", adapter_version="a1",
                              mapping_version=MAPPING_VERSION)
    graph = TechnologyGraph(TKGStore(str(radar_dir / "graph.db")), taxonomy)
    graph.materialize(ledger, limit=50, log=lambda _m: None)
    graph.store.close()
    ledger.close()


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    radar_dir = tmp_path / "radar"
    _seed(radar_dir)
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    app = create_app(data_dir=tmp_path / "data", web_dir=web_dir, radar_dir=radar_dir)
    return TestClient(app)


@pytest.fixture()
def empty_client(tmp_path: Path) -> TestClient:
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    app = create_app(data_dir=tmp_path / "data", web_dir=web_dir,
                     radar_dir=tmp_path / "no-radar-here")
    return TestClient(app)


def test_without_a_ledger_the_api_says_so_instead_of_returning_an_empty_feed(empty_client: TestClient):
    response = empty_client.get("/api/radar/feed")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "radar_not_configured"
    assert "does not invent data" in detail["message"]


def test_health_reports_not_configured_rather_than_green(empty_client: TestClient):
    response = empty_client.get("/api/radar/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["state"] == "not_configured"


def test_meta_lists_every_source_including_the_blocked_one(client: TestClient):
    payload = client.get("/api/radar/meta").json()
    sources = {source["source_id"]: source for source in payload["sources"]}
    assert sources["gehealthcare_official"]["enabled"] is False
    assert sources["gehealthcare_official"]["access"] == "BLOCKED"


def test_the_feed_carries_the_standard_event_fields(client: TestClient):
    payload = client.get("/api/radar/feed", params={"limit": 10}).json()
    assert payload["total"] == 2
    item = payload["items"][0]
    for field in ("observation_id", "source", "official_identifier", "title", "source_url",
                  "record_type", "first_observed_at", "content_hash", "version",
                  "organization_candidates", "technology_topics", "evidence_references",
                  "processing_state", "change_state", "discovery_phase"):
        assert field in item, field
    assert item["evidence_references"][0]["url"]


def test_the_feed_filters_by_company_and_by_change_state(client: TestClient):
    filtered = client.get("/api/radar/feed", params={"organization": "philips"}).json()
    assert filtered["total"] == 2
    other = client.get("/api/radar/feed", params={"organization": "draeger"}).json()
    assert other["total"] == 0
    new_only = client.get("/api/radar/feed", params={"change_state": "UPDATED"}).json()
    assert new_only["total"] == 0
    bad = client.get("/api/radar/feed", params={"change_state": "MAYBE"})
    assert bad.status_code == 400


def test_the_technology_map_is_served_with_its_time_semantics(client: TestClient):
    payload = client.get("/api/radar/technology-map",
                         params={"companies": "philips,draeger"}).json()
    assert payload["mode"] == "public_time_reconstruction" or payload["mode"] == "knowledge_time"
    assert payload["time_semantics"]["statement"]
    assert payload["counts"]["edges"] > 0
    topic_ids = {topic["topic_id"] for topic in payload["topics"]}
    assert topic_ids, "the seeded FDA record must create a technology branch"
    branch = next(topic for topic in payload["topics"])
    assert branch["companies"]
    assert branch["companies"][0]["evidence"][0]["source_url"]


def test_the_map_supports_a_knowledge_time_cutoff(client: TestClient):
    payload = client.get("/api/radar/technology-map",
                         params={"mode": "knowledge", "at": "2000-01-01T00:00:00Z"}).json()
    assert payload["mode"] == "knowledge_time"
    assert payload["topics"] == [], "a 2000 knowledge view cannot contain 2026 observations"


def test_compare_states_no_evidence_is_not_no_technology(client: TestClient):
    payload = client.get("/api/radar/compare", params={"companies": "philips,draeger"}).json()
    assert "does not mean the company lacks" in payload["no_evidence_means"]
    assert payload["not_comparable_warning"]
    states = {(row["topic_id"], cell["organization_id"]): cell for row in payload["rows"]
              for cell in row["cells"]}
    philips_cells = [cell for (topic, org), cell in states.items() if org == "philips"]
    assert any(cell["state"] == "EVIDENCE_PRESENT" for cell in philips_cells)
    draeger_cells = [cell for (topic, org), cell in states.items() if org == "draeger"]
    assert all(cell["state"] == "NO_EVIDENCE_FOUND" for cell in draeger_cells)
    assert all("not a claim" in cell["statement"] or "No evidence found" in cell["statement"]
               for cell in draeger_cells)


def test_intelligence_detail_exposes_versions_and_a_bounded_payload(client: TestClient):
    feed = client.get("/api/radar/feed", params={"limit": 1}).json()
    observation_id = feed["items"][0]["observation_id"]
    payload = client.get(f"/api/radar/intelligence/{observation_id}").json()
    assert payload["versions"] and payload["versions"][0]["payload_keys"]
    assert payload["changes"]
    missing = client.get("/api/radar/intelligence/does-not-exist")
    assert missing.status_code == 404


def test_notices_count_new_observations_since_a_timestamp(client: TestClient):
    payload = client.get("/api/radar/notices", params={"since": "2000-01-01T00:00:00Z"}).json()
    assert payload["new_count"] == 2
    assert payload["items"]


def test_graph_summary_and_changes_are_available(client: TestClient):
    summary = client.get("/api/radar/graph/summary").json()
    assert summary["nodes"] > 0 and summary["edges"] > 0
    changes = client.get("/api/radar/graph/changes",
                         params={"earlier": "2000-01-01T00:00:00Z"}).json()
    assert changes["counts"]["added"] > 0


def test_graph_node_returns_citations_and_404s_for_a_missing_node(client: TestClient):
    payload = client.get("/api/radar/graph/node",
                         params={"node_type": "company", "node_id": "org:philips"}).json()
    assert payload["node"]
    assert payload["incoming"] or payload["outgoing"]
    missing = client.get("/api/radar/graph/node",
                         params={"node_type": "company", "node_id": "org:nobody"})
    assert missing.status_code == 404


def test_pipeline_endpoint_reports_the_flow_and_the_graph(client: TestClient):
    payload = client.get("/api/radar/pipeline").json()
    assert payload["available"] is True
    assert payload["flow"] == ["ingest", "deduplicate", "classify", "resolve", "link", "publish"]
    assert payload["graph"]["edges"] > 0
