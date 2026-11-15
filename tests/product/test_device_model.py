"""PRODUCT-003 device model: identity, hierarchy, evidence and honest unknowns.

These tests pin the difference between a regulatory record, an application, a device identity and a
product family, and they pin what may NOT be claimed: no device merge from a similar name, no recall
device identity, no predicate relation, no confirmed status without official evidence.
"""
from __future__ import annotations

import base64
import json

import pytest

from medradar.product.device import RELATION_STATUSES, build_index, quality_report
from medradar.product.device.identifiers import (
    APPLICATION_PREFIX,
    DEVICE_PREFIX,
    FAMILY_PREFIX,
    NOT_MODELLED,
    RELATION_TYPES,
)


@pytest.fixture(scope="session")
def index(dataset):
    return dataset.device_index()


def test_identifiers_are_internal_and_prefixed(index) -> None:
    assert len(index.devices) > 20000
    for device in list(index.devices.values())[:200]:
        assert device.device_id.startswith(DEVICE_PREFIX)
        assert not device.device_id.startswith("K")
        assert device.official_id
        assert device.official_id not in device.device_id or ":" in device.device_id
    for application in list(index.applications.values())[:200]:
        assert application.application_id.startswith(APPLICATION_PREFIX)
    for family in list(index.families.values())[:50]:
        assert family.family_id.startswith(FAMILY_PREFIX)


def test_one_device_identity_per_application_and_none_per_recall(index) -> None:
    application_count = sum(1 for app in index.applications.values() if app.kind in ("510k", "pma"))
    assert len(index.devices) == application_count
    assert index.stats["recalls"] > 20000
    # a recall record never becomes a device identity
    assert not any(device.identity_basis not in ("510k_clearance", "pma_approval") for device in index.devices.values())


def test_identity_basis_is_stated(index) -> None:
    for device in list(index.devices.values())[:100]:
        if device.kind == "510k":
            assert device.identity_basis == "510k_clearance"
        else:
            assert device.identity_basis == "pma_approval"


def test_pma_supplements_form_the_official_hierarchy(index) -> None:
    supplement_relations = [relation for relation in index.relations if relation.relation_type == "application_has_supplement"]
    assert supplement_relations
    for relation in supplement_relations:
        parent = index.applications[relation.source_id]
        child = index.applications[relation.target_id]
        assert parent.kind == "pma"
        assert child.kind == "pma_supplement"
        assert parent.pma_number == child.pma_number == relation.evidence[0].value
        assert relation.status == "confirmed"
        assert relation.rule == "same_official_pma_number_v1"
        assert relation.evidence and all(item.official_url for item in relation.evidence)


def test_a_supplement_never_attaches_to_a_different_pma(index) -> None:
    families = list(index.families.values())
    assert families
    for family in families[:50]:
        for version_id in family.version_application_ids:
            version = index.applications[version_id]
            assert version.kind == "pma_supplement"
            assert family.family_id == FAMILY_PREFIX + "pma:" + version.pma_number


def test_family_without_original_is_labelled(index) -> None:
    orphans = [family for family in index.families.values() if not family.original_in_snapshot]
    assert orphans, "the snapshot contains supplement-only PMA numbers"
    for family in orphans[:10]:
        assert family.application_id is None
        assert family.version_application_ids
        assert family.supplement_count == len(family.version_application_ids)


def test_recall_links_come_only_from_the_official_k_number_field(index) -> None:
    relations = [relation for relation in index.relations if relation.relation_type == "recall_references_application"]
    assert relations
    for relation in relations[:500]:
        recall = index.recalls[relation.source_id]
        assert relation.status == "confirmed"
        assert relation.rule == "official_k_numbers_field_v1"
        assert relation.evidence
        assert relation.evidence[0].field == "k_numbers"
        assert relation.evidence[0].value in recall.k_numbers
        assert relation.target_in_snapshot is True
        assert relation.target_id in index.applications


def test_recall_referencing_an_absent_application_is_not_attached(index) -> None:
    # external references are counted, never materialised as an edge to a missing record
    assert index.external_k_references
    for event_id, k_numbers in list(index.external_k_references.items())[:50]:
        for k_number in k_numbers:
            assert k_number not in {app.official_id for app in index.applications.values() if app.kind == "510k"}


def test_unlinked_recalls_are_visible_not_deleted(index) -> None:
    unlinked = index.unlinked_recalls()
    total = index.stats["recalls"]
    assert 0 < len(unlinked) < total
    for recall in unlinked[:50]:
        assert not index.recall_k_references.get(recall.event_id)
        assert recall.official_url.startswith("http")


def test_no_device_merge_from_a_similar_name(index) -> None:
    candidates = [relation for relation in index.relations if relation.relation_type == "candidate_same_device"]
    assert candidates
    for relation in candidates[:200]:
        assert relation.status == "candidate"
        assert relation.rule == "same_applicant_product_code_normalised_device_name_v1"
        # both endpoints remain separate device identities
        assert relation.source_id in index.devices
        assert relation.target_id in index.devices
        assert relation.source_id != relation.target_id
        assert relation.score is not None
    confirmed = [relation for relation in index.relations if relation.relation_type == "candidate_same_device" and relation.status == "confirmed"]
    assert confirmed == [], "a name-similarity relation must never be confirmed"


def test_candidate_relations_are_never_confirmed(index) -> None:
    for relation in index.relations:
        if relation.relation_type.startswith("candidate_"):
            assert relation.status == "candidate", relation.relation_id
    for relation in index.relations:
        expected = RELATION_TYPES.get(relation.relation_type)
        assert expected is not None
        assert relation.status == expected


def test_every_confirmed_relation_carries_official_evidence(index) -> None:
    confirmed = [relation for relation in index.relations if relation.status == "confirmed"]
    assert confirmed
    for relation in confirmed:
        assert relation.evidence
        for item in relation.evidence:
            assert item.field
            assert item.kind in ("official_identifier", "record_field")
        assert relation.snapshot_id == index.snapshot_id


def test_predicate_relations_are_not_invented(index) -> None:
    assert "application_references_predicate" in NOT_MODELLED
    assert all(relation.relation_type != "application_references_predicate" for relation in index.relations)


def test_quality_report_is_honest_about_verification(index) -> None:
    report = quality_report(index)
    levels = report["verification_levels"]
    assert levels["human_review"]["value"] == 0
    assert levels["accuracy_estimate"]["state"] == "unknown"
    assert levels["accuracy_estimate"]["value"] is None
    assert report["candidates"]["statement"]
    assert report["recalls"]["without_any_official_reference"] > 0
    assert report["conflicts_and_ambiguity"]["product_code_mismatch_between_recall_and_referenced_application"] >= 0
    assert report["limitations"]
    assert report["snapshot_id"] == index.snapshot_id


def test_index_is_deterministic(dataset) -> None:
    first = build_index(dataset)
    second = build_index(dataset)
    assert set(first.devices) == set(second.devices)
    assert set(first.families) == set(second.families)
    assert len(first.relations) == len(second.relations)
    assert {relation.relation_id for relation in first.relations} == {relation.relation_id for relation in second.relations}


def test_device_counts_include_official_references_to_its_application(index) -> None:
    with_recalls = [device for device in index.devices.values() if index.device_stats[device.device_id]["recalls"] > 0]
    assert len(with_recalls) > 100
    device = with_recalls[0]
    stats = index.device_stats[device.device_id]
    assert stats["confirmed_relations"] >= stats["recalls"]
    relations = index.relations_for(device.device_id)
    assert any(relation.relation_type == "recall_references_application" for relation in relations)
    assert len([r for r in relations if r.status == "confirmed"]) == stats["confirmed_relations"]


# ---------------------------------------------------------------- API surface

def test_devices_api_filters_and_pagination(client) -> None:
    everything = client.get("/api/devices?page_size=5").json()
    assert everything["total"] > 20000
    assert len(everything["items"]) == 5
    assert everything["total_pages"] > 1
    org = client.get("/api/devices?org=medtronic&page_size=100").json()
    assert org["total"] > 0
    assert all(item["organization_key"] == "medtronic" for item in org["items"])
    pma = client.get("/api/devices?pathway=pma&page_size=100").json()
    assert pma["total"] == 574
    assert all(item["kind"] == "pma" for item in pma["items"])
    by_code = client.get("/api/devices?product_code=JAA&page_size=100").json()
    assert by_code["total"] > 0
    assert all(item["product_code"] == "JAA" for item in by_code["items"])
    no_relation = client.get("/api/devices?relation=none&page_size=50").json()
    assert no_relation["total"] > 0
    assert all(item["counts"]["confirmed_relations"] == 0 and item["counts"]["candidate_relations"] == 0 for item in no_relation["items"])


def test_devices_api_searches_official_numbers(client) -> None:
    family = client.get("/api/device-families/family:pma:P980016").json()
    official = family["family"]["application_id"].split(":")[-1]
    found = client.get("/api/devices?q=" + official + "&page_size=10").json()
    assert found["total"] >= 1
    assert any(item["official_id"] == official for item in found["items"])


def test_device_detail_reports_identity_disclosures_and_evidence(client) -> None:
    listing = client.get("/api/devices?pathway=pma&page_size=5&sort=relevance").json()
    device = listing["items"][0]
    detail = client.get("/api/devices/" + device["device_id"]).json()
    assert detail["device"]["device_id"] == device["device_id"]
    assert detail["identity"]["basis"]
    assert detail["identity"]["what_this_page_represents"]
    assert "not officially" not in detail["identity"]["not_impersonating_fda"].lower()
    assert detail["identity"]["not_impersonating_fda"]
    assert detail["applicant"]["verification"] in {
        "proposed",
        "rule_verified",
        "evidence_verified",
        "human_reviewed",
        "rejected",
        "unresolved",
        "unattributed",
    }
    assert detail["relations"]["confirmed"]
    assert all(item["evidence"] for item in detail["relations"]["confirmed"])
    assert detail["evidence"]
    assert detail["disclosures"]["predicate_relations"]
    for family in detail.get("versions") or []:
        assert family["kind"] == "pma_supplement"


def test_device_detail_404_and_hint(client) -> None:
    response = client.get("/api/devices/device:nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "device_not_found"
    assert "K123456" in response.json()["error"]["hint"]


def test_family_endpoint_states_the_basis_and_missing_original(client) -> None:
    payload = client.get("/api/device-families/family:pma:P980016").json()
    assert payload["family"]["family_id"] == "family:pma:P980016"
    assert payload["versions_count"] == payload["family"]["supplement_count"]
    assert payload["disclosures"]["basis"]
    assert payload["disclosures"]["not_a_commercial_brand_family"]
    assert payload["family"]["original_in_snapshot"] is True


def test_unlinked_endpoint_lists_reasons(client) -> None:
    payload = client.get("/api/devices/unlinked?page_size=10").json()
    assert payload["total"] > 0
    assert payload["items"]
    for item in payload["items"]:
        assert item["reason"]
        assert item["official_url"].startswith("http")


def test_devices_csv_matches_the_explorer(client) -> None:
    query = "org=medtronic&pathway=pma"
    explorer = client.get("/api/devices?" + query + "&page_size=100").json()
    response = client.get("/api/export/devices.csv?" + query)
    assert response.status_code == 200
    text = response.text.replace("\ufeff", "")
    rows = [line for line in text.splitlines() if line.strip()]
    assert len(rows) - 1 == explorer["total"]
    header = rows[0]
    for column in ("device_id", "identity_basis", "official_id", "organization_key", "confirmed_relations", "candidate_relations", "family_id"):
        assert column in header
    assert response.headers["X-MedRadar-Records"] == str(explorer["total"])
    provenance = json.loads(base64.urlsafe_b64decode(response.headers["X-MedRadar-Provenance"]))
    assert provenance["filters"]["org"] == "medtronic"


def test_device_markdown_brief_states_identity_and_relations(client) -> None:
    detail = client.get("/api/devices/device:openfda_pma:P980016").json()
    response = client.get("/api/export/device.md?device=device:openfda_pma:P980016")
    assert response.status_code == 200
    text = response.text
    assert detail["device"]["official_id"] in text
    assert "Device identity" in text
    assert "Confirmed relations" in text
    assert "Candidate relations (not established)" in text
    assert "Regulatory timeline" in text
    assert "not causation" in text
