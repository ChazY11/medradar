"""The identity-review ledger: append-only, evidence-gated, isolated, and unreachable from public routes."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medradar.product.review.store import (
    ReviewError,
    ReviewStore,
    agent_authority,
    human_authority,
    HumanAuthorityUnavailable,
)

EVIDENCE = [{"evidence_type": "jurisdiction_filing", "url": "https://example.org/filing", "title": "test filing"}]


def _store(tmp_path: Path) -> ReviewStore:
    return ReviewStore(tmp_path / "review.db")


def test_agent_cannot_claim_human_review(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(HumanAuthorityUnavailable):
        store.append(
            applicant_name="Some Applicant",
            action="approve",
            status="human_reviewed",
            organization_key="medtronic",
            reviewer="agent:lead",
            authority=agent_authority("agent:lead"),
            evidence=EVIDENCE,
        )
    assert store.effective() == {}, "a refused decision must not be written"


def test_human_authority_cannot_be_constructed(tmp_path: Path) -> None:
    with pytest.raises(HumanAuthorityUnavailable):
        human_authority(label="alice", method="self_asserted")
    store = _store(tmp_path)
    with pytest.raises(ReviewError):
        store.append(
            applicant_name="Some Applicant",
            action="approve",
            status="evidence_verified",
            organization_key="medtronic",
            reviewer="alice",
            authority="human",  # type: ignore[arg-type]
            evidence=EVIDENCE,
        )


def test_evidence_verified_requires_evidence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ReviewError):
        store.append(
            applicant_name="Some Applicant",
            action="approve",
            status="evidence_verified",
            organization_key="medtronic",
            reviewer="alice",
            authority=agent_authority("alice"),
            evidence=[],
        )
    decision = store.append(
        applicant_name="Some Applicant",
        action="approve",
        status="evidence_verified",
        organization_key="medtronic",
        reviewer="alice",
        authority=agent_authority("alice"),
        evidence=EVIDENCE,
    )
    assert decision.evidence


def test_ledger_is_append_only_at_the_database_level(tmp_path: Path) -> None:
    store = _store(tmp_path)
    decision = store.append(
        applicant_name="Some Applicant",
        action="approve",
        status="evidence_verified",
        organization_key="medtronic",
        reviewer="alice",
        authority=agent_authority("alice"),
        evidence=EVIDENCE,
    )
    connection = sqlite3.connect(str(store.path))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("UPDATE review_decisions SET status = 'human_reviewed' WHERE decision_uid = ?", (decision.decision_uid,))
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute("DELETE FROM review_decisions WHERE decision_uid = ?", (decision.decision_uid,))
    finally:
        connection.close()


def test_revocation_restores_the_previous_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.append(
        applicant_name="Some Applicant",
        action="reject",
        status="rejected",
        organization_key=None,
        reviewer="alice",
        authority=agent_authority("alice"),
        note="not this company",
    )
    assert "some applicant" in store.effective()
    store.append(
        applicant_name="Some Applicant",
        action="revoke",
        status="unresolved",
        organization_key=None,
        reviewer="alice",
        authority=agent_authority("alice"),
        supersedes_uid=first.decision_uid,
        note="withdrawn",
    )
    assert store.effective() == {}
    history = store.history("Some Applicant")
    assert len(history) == 2
    assert history[0].revoked is True


def test_decision_changes_only_the_target_organization(tmp_path: Path) -> None:
    from medradar.product.dataset import load_dataset
    from medradar.product.review.service import attribution_impact

    from tests.product.conftest import NO_REVIEW_LEDGER

    baseline = load_dataset(review_db=NO_REVIEW_LEDGER)
    store = _store(tmp_path)
    applicant = "Abbott Vascular-Cardiac Therapies dba Guidant Corporation"
    store.append(
        applicant_name=applicant,
        action="approve",
        status="rule_verified",
        organization_key="abbott",
        reviewer="agent:lead",
        authority=agent_authority("agent:lead"),
        basis="name_identity_v1",
        note="the string names Abbott Vascular",
    )
    current = load_dataset(review_db=store.path)
    impact = attribution_impact(baseline, current)
    assert len(impact["changed_organizations"]) == 1
    changed = impact["changed_organizations"][0]
    assert changed["organization_key"] == "abbott"
    assert changed["records_delta"] > 0
    assert impact["unchanged_organizations"] >= 50
    decision, _ = current.registry.decide(applicant)
    assert decision is not None and decision.organization_key == "abbott"


def test_overlay_marks_unresolved_strings(tmp_path: Path) -> None:
    from medradar.product.dataset import load_dataset

    store = _store(tmp_path)
    applicant = "Olympus Terumo Biomaterials Corporation"
    store.append(
        applicant_name=applicant,
        action="unresolved",
        status="unresolved",
        organization_key=None,
        reviewer="alice",
        authority=agent_authority("alice"),
        note="joint venture",
    )
    dataset = load_dataset(review_db=store.path)
    from medradar.product.review.store import normalise_applicant

    assert normalise_applicant(applicant) in dataset.registry.unresolved_strings
    decision, rejection = dataset.registry.decide(applicant)
    assert decision is None and rejection is None


def test_queue_is_ordered_by_affected_records_and_hides_verified(tmp_path: Path) -> None:
    from medradar.product.dataset import load_dataset
    from medradar.product.review.service import build_queue

    from tests.product.conftest import NO_REVIEW_LEDGER

    dataset = load_dataset(review_db=NO_REVIEW_LEDGER)
    store = _store(tmp_path)
    queue = build_queue(dataset, store, page_size=10)
    counts = [row["record_count"] for row in queue["items"]]
    assert counts == sorted(counts, reverse=True)
    assert queue["total"] > 0
    assert all(row["status"] not in ("evidence_verified", "human_reviewed") for row in queue["items"])


def test_case_carries_evidence_history_and_risk_flags(tmp_path: Path) -> None:
    from medradar.product.dataset import load_dataset
    from medradar.product.review.service import build_case

    from tests.product.conftest import NO_REVIEW_LEDGER

    dataset = load_dataset(review_db=NO_REVIEW_LEDGER)
    store = _store(tmp_path)
    case = build_case(dataset, store, "Abbott Vascular-Cardiac Therapies dba Guidant Corporation")
    assert case["record_count"] > 0
    assert case["sample_records"] and case["sample_records"][0]["official_url"]
    assert {flag["code"] for flag in case["risk_flags"]} >= {"unmatched_string", "multi_org_scope"}
    assert case["history"] == []


def test_public_application_has_no_review_write_routes(tmp_path: Path) -> None:
    from medradar.product.api import create_app

    client = TestClient(create_app())
    assert client.get("/api/review/queue").status_code == 404
    assert client.post("/api/review/decisions", json={}).status_code in (404, 405)


def test_admin_application_requires_a_token(tmp_path: Path) -> None:
    from medradar.product.review.admin import create_admin_app

    app = create_admin_app(review_db=tmp_path / "review.db", token="secret-token")
    client = TestClient(app)
    assert client.get("/api/review/queue").status_code == 401
    assert client.get("/api/review/queue", headers={"X-MedRadar-Review-Token": "wrong"}).status_code == 401
    assert client.get("/api/review/queue", headers={"X-MedRadar-Review-Token": "secret-token"}).status_code == 200
    assert client.post("/api/review/decisions", json={}).status_code == 401
    # the public read routes still work through the admin application
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/metrics").status_code == 200


def test_admin_decision_is_visible_and_revocable(tmp_path: Path) -> None:
    from medradar.product.review.admin import create_admin_app

    app = create_admin_app(review_db=tmp_path / "review.db", token="secret-token")
    client = TestClient(app)
    headers = {"X-MedRadar-Review-Token": "secret-token"}
    applicant = "Abbott Vascular-Cardiac Therapies dba Guidant Corporation"
    response = client.post(
        "/api/review/decisions",
        headers=headers,
        json={
            "applicant_name": applicant,
            "action": "approve",
            "status": "rule_verified",
            "organization_key": "abbott",
            "basis": "name_identity_v1",
            "reviewer": "alice",
            "note": "names Abbott Vascular",
        },
    )
    assert response.status_code == 200, response.text
    uid = response.json()["decision"]["decision_uid"]
    case = client.get("/api/review/case/" + applicant, headers=headers).json()
    assert case["current"]["organization_key"] == "abbott"
    impact = client.get("/api/review/impact", headers=headers).json()
    assert impact["changed_organizations"]
    revoke = client.post("/api/review/decisions/" + uid + "/revoke", headers=headers, json={"reviewer": "alice"})
    assert revoke.status_code == 200
    case_after = client.get("/api/review/case/" + applicant, headers=headers).json()
    assert case_after["current"]["organization_key"] is None
    assert len(case_after["history"]) == 2
