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

Reviewer authority (PRODUCT-003 P0-A)
-------------------------------------
An earlier version accepted a client-supplied reviewer_kind and defaulted it to "human". Any caller
could therefore assert that a human had approved a mapping. That is fixed here:

* the *authority* of an actor is derived on the server, never from the request body;
* the only authority this release can issue is "agent" (a named actor operating the local service or
  CLI, whose human-ness cannot be verified), plus "unverified_operator" for legacy rows;
* human_reviewed is refused by the store itself. Re-enabling it requires a real server-side operator
  authentication and authorisation mechanism, which this release does not have. The capability is
  reported as unavailable through /api/review/capabilities;
* legacy rows that claimed human_reviewed are preserved verbatim, but their *effective* status is
  downgraded at read time (to evidence_verified when evidence exists, otherwise unresolved). Nothing
  is rewritten, nothing is silently upgraded, and the downgrade is visible in the API and the audit.

Effective mapping
-----------------
effective() folds the ledger: for each applicant string, the latest decision that has not been
revoked wins. A revocation therefore restores the previous state without touching either row.

Access boundary
---------------
This module is storage only. Writing is reachable only through the loopback-bound internal admin
service (medradar.product.review.admin) or the CLI, never through the public API. See
docs/product/product_003/P0_FIXES.md and docs/product/product_002/IDENTITY_REVIEW_PROTOCOL.md.
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

SCHEMA_VERSION = 2
DEFAULT_DB = Path("data") / "identity" / "review.db"

ACTIONS = ("approve", "reassign", "reject", "unresolved", "revoke")

#: Statuses a review decision may *request*. human_reviewed is refused by the store in this release.
DECISION_STATUSES = ("rule_verified", "evidence_verified", "human_reviewed", "rejected", "unresolved")

#: Statuses that can actually be written today.
WRITABLE_STATUSES = ("rule_verified", "evidence_verified", "rejected", "unresolved")

#: Explicit capability switch. It becomes True only when a server-side human authentication
#: mechanism exists. Flipping it without such a mechanism is not a configuration change, it is a lie.
HUMAN_REVIEW_AUTHORITY_AVAILABLE = False

ACTOR_KINDS = ("agent", "unverified_operator")

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
    # Server-derived authority records. A separate table keeps review_decisions immutable: no UPDATE
    # is ever needed, including for legacy rows.
    "CREATE TABLE IF NOT EXISTS review_authority ("
    " decision_uid TEXT PRIMARY KEY,"
    " actor_label TEXT NOT NULL,"
    " authority_kind TEXT NOT NULL,"
    " authority_method TEXT,"
    " attestation TEXT,"
    " recorded_at TEXT NOT NULL)",
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


class ReviewError(ValueError):
    """Raised when a decision would violate the ledger's rules."""


class HumanAuthorityUnavailable(ReviewError):
    """Raised when code attempts to obtain human review authority in this release."""


@dataclass(frozen=True)
class ReviewerAuthority:
    """Server-derived description of who is acting.

    kind is decided by the server, not by the request. label is the actor's claimed name and is
    recorded for accountability only; it is never used to justify a status.
    """

    kind: str
    method: str
    label: str
    attestation: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ACTOR_KINDS:
            raise ReviewError("unsupported actor kind: " + repr(self.kind))


def agent_authority(label: str, method: str = "local_service_token", attestation: str | None = None) -> ReviewerAuthority:
    """The only authority this release can issue: a named actor that is not verified as a human."""
    return ReviewerAuthority(kind="agent", method=method, label=str(label or "").strip(), attestation=attestation)


def human_authority(*, label: str, method: str, attestation: str | None = None) -> ReviewerAuthority:
    """Always raises.

    Human review authority requires server-side operator authentication and authorisation. Until that
    exists, no code path may construct it, so human_reviewed cannot be written at all. Keeping this
    function (instead of silently removing the concept) makes the boundary explicit and testable.
    """
    raise HumanAuthorityUnavailable(
        "human review authority is unavailable: this release has no server-side mechanism that can "
        "verify that the operator is a human. Record evidence_verified instead, or wire an "
        "authenticated operator identity before enabling human_reviewed."
    )


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
    status_recorded: str
    status_downgraded: bool
    status_downgraded_reason: str | None
    basis: str | None
    evidence_type: str | None
    evidence: tuple[dict[str, Any], ...]
    note: str | None
    reviewer: str
    reviewer_kind: str
    authority_kind: str
    authority_method: str | None
    attestation: str | None
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
            "status_recorded": self.status_recorded,
            "status_downgraded": self.status_downgraded,
            "status_downgraded_reason": self.status_downgraded_reason,
            "basis": self.basis,
            "evidence_type": self.evidence_type,
            "evidence": list(self.evidence),
            "note": self.note,
            "reviewer": self.reviewer,
            "reviewer_kind": self.reviewer_kind,
            "authority_kind": self.authority_kind,
            "authority_method": self.authority_method,
            "attestation": self.attestation,
            "created_at": self.created_at,
            "supersedes_uid": self.supersedes_uid,
            "snapshot_id": self.snapshot_id,
            "source": self.source,
            "revoked": self.revoked,
        }


def _effective_status(recorded: str, authority_kind: str, evidence: tuple[dict[str, Any], ...]) -> tuple[str, bool, str | None]:
    """Downgrade a claim that the current system is unable to substantiate."""
    if recorded == "human_reviewed" and authority_kind != "human":
        if evidence:
            return "evidence_verified", True, (
                "recorded as human_reviewed by an actor whose human status could not be verified; "
                "the effective status is evidence_verified because evidence is recorded"
            )
        return "unresolved", True, (
            "recorded as human_reviewed by an actor whose human status could not be verified and no "
            "evidence is recorded; the effective status is unresolved"
        )
    return recorded, False, None


class ReviewStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self._lock = threading.RLock()
        self._ensure()
        self._migrate()

    # ------------------------------------------------------------------ setup
    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        try:
            return {row["name"] for row in connection.execute("PRAGMA table_info(" + table + ")")}
        except sqlite3.DatabaseError:
            return set()

    def _ensure(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.commit()
            finally:
                connection.close()

    def _migrate(self) -> None:
        """Schema 1 -> 2: record server-derived authority for legacy rows, never rewrite history."""
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
                version = int(row["value"]) if row else 1
                if version >= SCHEMA_VERSION:
                    return
                inserted = 0
                legacy = connection.execute(
                    "SELECT decision_uid, reviewer, reviewer_kind, created_at FROM review_decisions"
                ).fetchall()
                for item in legacy:
                    kind = "agent" if item["reviewer_kind"] == "agent" else "unverified_operator"
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO review_authority"
                        "(decision_uid, actor_label, authority_kind, authority_method, attestation, recorded_at)"
                        " VALUES(?,?,?,?,?,?)",
                        (item["decision_uid"], item["reviewer"], kind, "legacy_migration", None, item["created_at"]),
                    )
                    inserted += int(cursor.rowcount or 0)
                connection.execute(
                    "INSERT INTO review_audit(at, actor, actor_kind, operation, payload_json) VALUES(?,?,?,?,?)",
                    (
                        _now(),
                        "system:migration",
                        "system",
                        "migrate:schema_v2",
                        json.dumps(
                            {
                                "from_version": version,
                                "to_version": SCHEMA_VERSION,
                                "legacy_decisions": len(legacy),
                                "authority_rows_inserted": inserted,
                                "note": "server-derived authority added; legacy reviewer_kind=human rows become "
                                "unverified_operator and any human_reviewed claim is downgraded at read time, "
                                "never rewritten",
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
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
        authority = {
            row["decision_uid"]: row
            for row in connection.execute("SELECT * FROM review_authority").fetchall()
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
            record = authority.get(row["decision_uid"])
            if record is not None:
                authority_kind = record["authority_kind"]
                authority_method = record["authority_method"]
                attestation = record["attestation"]
            else:
                authority_kind = "agent" if row["reviewer_kind"] == "agent" else "unverified_operator"
                authority_method = None
                attestation = None
            effective, downgraded, reason = _effective_status(row["status"], authority_kind, evidence)
            out.append(
                ReviewDecision(
                    id=int(row["id"]),
                    decision_uid=row["decision_uid"],
                    applicant_key=row["applicant_key"],
                    applicant_name=row["applicant_name"],
                    organization_key=row["organization_key"],
                    prior_organization_key=row["prior_organization_key"],
                    action=row["action"],
                    status=effective,
                    status_recorded=row["status"],
                    status_downgraded=downgraded,
                    status_downgraded_reason=reason,
                    basis=row["basis"],
                    evidence_type=row["evidence_type"],
                    evidence=evidence,
                    note=row["note"],
                    reviewer=row["reviewer"],
                    reviewer_kind=authority_kind,
                    authority_kind=authority_kind,
                    authority_method=authority_method,
                    attestation=attestation,
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
        by_authority: dict[str, int] = {}
        downgraded = 0
        for decision in decisions:
            if decision.revoked:
                continue
            by_status[decision.status] = by_status.get(decision.status, 0) + 1
            by_authority[decision.authority_kind] = by_authority.get(decision.authority_kind, 0) + 1
            downgraded += int(decision.status_downgraded)
        return {
            "db_path": str(self.path),
            "schema_version": SCHEMA_VERSION,
            "decision_count": len(decisions),
            "revoked_count": sum(1 for decision in decisions if decision.revoked),
            "effective_count": len(self.effective()),
            "human_reviewed_count": by_status.get("human_reviewed", 0),
            "human_review_authority_available": HUMAN_REVIEW_AUTHORITY_AVAILABLE,
            "downgraded_claim_count": downgraded,
            "agent_recorded_count": sum(count for kind, count in by_authority.items() if kind != "human"),
            "by_status": by_status,
            "by_authority_kind": by_authority,
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
        authority: ReviewerAuthority,
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
        if not isinstance(authority, ReviewerAuthority):
            raise ReviewError("append() requires a server-derived ReviewerAuthority")
        if not str(reviewer).strip():
            raise ReviewError("reviewer identity label is required")
        evidence_payload = [dict(item) for item in (evidence or [])]
        if action == "revoke":
            if not supersedes_uid:
                raise ReviewError("action=revoke requires supersedes_uid")
        else:
            if status not in DECISION_STATUSES:
                raise ReviewError("unknown decision status: " + repr(status))
            if status == "human_reviewed":
                raise HumanAuthorityUnavailable(
                    "human_reviewed cannot be written: human review authority is unavailable in this "
                    "release (no server-side operator authentication). Use evidence_verified with recorded "
                    "evidence, or unresolved when evidence is insufficient."
                )
            if status not in WRITABLE_STATUSES:
                raise ReviewError("status " + repr(status) + " is not writable in this release")
            if status in ("rule_verified", "evidence_verified") and not organization_key:
                raise ReviewError("an accepted decision needs an organization_key")
            if status == "evidence_verified" and not evidence_payload:
                raise ReviewError(
                    "evidence_verified requires at least one recorded evidence reference; use action=unresolved if none exists"
                )
            if status == "rule_verified" and not evidence_payload and not str(basis or "").strip():
                raise ReviewError(
                    "rule_verified requires the rule id in 'basis' (or an evidence reference) so the claim can be reproducible"
                )
            if action == "reject" and status != "rejected":
                raise ReviewError("action=reject requires status=rejected")
            if action == "unresolved" and status != "unresolved":
                raise ReviewError("action=unresolved requires status=unresolved")
        uid = uuid.uuid4().hex
        created = _now()
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
                        authority.kind,
                        created,
                        supersedes_uid,
                        snapshot_id,
                        source,
                    ),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO review_authority"
                    "(decision_uid, actor_label, authority_kind, authority_method, attestation, recorded_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (uid, authority.label, authority.kind, authority.method, authority.attestation, created),
                )
                if action == "revoke":
                    connection.execute(
                        "INSERT INTO review_revocations(decision_uid, revoked_by_uid, created_at, actor, reason)"
                        " VALUES(?,?,?,?,?)",
                        (supersedes_uid, uid, created, reviewer, note),
                    )
                connection.execute(
                    "INSERT INTO review_audit(at, actor, actor_kind, operation, payload_json) VALUES(?,?,?,?,?)",
                    (
                        created,
                        reviewer,
                        authority.kind,
                        "append:" + action,
                        json.dumps(
                            {
                                "decision_uid": uid,
                                "applicant_key": applicant_key,
                                "organization_key": organization_key,
                                "status": None if action == "revoke" else status,
                                "authority_kind": authority.kind,
                                "authority_method": authority.method,
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
            status_recorded="unresolved" if action == "revoke" else status,
            status_downgraded=False,
            status_downgraded_reason=None,
            basis=basis,
            evidence_type=evidence_type,
            evidence=tuple(evidence_payload),
            note=note,
            reviewer=reviewer,
            reviewer_kind=authority.kind,
            authority_kind=authority.kind,
            authority_method=authority.method,
            attestation=authority.attestation,
            created_at=created,
            supersedes_uid=supersedes_uid,
            snapshot_id=snapshot_id,
            source=source,
        )
