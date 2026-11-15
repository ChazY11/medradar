"""Historical ownership: current group, original applicant and verified history are separate."""
from __future__ import annotations

from medradar.product.attribution import ownership as ownership_module


def test_relations_have_explicit_status_and_evidence() -> None:
    registry = ownership_module.ownership()
    assert registry.relations
    verified = [relation for relation in registry.relations if relation.verified]
    unresolved = [relation for relation in registry.relations if not relation.verified]
    assert verified and unresolved, "this release records both verified and unresolved relations"
    for relation in verified:
        assert relation.evidence, "a verified relation must carry evidence"
        assert all(item.url for item in relation.evidence)
        assert relation.reviewer_kind in ("human", "agent")
    for relation in unresolved:
        assert relation.evidence == (), "an unresolved relation must not pretend to have evidence"


def test_current_group_summary_states_its_basis(dataset) -> None:
    summary = ownership_module.organization_ownership_summary("medtronic", events=dataset.org_events("medtronic"))
    assert summary["verified_relation_count"] >= 1
    assert "CURRENT GROUP" in summary["current_group_policy"]
    assert summary["concepts"]["original_applicant"] and summary["concepts"]["historical_owner"]
    assert summary["historical_split"], "the 2015 Covidien acquisition has an effective date"


def test_historical_split_counts_before_and_after_the_effective_date(dataset) -> None:
    summary = ownership_module.organization_ownership_summary("ge_healthcare", events=dataset.org_events("ge_healthcare"))
    rows = [row for row in summary["historical_split"] if row["relation_id"] == "REL-0004"]
    assert rows, "the GE HealthCare spin-off relation is verified"
    row = rows[0]
    assert row["effective_from"] == "2023-01-03"
    assert row["records_before_effective_date"] > 0
    assert row["records_before_effective_date"] + row["records_on_or_after_effective_date"] <= dataset.org_stats["ge_healthcare"].counts["records"]


def test_predecessor_applicants_are_detected() -> None:
    assert ownership_module.is_predecessor_applicant("medtronic", "COVIDIEN LLC") is True
    assert ownership_module.is_predecessor_applicant("medtronic", "MEDTRONIC VASCULAR") is False
    assert ownership_module.is_predecessor_applicant("ge_healthcare", "GE MEDICAL SYSTEMS") is True


def test_original_registrant_basis_excludes_predecessor_records(dataset) -> None:
    current = dataset.filter_events(org_keys=["ge_healthcare"])
    original = dataset.filter_events(org_keys=["ge_healthcare"], basis="original_registrant")
    assert len(original) <= len(current)
    assert all(not event.attribution_is_predecessor for event in original)


def test_unresolved_relation_is_not_used_as_evidence() -> None:
    registry = ownership_module.ownership()
    unresolved = [relation for relation in registry.relations if not relation.verified]
    for relation in unresolved:
        assert registry.verified_for(relation.organization_key, relation.patterns[0]) == []
