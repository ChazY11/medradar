"""P0-A: the actor kind is server-derived and human_reviewed cannot be forged.

The previous implementation accepted reviewer_kind from the request and defaulted it to "human".
These tests pin the fix end to end: the store refuses human review, the service rejects the field,
the CLI refuses the status, imports ignore the field, legacy claims are downgraded without rewriting
history, and the capability is reported honestly.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from medradar.product.review.store import (
    HUMAN_REVIEW_AUTHORITY_AVAILABLE,
    HumanAuthorityUnavailable,
    ReviewError,
    ReviewStore,
    agent_authority,
    human_authority,
)

EVIDENCE = [{"evidence_type": "regulator_record", "url": "https://example.org/record", "title": "record"}]
HEADERS = {"X-MedRadar-Review-Token": "authority-token"}


def _admin(tmp_path: Path) -> TestClient:
    from medradar.product.review.admin import create_admin_app

    return TestClient(create_admin_app(review_db=tmp_path / "review.db", token="authority-token"))


def test_authority_is_server_derived_and_human_is_unavailable() -> None:
    assert HUMAN_REVIEW_AUTHORITY_AVAILABLE is False
    authority = agent_authority("alice", "local_service_token")
    assert authority.kind == "agent"
    with pytest.raises(HumanAuthorityUnavailable):
        human_authority(label="alice", method="self_asserted")
    with pytest.raises(ReviewError):
        agent_authority("alice").__class__(kind="human", method="x", label="alice")


def test_store_refuses_human_reviewed(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.db")
    with pytest.raises(HumanAuthorityUnavailable):
        store.append(
            applicant_name="Some Applicant",
            action="approve",
            status="human_reviewed",
            organization_key="medtronic",
            reviewer="alice",
            authority=agent_authority("alice"),
            evidence=EVIDENCE,
        )
    assert store.all_decisions() == []
    assert store.effective() == {}


def test_api_rejects_self_declared_actor_kind(tmp_path: Path) -> None:
    client = _admin(tmp_path)
    response = client.post(
        "/api/review/decisions",
        headers=HEADERS,
        json={
            "applicant_name": "Some Applicant",
            "action": "approve",
            "status": "evidence_verified",
            "organization_key": "medtronic",
            "reviewer": "alice",
            "reviewer_kind": "human",
            "evidence": EVIDENCE,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "reviewer_kind_forbidden"
    # nothing was written
    assert client.get("/api/review/stats", headers=HEADERS).json()["decision_count"] == 0


def test_api_refuses_human_reviewed_status(tmp_path: Path) -> None:
    client = _admin(tmp_path)
    response = client.post(
        "/api/review/decisions",
        headers=HEADERS,
        json={
            "applicant_name": "Some Applicant",
            "action": "approve",
            "status": "human_reviewed",
            "organization_key": "medtronic",
            "reviewer": "alice",
            "evidence": EVIDENCE,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "human_review_authority_unavailable"
    assert client.get("/api/review/stats", headers=HEADERS).json()["decision_count"] == 0


def test_api_records_agent_authority_for_a_valid_decision(tmp_path: Path) -> None:
    client = _admin(tmp_path)
    response = client.post(
        "/api/review/decisions",
        headers=HEADERS,
        json={
            "applicant_name": "Some Applicant",
            "action": "approve",
            "status": "evidence_verified",
            "organization_key": "medtronic",
            "reviewer": "alice",
            "evidence": EVIDENCE,
        },
    )
    assert response.status_code == 200, response.text
    decision = response.json()["decision"]
    assert decision["status"] == "evidence_verified"
    assert decision["authority_kind"] == "agent"
    assert decision["authority_method"] == "local_service_token"
    assert decision["reviewer_kind"] == "agent"
    stats = client.get("/api/review/stats", headers=HEADERS).json()
    assert stats["human_reviewed_count"] == 0
    assert stats["human_review_authority_available"] is False


def test_capabilities_state_the_boundary(tmp_path: Path) -> None:
    client = _admin(tmp_path)
    payload = client.get("/api/review/capabilities", headers=HEADERS).json()
    assert payload["human_review_authority_available"] is False
    assert "human_reviewed" not in payload["writable_statuses"]
    assert payload["authority_kinds"] == ["agent"]
    assert "authentication" in payload["human_review_reason"].lower()


def test_import_ignores_self_declared_actor_kind(tmp_path: Path) -> None:
    client = _admin(tmp_path)
    payload = {
        "decisions": [
            {
                "applicant_name": "Some Applicant",
                "action": "approve",
                "status": "evidence_verified",
                "organization_key": "medtronic",
                "reviewer": "alice",
                "reviewer_kind": "human",
                "evidence": EVIDENCE,
            }
        ]
    }
    response = client.post("/api/review/import", headers=HEADERS, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["imported"] == 1
    assert body["ignored_reviewer_kind_fields"] == 1
    stored = client.get("/api/review/history/Some Applicant", headers=HEADERS).json()["history"]
    assert stored[0]["authority_kind"] == "agent"
    assert stored[0]["status"] == "evidence_verified"


def test_cli_refuses_human_reviewed(tmp_path: Path, capsys) -> None:
    from medradar.product.review.cli import main

    code = main(
        [
            "decide",
            "--applicant", "Some Applicant",
            "--action", "approve",
            "--status", "human_reviewed",
            "--org", "medtronic",
            "--reviewer", "alice",
            "--review-db", str(tmp_path / "review.db"),
        ]
    )
    assert code == 1
    assert "human_reviewed cannot be recorded" in capsys.readouterr().err


def _create_legacy_database(path: Path) -> None:
    """A schema-1 database written by the previous release, including a forged human claim."""
    connection = sqlite3.connect(str(path))
    try:
        connection.executescript(
            """
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE review_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_uid TEXT NOT NULL UNIQUE,
                applicant_key TEXT NOT NULL,
                applicant_name TEXT NOT NULL,
                organization_key TEXT,
                prior_organization_key TEXT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                basis TEXT,
                evidence_type TEXT,
                evidence_json TEXT,
                note TEXT,
                reviewer TEXT NOT NULL,
                reviewer_kind TEXT NOT NULL,
                created_at TEXT NOT NULL,
                supersedes_uid TEXT,
                snapshot_id TEXT,
                source TEXT
            );
            CREATE TABLE review_revocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_uid TEXT NOT NULL,
                revoked_by_uid TEXT NOT NULL,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT
            );
            CREATE TABLE review_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                actor TEXT NOT NULL,
                actor_kind TEXT NOT NULL,
                operation TEXT NOT NULL,
                payload_json TEXT
            );
            CREATE TRIGGER review_decisions_no_update BEFORE UPDATE ON review_decisions
            BEGIN SELECT RAISE(ABORT, 'append only'); END;
            CREATE TRIGGER review_decisions_no_delete BEFORE DELETE ON review_decisions
            BEGIN SELECT RAISE(ABORT, 'append only'); END;
            """
        )
        connection.execute("INSERT INTO schema_meta(key, value) VALUES('schema_version', '1')")
        connection.execute(
            "INSERT INTO review_decisions(decision_uid, applicant_key, applicant_name, organization_key,"
            " prior_organization_key, action, status, basis, evidence_type, evidence_json, note, reviewer,"
            " reviewer_kind, created_at, supersedes_uid, snapshot_id, source)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-human-uid",
                "some applicant",
                "Some Applicant",
                "medtronic",
                None,
                "approve",
                "human_reviewed",
                "brand",
                "regulator_record",
                json.dumps(EVIDENCE),
                "legacy forged claim",
                "alice",
                "human",
                "2026-01-01T00:00:00Z",
                None,
                None,
                "admin_api",
            ),
        )
        connection.execute(
            "INSERT INTO review_decisions(decision_uid, applicant_key, applicant_name, organization_key,"
            " prior_organization_key, action, status, basis, evidence_type, evidence_json, note, reviewer,"
            " reviewer_kind, created_at, supersedes_uid, snapshot_id, source)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-agent-uid",
                "other applicant",
                "Other Applicant",
                "medtronic",
                None,
                "approve",
                "evidence_verified",
                "brand",
                "regulator_record",
                json.dumps(EVIDENCE),
                "legacy agent decision",
                "agent:lead",
                "agent",
                "2026-01-01T00:00:00Z",
                None,
                None,
                "admin_api",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_legacy_human_claim_is_downgraded_without_rewriting_history(tmp_path: Path) -> None:
    path = tmp_path / "review.db"
    _create_legacy_database(path)
    store = ReviewStore(path)
    history = store.history("Some Applicant")
    assert len(history) == 1
    record = history[0]
    assert record.status_recorded == "human_reviewed", "the historical claim stays visible"
    assert record.status == "evidence_verified", "the effective status is downgraded"
    assert record.status_downgraded is True
    assert record.authority_kind == "unverified_operator"
    assert record.evidence, "the evidence is still there"
    effective = store.effective()["some applicant"]
    assert effective.status == "evidence_verified"
    stats = store.stats()
    assert stats["human_reviewed_count"] == 0
    assert stats["downgraded_claim_count"] == 1
    assert stats["schema_version"] == 2
    # the underlying row is untouched
    connection = sqlite3.connect(str(path))
    try:
        raw = connection.execute(
            "SELECT status, reviewer_kind FROM review_decisions WHERE decision_uid = 'legacy-human-uid'"
        ).fetchone()
        assert raw == ("human_reviewed", "human")
        audit = connection.execute(
            "SELECT operation FROM review_audit WHERE operation = 'migrate:schema_v2'"
        ).fetchone()
        assert audit is not None
    finally:
        connection.close()


def test_legacy_agent_decision_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "review.db"
    _create_legacy_database(path)
    store = ReviewStore(path)
    record = store.history("Other Applicant")[0]
    assert record.status == "evidence_verified"
    assert record.status_downgraded is False
    assert record.authority_kind == "agent"


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "review.db"
    _create_legacy_database(path)
    ReviewStore(path)
    second = ReviewStore(path)
    assert second.stats()["schema_version"] == 2
    connection = sqlite3.connect(str(path))
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM review_audit WHERE operation = 'migrate:schema_v2'"
        ).fetchone()[0]
        assert count == 1
    finally:
        connection.close()
