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


# --- QUALITY-001 ---------------------------------------------------------------------------

def test_a_historical_public_time_view_answers_200_instead_of_500(client: TestClient):
    """Bug A: every dated public-time request raised TypeError and leaked the signature."""
    response = client.get("/api/radar/technology-map", params={
        "mode": "public", "at": "2020-01-01T00:00:00Z", "companies": "philips",
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reconstructed"] is True
    assert payload["topics"] == [], "nothing was public in 2020: an empty view, not an error"
    knowledge = client.get("/api/radar/technology-map", params={
        "mode": "knowledge", "at": "2020-01-01T00:00:00Z", "companies": "philips",
    })
    assert knowledge.status_code == 200
    assert knowledge.json()["topics"] == []


def test_the_map_sends_the_exact_node_id_and_the_node_endpoint_accepts_it(client: TestClient):
    """Bug B: the UI split the id and 404'd. The API must be usable with what it sends."""
    payload = client.get("/api/radar/technology-map", params={"companies": "philips"}).json()
    rows = [row for branch in payload["topics"] for company in branch["companies"]
            for row in company["evidence"]]
    assert rows
    row = rows[0]
    assert row["record_node_id"] == row["record_node"]
    assert row["record_node_id"].startswith("obs:")
    found = client.get("/api/radar/graph/node", params={
        "node_type": row["record_node_type"], "node_id": row["record_node_id"],
    })
    assert found.status_code == 200, found.text
    stripped = client.get("/api/radar/graph/node", params={
        "node_type": row["record_node_type"],
        "node_id": row["record_node_id"].split(":", 1)[1],
    })
    assert stripped.status_code == 404


def test_no_regulatory_product_is_reported_as_a_capability(client: TestClient):
    payload = client.get("/api/radar/technology-map", params={"companies": "philips"}).json()
    products = [product for branch in payload["topics"] for company in branch["companies"]
                for product in company["products"]]
    assert products
    for product in products:
        assert all(cap["basis"] != "regulatory_record_topic"
                   for cap in product["reported_capabilities"])
        if product.get("regulatory_evidence"):
            assert product["reported_capabilities"] == []
    for branch in payload["topics"]:
        for company in branch["companies"]:
            assert company["reported_capabilities_total"] == sum(
                len(product["reported_capabilities"]) for product in company["products"])


def test_the_public_500_never_returns_the_internal_exception(monkeypatch):
    """P2-04: a 500 must not print a Python signature to a public client."""
    from medradar.product import api as product_api

    def explode(*_args, **_kwargs):
        raise TypeError("normalize_moment() missing 1 required positional argument: 'field'")

    monkeypatch.setattr("medradar.radar.api.system_status", explode)
    monkeypatch.setenv("MEDRADAR_ALPHA_USER", "")
    app_client = None
    try:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            radar_dir = Path(tmp) / "radar"
            _seed(radar_dir)
            web_dir = Path(tmp) / "web"
            web_dir.mkdir()
            (web_dir / "index.html").write_text("<html></html>", encoding="utf-8")
            app = product_api.create_app(data_dir=Path(tmp) / "data", web_dir=web_dir,
                                         radar_dir=radar_dir)
            app_client = TestClient(app, raise_server_exceptions=False)
            response = app_client.get("/api/radar/health")
    finally:
        if app_client is not None:
            app_client.close()
    assert response.status_code == 500
    body = response.text
    assert "normalize_moment" not in body and "TypeError" not in body
    payload = response.json()["error"]
    assert payload["code"] == "internal_error"
    assert payload["message"] == "The server could not complete this request."
    assert "reference" in (payload.get("hint") or "")


def test_admission_scopes_separate_new_publications_from_the_archive(client: TestClient, tmp_path: Path):
    from medradar.radar.engine import apply_admissions

    ledger = ObservationLedger(tmp_path / "radar" / "radar.db", create=False)
    try:
        applied = apply_admissions(ledger, limit=100)
    finally:
        ledger.close()
    assert applied >= 2
    latest = client.get("/api/radar/feed", params={"scope": "latest"}).json()
    archive = client.get("/api/radar/feed", params={"scope": "archive"}).json()
    review = client.get("/api/radar/feed", params={"scope": "review"}).json()
    assert latest["scope"] == "latest"
    assert latest["views"]["archive"] >= latest["views"]["latest"]
    assert latest["total"] <= archive["total"]
    assert review["total"] == latest["views"]["review"]
    if latest["items"]:
        assert latest["items"][0]["admission"]["tier"] == "HIGH_RELEVANCE"


def test_the_asset_cache_policy_makes_a_hashed_bundle_reusable():
    """A 557 KB bundle re-downloaded on every navigation was part of the measured cold start."""
    from medradar.radar.alpha_gate import cache_policy

    assert b"immutable" in cache_policy("/assets/index-DDZb-qTC.js")
    assert b"max-age=31536000" in cache_policy("/assets/index-iIx0b16V.css")
    assert cache_policy("/radar") == b"no-store"
    assert cache_policy("/api/radar/feed") == b"no-store"
    assert b"no-store" not in cache_policy("/favicon.svg")


def test_map_pagination_can_walk_a_branch_to_its_end(client: TestClient):
    first = client.get("/api/radar/technology-map", params={
        "companies": "philips", "max_evidence": 1, "max_products": 1,
    }).json()
    branch = next((branch for branch in first["topics"] if branch["companies"]), None)
    assert branch is not None
    company = branch["companies"][0]
    assert company["evidence_offset"] == 0
    if company["evidence_total"] > 1:
        assert company["has_more_evidence"] is True
        second = client.get("/api/radar/technology-map", params={
            "companies": "philips", "topic_id": branch["topic_id"],
            "max_evidence": 1, "max_products": 1, "evidence_offset": 1,
        }).json()
        following = second["topics"][0]["companies"][0]
        assert following["evidence_offset"] == 1
        assert following["evidence"][0]["record_node_id"] != company["evidence"][0]["record_node_id"]


def test_graph_changes_reports_offset_and_has_more(client: TestClient):
    payload = client.get("/api/radar/graph/changes", params={
        "earlier": "2020-01-01T00:00:00Z", "limit": 1,
    }).json()
    assert payload["list_limit"] == 1
    assert payload["list_offset"] == 0
    assert "has_more" in payload
    assert len(payload["added"]) <= 1
    second = client.get("/api/radar/graph/changes", params={
        "earlier": "2020-01-01T00:00:00Z", "limit": 1, "offset": 1,
    }).json()
    assert second["list_offset"] == 1
