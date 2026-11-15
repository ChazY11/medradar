"""Auditable, append-only identity review ledger (SQLite).

Why an append-only ledger
-------------------------
An attribution decision is a claim about a legal entity. The product must be able to answer, for
any record: who decided this, on what evidence, when, and what the previous decision was. A table
that is updated in place cannot answer the last question, so this store never updates or deletes a
decision:

* every decision is a new row with its own decision_uid;
* correcting a decision appends a new decision that supersedes it (supersedes_uid);
* withdrawing a decision appends a revocation record for that uid and nothing else;
* SQLite triggers reject UPDATE and DELETE on the decisions table, so even a bug (or a future
  contributor) cannot rewrite history silently.

Effective mapping
-----------------
effective() folds the ledger: for each applicant string, the latest decision that has not been
revoked wins. A revocation therefore restores the previous state without touching either row.

Access boundary
---------------
This module is storage only. It does not decide authorisation. Writing is reachable only through
the loopback-bound internal admin service (medradar.product.review.admin) or the CLI, never through
the public API. See docs/product/product_002/IDENTITY_REVIEW_PROTOCOL.md.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = 1
DEFAULT_DB = Path("data") / "identity" / "review.db"

ACTIONS = ("approve", "reassign", "reject", "unresolved", "revoke")

#: Statuses a review decision may set. "human_reviewed" requires reviewer_kind == "human".
DECISION_STATUSES = ("rule_verified", "evidence_verified", "human_reviewed", "rejected", "unresolved")

_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS review_decisions ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " decision_uid TEXT NOT NULL UNIQUE,"
    " applicant_key TEXT NOT NULL,"
    " applicant_name TEXT NOT NULL,"
    " organization_key TEXT,"
    " prior_organization_key TEXT,"
    " action TEXT NOT NULL,"
    " status TEXT NOT NULL,"
    " basis TEXT,"
    " evidence_type TEXT,"
    " evidence_json TEXT,"
    " note TEXT,"
    " reviewer TEXT NOT NULL,"
    " reviewer_kind TEXT NOT NULL,"
    " created_at TEXT NOT NULL,"
    " supersedes_uid TEXT,"
    " snapshot_id TEXT,"
    " source TEXT)",
    "CREATE TABLE IF NOT EXISTS review_revocations ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " decision_uid TEXT NOT NULL,"
    " revoked_by_uid TEXT NOT NULL,"
    " created_at TEXT NOT NULL,"
    " actor TEXT NOT NULL,"
    " reason TEXT)",
    "CREATE TABLE IF NOT EXISTS review_audit ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " at TEXT NOT NULL,"
    " actor TEXT NOT NULL,"
    " actor_kind TEXT NOT NULL,"
    " operation TEXT NOT NULL,"
    " payload_json TEXT)",
    "CREATE INDEX IF NOT EXISTS review_decisions_applicant ON review_decisions(applicant_key, id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS review_revocation_unique ON review_revocations(decision_uid)",
    "CREATE TRIGGER IF NOT EXISTS review_decisions_no_update BEFORE UPDATE ON review_decisions"
    " BEGIN SELECT RAISE(ABORT, 'review decisions are append-only: append a new decision instead'); END",
    "CREATE TRIGGER IF NOT EXISTS review_decisions_no_delete BEFORE DELETE ON review_decisions"
    " BEGIN SELECT RAISE(ABORT, 'review decisions are append-only: append a revocation instead'); END",
    "CREATE TRIGGER IF NOT EXISTS review_revocations_no_update BEFORE UPDATE ON review_revocations"
    " BEGIN SELECT RAISE(ABORT, 'review revocations are append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS review_revocations_no_delete BEFORE DELETE ON review_revocations"
    " BEGIN SELECT RAISE(ABORT, 'review revocations are append-only'); END",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_db_path() -> Path:
    override = os.environ.get("MEDRADAR_REVIEW_DB")
    if override:
        return Path(override)
    return DEFAULT_DB


def normalise_applicant(value: str) -> str:
    text = unicodedata.normalize("NFC", value or "")
    return " ".join(text.casefold().split())


@dataclass(frozen=True)
class ReviewDecision:
    id: int
    decision_uid: str
    applicant_key: str
    applicant_name: str
    organization_key: str | None
    prior_organization_key: str | None
    action: str
    status: str
    basis: str | None
    evidence_type: str | None
    evidence: tuple[dict[str, Any], ...]
    note: str | None
    reviewer: str
    reviewer_kind: str
    created_at: str
    supersedes_uid: str | None
    snapshot_id: str | None
    source: str | None
    revoked: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "decision_uid": self.decision_uid,
            "applicant_key": self.applicant_key,
            "applicant_name": self.applicant_name,
            "organization_key": self.organization_key,
            "prior_organization_key": self.prior_organization_key,
            "action": self.action,
            "status": self.status,
            "basis": self.basis,
            "evidence_type": self.evidence_type,
            "evidence": list(self.evidence),
            "note": self.note,
            "reviewer": self.reviewer,
            "reviewer_kind": self.reviewer_kind,
            "created_at": self.created_at,
            "supersedes_uid": self.supersedes_uid,
            "snapshot_id": self.snapshot_id,
            "source": self.source,
            "revoked": self.revoked,
        }


class ReviewError(ValueError):
    """Raised when a decision would violate the ledger's rules."""


class ReviewStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self._lock = threading.RLock()
        self._ensure()

    # ------------------------------------------------------------------ setup
    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _ensure(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) ON CONFLICT(key) DO NOTHING",
                    (str(SCHEMA_VERSION),),
                )
                connection.commit()
            finally:
                connection.close()

    # ------------------------------------------------------------------ read
    def _decisions(self, connection: sqlite3.Connection, applicant_key: str | None = None) -> list[ReviewDecision]:
        revoked = {
            row["decision_uid"]
            for row in connection.execute("SELECT decision_uid FROM review_revocations").fetchall()
        }
        if applicant_key is None:
            rows = connection.execute("SELECT * FROM review_decisions ORDER BY id").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM review_decisions WHERE applicant_key = ? ORDER BY id", (applicant_key,)
            ).fetchall()
        out = []
        for row in rows:
            payload = row["evidence_json"]
            evidence = tuple(json.loads(payload)) if payload else ()
            out.append(
                ReviewDecision(
                    id=int(row["id"]),
                    decision_uid=row["decision_uid"],
                    applicant_key=row["applicant_key"],
                    applicant_name=row["applicant_name"],
                    organization_key=row["organization_key"],
                    prior_organization_key=row["prior_organization_key"],
                    action=row["action"],
                    status=row["status"],
                    basis=row["basis"],
                    evidence_type=row["evidence_type"],
                    evidence=evidence,
                    note=row["note"],
                    reviewer=row["reviewer"],
                    reviewer_kind=row["reviewer_kind"],
                    created_at=row["created_at"],
                    supersedes_uid=row["supersedes_uid"],
                    snapshot_id=row["snapshot_id"],
                    source=row["source"],
                    revoked=row["decision_uid"] in revoked,
                )
            )
        return out

    def all_decisions(self) -> list[ReviewDecision]:
        with self._lock:
            connection = self._connect()
            try:
                return self._decisions(connection)
            finally:
                connection.close()

    def history(self, applicant_key: str) -> list[ReviewDecision]:
        with self._lock:
            connection = self._connect()
            try:
                return self._decisions(connection, normalise_applicant(applicant_key))
            finally:
                connection.close()

    def effective(self) -> dict[str, ReviewDecision]:
        """Per applicant string: the latest decision that has not been revoked."""
        effective: dict[str, ReviewDecision] = {}
        for decision in self.all_decisions():
            if decision.revoked or decision.action == "revoke":
                continue
            effective[decision.applicant_key] = decision
        return effective

    def overlay_items(self) -> tuple:
        """Hashable overlay for medradar.product.identity.registry_with_overlay."""
        items = []
        for key, decision in sorted(self.effective().items()):
            items.append(
                (
                    key,
                    decision.organization_key,
                    decision.action,
                    decision.status,
                    decision.reviewer,
                    decision.reviewer_kind,
                    json.dumps(list(decision.evidence), sort_keys=True, ensure_ascii=False) if decision.evidence else "",
                    decision.decision_uid,
                    decision.note or "",
                    decision.applicant_name,
                )
            )
        return tuple(items)

    def fingerprint(self) -> tuple[int, int, int]:
        with self._lock:
            connection = self._connect()
            try:
                count = int(connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0])
                latest = int(connection.execute("SELECT COALESCE(MAX(id), 0) FROM review_decisions").fetchone()[0])
                revoked = int(connection.execute("SELECT COUNT(*) FROM review_revocations").fetchone()[0])
                return (count, latest, revoked)
            finally:
                connection.close()

    def stats(self) -> dict[str, Any]:
        decisions = self.all_decisions()
        by_status: dict[str, int] = {}
        by_reviewer_kind: dict[str, int] = {}
        for decision in decisions:
            if decision.revoked:
                continue
            by_status[decision.status] = by_status.get(decision.status, 0) + 1
            by_reviewer_kind[decision.reviewer_kind] = by_reviewer_kind.get(decision.reviewer_kind, 0) + 1
        return {
            "db_path": str(self.path),
            "decision_count": len(decisions),
            "revoked_count": sum(1 for decision in decisions if decision.revoked),
            "effective_count": len(self.effective()),
            "human_reviewed_count": by_status.get("human_reviewed", 0),
            "agent_recorded_count": sum(count for kind, count in by_reviewer_kind.items() if kind != "human"),
            "by_status": by_status,
            "by_reviewer_kind": by_reviewer_kind,
        }

    def audit_trail(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT * FROM review_audit ORDER BY id DESC LIMIT ?", (int(limit),)
                ).fetchall()
                return [
                    {
                        "id": int(row["id"]),
                        "at": row["at"],
                        "actor": row["actor"],
                        "actor_kind": row["actor_kind"],
                        "operation": row["operation"],
                        "payload": json.loads(row["payload_json"]) if row["payload_json"] else None,
                    }
                    for row in rows
                ]
            finally:
                connection.close()

    # ------------------------------------------------------------------ write
    def append(
        self,
        *,
        applicant_name: str,
        action: str,
        status: str,
        organization_key: str | None,
        reviewer: str,
        reviewer_kind: str,
        prior_organization_key: str | None = None,
        basis: str | None = None,
        evidence_type: str | None = None,
        evidence: Iterable[Mapping[str, Any]] | None = None,
        note: str | None = None,
        supersedes_uid: str | None = None,
        snapshot_id: str | None = None,
        source: str = "admin_api",
    ) -> ReviewDecision:
        applicant_key = normalise_applicant(applicant_name)
        if not applicant_key:
            raise ReviewError("applicant_name is required")
        if action not in ACTIONS:
            raise ReviewError("unknown action: " + repr(action))
        if reviewer_kind not in ("human", "agent"):
            raise ReviewError("reviewer_kind must be 'human' or 'agent'")
        if not str(reviewer).strip():
            raise ReviewError("reviewer is required")
        evidence_payload = [dict(item) for item in (evidence or [])]
        if action == "revoke":
            if not supersedes_uid:
                raise ReviewError("action=revoke requires supersedes_uid")
        else:
            if status not in DECISION_STATUSES:
                raise ReviewError("unknown decision status: " + repr(status))
            if status in ("rule_verified", "evidence_verified", "human_reviewed") and not organization_key:
                raise ReviewError("an accepted decision needs an organization_key")
            if status in ("evidence_verified", "human_reviewed") and not evidence_payload:
                raise ReviewError(
                    status + " requires at least one recorded evidence reference; use action=unresolved if none exists"
                )
            if status == "rule_verified" and not evidence_payload and not str(basis or "").strip():
                raise ReviewError(
                    "rule_verified requires the rule id in 'basis' (or an evidence reference) so the claim can be reproduced"
                )
            if status == "human_reviewed" and reviewer_kind != "human":
                raise ReviewError(
                    "human_reviewed requires reviewer_kind=human: an agent cannot mark its own judgement as human review"
                )
            if action == "reject" and status != "rejected":
                raise ReviewError("action=reject requires status=rejected")
            if action == "unresolved" and status != "unresolved":
                raise ReviewError("action=unresolved requires status=unresolved")
        uid = uuid.uuid4().hex
        with self._lock:
            connection = self._connect()
            try:
                if action == "revoke":
                    target = connection.execute(
                        "SELECT decision_uid FROM review_decisions WHERE decision_uid = ?", (supersedes_uid,)
                    ).fetchone()
                    if target is None:
                        raise ReviewError("no decision with uid " + repr(supersedes_uid))
                connection.execute(
                    "INSERT INTO review_decisions(decision_uid, applicant_key, applicant_name, organization_key,"
                    " prior_organization_key, action, status, basis, evidence_type, evidence_json, note, reviewer,"
                    " reviewer_kind, created_at, supersedes_uid, snapshot_id, source)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        uid,
                        applicant_key,
                        applicant_name,
                        organization_key,
                        prior_organization_key,
                        action,
                        "unresolved" if action == "revoke" else status,
                        basis,
                        evidence_type,
                        json.dumps(evidence_payload, ensure_ascii=False) if evidence_payload else None,
                        note,
                        reviewer,
                        reviewer_kind,
                        _now(),
                        supersedes_uid,
                        snapshot_id,
                        source,
                    ),
                )
                if action == "revoke":
                    connection.execute(
                        "INSERT INTO review_revocations(decision_uid, revoked_by_uid, created_at, actor, reason)"
                        " VALUES(?,?,?,?,?)",
                        (supersedes_uid, uid, _now(), reviewer, note),
                    )
                connection.execute(
                    "INSERT INTO review_audit(at, actor, actor_kind, operation, payload_json) VALUES(?,?,?,?,?)",
                    (
                        _now(),
                        reviewer,
                        reviewer_kind,
                        "append:" + action,
                        json.dumps(
                            {
                                "decision_uid": uid,
                                "applicant_key": applicant_key,
                                "organization_key": organization_key,
                                "status": None if action == "revoke" else status,
                                "supersedes_uid": supersedes_uid,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
                connection.commit()
            finally:
                connection.close()
        return ReviewDecision(
            id=0,
            decision_uid=uid,
            applicant_key=applicant_key,
            applicant_name=applicant_name,
            organization_key=organization_key,
            prior_organization_key=prior_organization_key,
            action=action,
            status="unresolved" if action == "revoke" else status,
            basis=basis,
            evidence_type=evidence_type,
            evidence=tuple(evidence_payload),
            note=note,
            reviewer=reviewer,
            reviewer_kind=reviewer_kind,
            created_at=_now(),
            supersedes_uid=supersedes_uid,
            snapshot_id=snapshot_id,
            source=source,
        )
