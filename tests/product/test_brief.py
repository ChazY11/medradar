"""PRODUCT-004: the Intelligence Brief must be reproducible from the dataset.

These tests do not mock the measurement path: they compare the brief with the same
``filter_events`` / ``build_compare`` calls the rest of the product uses, so a brief number that
drifts from the screen fails here.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from medradar.product import brief as brief_module
from medradar.product.compare import build_compare
from medradar.product.dataset import EVENT_TYPE_ORDER, load_dataset

DATA_DIR = Path(__file__).resolve().parents[2] / "medradar" / "product" / "snapshot"


def _all_findings(brief: dict) -> list[dict]:
    return list(brief.get("findings") or [])


def test_company_brief_counts_match_the_filter(dataset):
    built = brief_module.build_brief(dataset, mode="company", org="medtronic", years=5)
    assert built["schema"] == "medradar.brief.v1"
    assert built["kind"] == "company"
    assert built["scope"]["from"] == "2021-01-01"
    assert built["scope"]["to"] == "2025-12-31"
    assert built["scope"]["complete_years"] == ["2021", "2022", "2023", "2024", "2025"]

    events = dataset.filter_events(org_keys=["medtronic"], date_from="2021-01-01", date_to="2025-12-31")
    assert built["summary"]["records"] == len(events)
    assert sum(row["count"] for row in built["summary"]["by_type"]) == len(events)
    assert sum(row["count"] for row in built["activity"]["by_type"]) == len(events)


def test_company_brief_answers_every_question_with_evidence(dataset):
    built = brief_module.build_brief(dataset, mode="company", org="medtronic", years=5)
    findings = _all_findings(built)
    assert findings, "Medtronic 2021-2025 must produce at least one finding"
    for finding in findings:
        assert finding["basis"]["rule"]
        assert finding["basis"]["rules_version"] == brief_module.RULES_VERSION
        assert finding["cannot_conclude"]["en"] and finding["cannot_conclude"]["zh"]
        assert finding["statement"]["en"] and finding["statement"]["zh"]
        assert isinstance(finding["evidence"]["record_count"], int)
        # Every cited record must be a real official record with a URL.
        for record in finding["evidence"]["records"]:
            assert record["official_id"]
            assert record["official_url"].startswith("https://")
        if finding["drilldown"].get("url"):
            assert finding["drilldown"]["url"].startswith("/")
    assert any(finding["id"] == "pathway_concentration" for finding in findings)
    assert any(finding["id"] == "specialty_not_stated" for finding in findings)


def test_finding_rules_are_recomputable(dataset):
    built = brief_module.build_brief(dataset, mode="company", org="medtronic", years=5)
    concentration = next(finding for finding in built["findings"] if finding["id"] == "pathway_concentration")
    inputs = concentration["basis"]["inputs"]
    assert inputs["total_records"] == built["summary"]["records"]
    assert inputs["top_type"] == "pma_supplement"
    # The stated share is the exact count/total, not a rounded guess.
    assert inputs["top_share"] == pytest.approx(inputs["by_type"]["pma_supplement"] / inputs["total_records"], rel=1e-6)
    assert concentration["evidence"]["records"], "the finding cites the records that produced it"
    assert all(record["event_type"] == "pma_supplement" for record in concentration["evidence"]["records"])


def test_company_markdown_and_csv_agree_with_the_payload(dataset):
    built = brief_module.build_brief(dataset, mode="company", org="medtronic", years=5)
    markdown = brief_module.brief_markdown(built)
    assert "# Medtronic" in markdown
    assert "Evidence-backed findings" in markdown
    assert "Questions this cannot answer" in markdown
    assert f"{built['summary']['records']:,}" in markdown

    csv_body = brief_module.brief_evidence_csv(dataset, built)
    rows = list(csv.DictReader(io.StringIO(csv_body)))
    window_rows = [row for row in rows if row["section"] == "window_records"]
    assert len(window_rows) == built["summary"]["records"]
    assert all(row["official_url"].startswith("https://") for row in window_rows)
    assert all(row["snapshot_id"] == built["scope"]["snapshot"]["id"] for row in window_rows)
    finding_rows = [row for row in rows if row["section"].startswith("finding:")]
    assert finding_rows, "the appendix includes the records cited by findings"


def test_brief_changes_never_invent_an_update(dataset):
    built = brief_module.build_brief(dataset, mode="company", org="medtronic", years=5)
    changes = built["changes"]
    assert changes["state"] in ("not_configured", "no_changes", "available", "unavailable")
    if changes["state"] in ("not_configured", "no_changes"):
        assert changes["items"] == []
        assert changes["note"]["en"]


def test_compare_brief_matches_the_compare_computation(dataset):
    built = brief_module.build_brief(dataset, mode="compare", orgs=["ge_healthcare", "philips"], years=5)
    comparison = build_compare(dataset, ["ge_healthcare", "philips"], "2021-01-01", "2025-12-31")
    expected = {side["key"]: side["counts"]["records"] for side in comparison["organizations"]}
    assert {side["key"]: side["counts"]["records"] for side in built["sides"]} == expected
    assert built["coverage_assessment"]["symmetric"] == comparison["comparability"]["coverage_symmetric"]
    for metric in built["metrics"]:
        for value in metric["values"]:
            assert value["value"] >= 0
            assert value["key"] in expected
    total_metric = next(metric for metric in built["metrics"] if metric["id"] == "records_total")
    assert {value["key"]: value["value"] for value in total_metric["values"]} == expected
    pathway_metric = next(metric for metric in built["metrics"] if metric["id"] == "type.510k")
    for side in comparison["organizations"]:
        value = next(value for value in pathway_metric["values"] if value["key"] == side["key"])
        assert value["value"] == side["counts_by_type"]["510k"]


def test_explain_reproduces_brief_metric_and_records(dataset):
    built = brief_module.build_brief(dataset, mode="compare", orgs=["ge_healthcare", "philips"], years=5)
    metric = next(item for item in built["metrics"] if item["id"] == "type.pma_supplement")
    explained = brief_module.explain_metric(
        dataset, metric=metric["id"], org_keys=["ge_healthcare", "philips"], years=5,
    )
    for value in metric["values"]:
        side = next(side for side in explained["sides"] if side["key"] == value["key"])
        assert side["count"] == value["value"]
        assert side["drilldown"].startswith("/events?")
        for record in side["records"]:
            assert record["event_type"] == "pma_supplement"
    assert explained["denominator"]["value"] == sum(side["count"] for side in explained["sides"])


def test_explain_product_code_filter_is_exact(dataset):
    explained = brief_module.explain_metric(
        dataset, metric="product_code.NIK", org_keys=["medtronic"], years=5,
    )
    side = explained["sides"][0]
    expected = [
        event for event in dataset.filter_events(
            org_keys=["medtronic"], date_from="2021-01-01", date_to="2025-12-31", product_code="NIK",
        )
    ]
    assert side["count"] == len(expected)
    assert all(record["product_code"] == "NIK" for record in side["records"])
    assert "product_code=NIK" in side["drilldown"]


def test_device_brief_keeps_official_and_candidate_relations_apart(dataset):
    built = brief_module.build_brief(dataset, mode="device", device="P980016")
    assert built["kind"] == "device"
    assert built["device"]["official_id"] == "P980016"
    assert built["supplements_count"] == len(built["versions"])
    assert not built["related_recalls"]["confirmed"]
    assert any(finding["id"] == "no_confirmed_recall_link" for finding in built["findings"])
    # A supplement is not a new device: the finding must say so.
    supplement_finding = next(finding for finding in built["findings"] if finding["id"] == "pma_supplement_history")
    assert "not a new device" in supplement_finding["cannot_conclude"]["en"]


def test_organization_profile_exposes_classification_names(dataset):
    profile = dataset.organization_profile("medtronic")
    rows = profile["technology"]["product_families"]["rows"]
    assert rows
    top = rows[0]
    assert top["official_name"]
    assert top["product_code"] == top["product_code"].upper()
    assert top["records"] > 0


def test_brief_api_contract(client):
    response = client.get("/api/brief?mode=company&org=medtronic&years=5")
    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "medradar.brief.v1"
    assert body["kind"] == "company"

    compare = client.get("/api/brief?mode=compare&orgs=ge_healthcare,philips&years=5")
    assert compare.status_code == 200
    assert compare.json()["kind"] == "compare"

    device = client.get("/api/brief?mode=device&device=P980016")
    assert device.status_code == 200
    assert device.json()["kind"] == "device"

    assert client.get("/api/brief?mode=company").status_code == 400
    assert client.get("/api/brief?mode=company&org=nope&years=5").status_code == 404
    assert client.get("/api/brief?mode=device&device=NOPE").status_code == 404
    assert client.get("/api/brief?mode=company&org=medtronic&years=7").status_code == 400
    assert client.get("/api/brief?mode=company&org=medtronic&from=2024-01-01").status_code == 400


def test_brief_explain_and_exports_api(client):
    explain = client.get("/api/brief/explain?metric=type.recall&orgs=ge_healthcare,philips&years=5")
    assert explain.status_code == 200
    assert explain.json()["metric"] == "type.recall"
    assert explain.json()["sides"]

    markdown = client.get("/api/export/brief.md?mode=company&org=medtronic&years=5")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Evidence-backed findings" in markdown.text
    assert "attachment" in markdown.headers["content-disposition"]

    chinese = client.get("/api/export/brief.md?mode=company&org=medtronic&years=5&lang=zh")
    assert chinese.status_code == 200
    assert "研究问题" in chinese.text
    assert "有证据支持的发现" in chinese.text

    appendix = client.get("/api/export/brief-evidence.csv?mode=company&org=medtronic&years=5")
    assert appendix.status_code == 200
    assert appendix.headers["content-type"].startswith("text/csv")
    assert "official_url" in appendix.text
    assert appendix.headers["x-medradar-records"].isdigit()


def test_events_product_code_filter_api(client, dataset):
    expected = len(dataset.filter_events(org_keys=["medtronic"], product_code="NIK", date_from="2021-01-01", date_to="2025-12-31"))
    response = client.get(
        "/api/events?org=medtronic&product_code=NIK&from=2021-01-01&to=2025-12-31&page_size=10"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == expected
    assert all(item["product_code"] == "NIK" for item in body["items"])


def test_meta_exposes_whole_snapshot_aggregation(client):
    body = client.get("/api/meta").json()
    assert "global_aggregations" in body
    years = body["global_aggregations"]["by_year"]
    assert years
    # Sparse years: undated records are not invented into a year bucket.
    assert sum(row["total"] for row in years) + body["global_aggregations"]["undated_records"] == body["coverage"]["attributed_records"]
