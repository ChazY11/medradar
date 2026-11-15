"""P0-B: owner at event time, not "exclude predecessor names".

The previous implementation treated every record whose applicant string looked like an acquired
predecessor as a pre-acquisition record, regardless of its event date. That is wrong: the applicant
name is fixed while ownership changes. These tests pin the corrected semantics across the data model,
the filters, the comparison, the exports and the API.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medradar.product.attribution import ownership as ownership_module
from medradar.product.dataset import OWNERSHIP_BASES, RETIRED_OWNERSHIP_BASES


def test_owner_at_event_time_depends_on_the_event_date(dataset) -> None:
    # A Covidien entity existed independently before 2015-01-26 and was part of Medtronic after it.
    before = ownership_module.historical_owner("medtronic", "COVIDIEN LP", "2012-05-01")
    after = ownership_module.historical_owner("medtronic", "COVIDIEN LP", "2020-05-01")
    assert before.state == "verified" and before.reason == "verified_predecessor"
    assert "Covidien" in (before.display or "")
    assert after.state == "verified" and after.reason == "verified_current_group"
    assert after.organization_key == "medtronic"


def test_same_applicant_string_is_classified_by_date_in_the_dataset(dataset) -> None:
    fields = [
        event
        for event in dataset.events
        if event.organization_key == "medtronic" and "COVIDIEN" in event.applicant_name.upper() and event.event_date
    ]
    before = [event for event in fields if event.event_date < "2015-01-26"]
    after = [event for event in fields if event.event_date >= "2015-01-26"]
    assert before and after
    assert all(event.historical_owner_state == "verified" for event in before + after)
    assert all(event.historical_owner_reason == "verified_predecessor" for event in before)
    assert all(event.historical_owner_reason == "verified_current_group" for event in after)
    # the same spelling appears on both sides, and the classification still differs
    shared = {event.applicant_name for event in before} & {event.applicant_name for event in after}
    assert shared, "the fixture must contain a spelling filed on both sides of the acquisition"


def test_unknown_when_no_event_date_no_effective_date_or_no_relation() -> None:
    no_date = ownership_module.historical_owner("medtronic", "COVIDIEN LP", None)
    assert no_date.state == "unknown" and no_date.reason == "no_event_date"
    # REL-0002 records current subsidiary ownership with no verified effective date.
    no_effective = ownership_module.historical_owner("medtronic", "MEDTRONIC VASCULAR", "2020-01-01")
    assert no_effective.state == "unknown" and no_effective.reason == "no_effective_date"
    no_relation = ownership_module.historical_owner("medtronic", "Medtronic, Inc.", "2020-01-01")
    assert no_relation.state == "unknown" and no_relation.reason == "no_relation"
    unresolved_relation = ownership_module.historical_owner("medtronic", "TYCO HEALTHCARE", "2010-01-01")
    assert unresolved_relation.state == "unknown"


def test_spin_off_boundary_is_respected(dataset) -> None:
    before = ownership_module.historical_owner("ge_healthcare", "GE MEDICAL SYSTEMS", "2019-01-01")
    after = ownership_module.historical_owner("ge_healthcare", "GE MEDICAL SYSTEMS", "2024-01-01")
    assert before.reason == "verified_predecessor"
    assert "General Electric" in (before.display or "")
    assert after.reason == "verified_current_group"
    counts = dataset.org_stats["ge_healthcare"].counts
    assert counts["historical_verified_predecessor"] > 0
    assert counts["historical_verified_current_group"] > 0


def test_owner_counts_partition_the_attributed_records(dataset) -> None:
    total_current = total_predecessor = total_unknown = 0
    for stats in dataset.org_stats.values():
        counts = stats.counts
        records = counts["records"]
        assert counts["historical_verified_current_group"] + counts["historical_verified_predecessor"] + counts["historical_unknown"] == records
        total_current += counts["historical_verified_current_group"]
        total_predecessor += counts["historical_verified_predecessor"]
        total_unknown += counts["historical_unknown"]
    assert total_current + total_predecessor + total_unknown == dataset.global_counts["records"]
    assert total_unknown > 0, "most mappings have no verified ownership relation: that must be visible"


def test_historical_basis_counts_only_verified_current_group(dataset) -> None:
    filtered = dataset.filter_events(org_keys=["ge_healthcare"], basis="historical_owner_verified")
    assert filtered
    assert all(event.historical_owner_reason == "verified_current_group" for event in filtered)
    assert len(filtered) == dataset.org_stats["ge_healthcare"].counts["historical_verified_current_group"]


def test_retired_basis_is_refused_with_a_hint(dataset) -> None:
    assert "original_registrant" in RETIRED_OWNERSHIP_BASES
    with pytest.raises(ValueError) as error:
        dataset.filter_events(org_keys=["medtronic"], basis="original_registrant")
    assert "historical_owner_verified" in str(error.value)
    assert "not the same as restoring the owner at event time" in str(error.value)
    assert set(OWNERSHIP_BASES) == {"current_group", "historical_owner_verified"}


def test_api_refuses_the_retired_basis(client) -> None:
    response = client.get("/api/events?basis=original_registrant")
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "retired_basis"
    assert "historical_owner_verified" in body["hint"]


def test_api_and_profile_agree_on_the_historical_basis(client) -> None:
    profile = client.get("/api/organizations/ge_healthcare").json()
    record_level = profile["ownership"]["record_level"]
    events = client.get("/api/organizations/ge_healthcare/events?basis=historical_owner_verified&page_size=10").json()
    assert events["total"] == record_level["verified_current_group"]
    assert events["ownership_basis"] == "historical_owner_verified"
    assert all(item["attribution"]["historical_owner"]["reason"] == "verified_current_group" for item in events["items"])
    assert record_level["unknown"] == profile["counts"]["historical_unknown"]


def test_comparison_reports_what_the_historical_basis_excluded(dataset) -> None:
    from medradar.product.compare import build_compare

    current = build_compare(dataset, ["medtronic", "ge_healthcare"])
    historical = build_compare(dataset, ["medtronic", "ge_healthcare"], basis="historical_owner_verified")
    medtronic_hist = next(side for side in historical["organizations"] if side["key"] == "medtronic")
    medtronic_current = next(side for side in current["organizations"] if side["key"] == "medtronic")
    assert medtronic_hist["counts"]["records"] < medtronic_current["counts"]["records"]
    assert historical["basis_excluded_totals"]["excluded_unknown_owner"] > 0
    assert historical["basis_excluded_totals"]["excluded_predecessor_owner"] > 0
    codes = [warning["code"] for warning in historical["warnings"]]
    assert "historical_owner_basis_excludes_records" in codes
    assert historical["comparability"]["ownership_basis"] == "historical_owner_verified"
    for side in historical["organizations"]:
        assert side["historical_ownership"]["unknown"] == 0, "the basis filter leaves no unknown-owner records in the counted set"
        assert side["historical_ownership"]["excluded_unknown_owner"] >= 0


def test_all_unknown_organization_is_not_reported_as_zero_activity(dataset) -> None:
    from medradar.product.compare import build_compare

    # Abbott has no verified ownership relation, so every record's owner at event time is UNKNOWN.
    payload = build_compare(dataset, ["abbott", "medtronic"], basis="historical_owner_verified")
    abbott = next(side for side in payload["organizations"] if side["key"] == "abbott")
    assert abbott["counts"]["records"] == 0
    assert abbott["historical_ownership"]["excluded_unknown_owner"] > 0
    assert payload["basis_excluded_totals"]["excluded_unknown_owner"] > 0


def test_csv_and_markdown_exports_carry_the_same_semantics(client, dataset) -> None:
    csv_response = client.get("/api/export/events.csv?org=medtronic&basis=historical_owner_verified")
    assert csv_response.status_code == 200
    text = csv_response.text.replace("\ufeff", "")
    header = text.splitlines()[0]
    for column in (
        "historical_owner_state",
        "historical_owner_reason",
        "historical_owner",
        "historical_owner_relation",
        "historical_owner_effective_from",
        "ownership_basis",
    ):
        assert column in header
    provenance = json.loads(base64.urlsafe_b64decode(csv_response.headers["X-MedRadar-Provenance"]))
    assert provenance["filters"]["basis"] == "historical_owner_verified"

    markdown = client.get("/api/export/compare.md?orgs=medtronic,ge_healthcare&basis=historical_owner_verified").text
    assert "Ownership basis: historical_owner_verified" in markdown
    assert "Excluded by the historical-owner basis" in markdown
    assert "Owner at event time" in markdown
    assert "unknown is reported, not treated as zero" in markdown.lower() or "not treated as zero" in markdown.lower()

    brief = client.get("/api/export/organization.md?key=medtronic").text
    assert "Owner at event time" in brief
    assert "UNKNOWN" in brief
