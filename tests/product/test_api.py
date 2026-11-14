"""HTTP contract tests (docs/product/API_CONTRACT.md)."""
from __future__ import annotations

import csv
import io


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["snapshot"]["id"]


def test_meta_contract(client):
    body = client.get("/api/meta").json()
    for key in ("product", "snapshot", "freshness", "sources", "event_types", "categories", "coverage", "time_semantics", "limitations"):
        assert key in body
    assert body["coverage"]["tracked_organizations"] >= 50


def test_search_empty_query_is_400(client):
    assert client.get("/api/search").status_code == 400
    assert client.get("/api/search?q=%20").status_code == 400


def test_search_returns_organizations_and_coverage_note(client):
    body = client.get("/api/search?q=medtronic").json()
    assert body["results"][0]["key"] == "medtronic"
    assert "not a full FDA applicant registry" in body["coverage"]["note"]
    assert body["took_ms"] >= 0


def test_unknown_organization_is_404(client):
    response = client.get("/api/organizations/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "organization_not_found"


def test_organization_profile_contract(client):
    body = client.get("/api/organizations/medtronic").json()
    assert body["key"] == "medtronic"
    assert body["counts"]["records"] > 0
    assert body["counts"]["by_type"]
    assert body["attribution"]["examples"]
    assert body["coverage"]["sources"]
    assert body["basis"]["rule"]
    assert body["snapshot"]["id"]


def test_events_pagination_and_aggregations(client):
    body = client.get("/api/events?page_size=10").json()
    assert len(body["items"]) == 10
    assert body["total"] > 10
    assert body["total_pages"] >= 2
    assert body["aggregations"]["by_year"]
    assert body["counts"]["records"] == body["total"]


def test_events_filters_are_consistent(client):
    filtered = client.get("/api/events?types=510k&org=medtronic").json()
    assert filtered["total"] > 0
    for item in filtered["items"]:
        assert item["event_type"] == "510k"
        assert item["organization_key"] == "medtronic"


def test_events_invalid_type_is_400(client):
    response = client.get("/api/events?types=not-a-type")
    assert response.status_code == 400


def test_events_page_size_bounds(client):
    assert client.get("/api/events?page_size=5").status_code == 400
    assert client.get("/api/events?page_size=101").status_code == 400


def test_event_detail_by_event_id_and_official_id(client):
    first = client.get("/api/events?page_size=10").json()["items"][0]
    by_event = client.get("/api/events/" + first["event_id"])
    assert by_event.status_code == 200
    assert by_event.json()["event"]["event_id"] == first["event_id"]
    by_official = client.get("/api/events/" + first["official_id"])
    assert by_official.status_code == 200
    assert by_official.json()["event"]["official_id"] == first["official_id"]
    assert client.get("/api/events/NOPE-999").status_code == 404


def test_event_detail_has_provenance_and_raw_fields(client):
    first = client.get("/api/events?page_size=10").json()["items"][0]
    body = client.get("/api/events/" + first["event_id"]).json()
    provenance = body["provenance"]
    assert provenance["official_url"].startswith("https://www.accessdata.fda.gov/")
    assert provenance["raw"]
    assert provenance["official_identifier_label"]


def test_compare_requires_two_organizations(client):
    assert client.get("/api/compare?orgs=medtronic").status_code == 400
    assert client.get("/api/compare").status_code == 400


def test_compare_contract_and_warnings(client):
    body = client.get("/api/compare?orgs=medtronic,ge_healthcare").json()
    assert len(body["organizations"]) == 2
    assert body["window"]["complete_years"]
    assert body["disclaimer"]
    assert body["warnings"], "a comparison of these two should raise coverage or mix warnings"
    for warning in body["warnings"]:
        assert warning["code"] and warning["severity"] in ("info", "warning")
    for side in body["organizations"]:
        assert side["coverage"]["sources"]


def test_compare_unknown_org_is_404(client):
    assert client.get("/api/compare?orgs=medtronic,nope").status_code == 404


def test_coverage_reports_audit_and_manifest(client):
    body = client.get("/api/coverage").json()
    assert body["manifest"]["files"]
    assert body["collection_audit"]["tokens"]
    assert body["attribution_summary"]["pending_review_spellings"] > 0
    assert body["reproduce"]["collect"]


def test_attribution_policy_is_explicit(client):
    body = client.get("/api/attribution").json()
    assert body["policy"]
    assert any("exact" in line.lower() for line in body["policy"])
    assert body["decisions"]


def test_events_csv_matches_the_api_filtered_total(client):
    filtered = client.get("/api/events?org=medtronic&types=510k").json()
    response = client.get("/api/export/events.csv?org=medtronic&types=510k")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["x-medradar-provenance"]
    text = response.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == filtered["total"]
    first = rows[0]
    for column in (
        "event_id",
        "official_id",
        "official_url",
        "event_date",
        "published_at",
        "published_at_status",
        "first_observed_at",
        "event_type",
        "organization_key",
        "applicant_name",
        "attribution_review",
        "snapshot_id",
        "collected_at",
    ):
        assert column in first
    assert first["snapshot_id"]


def test_compare_markdown_export(client):
    response = client.get("/api/export/compare.md?orgs=medtronic,ge_healthcare")
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "# MedRadar comparison report" in body
    assert "Snapshot:" in body
    assert "Counting rule" in body
    assert "accessdata.fda.gov" in body
    assert "not a measure of innovation" in body


def test_organization_markdown_export(client):
    response = client.get("/api/export/organization.md?key=draeger")
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "# MedRadar organization brief: Draeger" in body
    assert "Attribution detail" in body
    assert "accessdata.fda.gov" in body


def test_spa_serves_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_unknown_api_route_is_json_404(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
