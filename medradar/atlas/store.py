"""SQLite store for ATLAS evidence, entities, relations and quality findings.

Immutability model
------------------
``evidence`` is append-only and keyed by ``(evidence_id, version)``.  Re-fetching
unchanged content is a no-op; changed content creates a new version and updates
only the ``evidence_head`` pointer.  Existing version rows are never updated or
deleted.  ``first_observed_at`` therefore keeps the *earliest* observation even
after many re-fetches — which is the only defensible basis for an ``as_of``
query.

Relations are also versioned by *revocation*: ``entity_relations`` rows are
never deleted.  Revoking sets ``revoked_at``/``revoked_reason`` and appends a
``relation_events`` row, so the history "this was believed, then withdrawn,
because…" survives.

The store opens only the path it is given.  It has no knowledge of, and no
write path into, the legacy MedRadar databases under ``data/``.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from . import config
from .db import current_version, migrate as run_migrations
from .evidence import schema as ev
from .evidence.timeq import utc_iso
from .identity.resolver import MatchDecision


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class AtlasStore:
    def __init__(self, path: Path | str | None = None, *, auto_migrate: bool = True) -> None:
        self.path = Path(path) if path else config.DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_report: dict[str, Any] = {}
        if auto_migrate:
            self.migration_report = run_migrations(self.path)
        self._conn: sqlite3.Connection | None = None

    # --------------------------------------------------------------- lifecycle
    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(str(self.path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "AtlasStore":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ------------------------------------------------------------------- runs
    def start_run(
        self,
        run_id: str,
        *,
        connector_id: str,
        source_id: str,
        git_commit: str = "",
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO collection_runs(run_id, connector_id, source_id, started_at, git_commit)"
                " VALUES (?, ?, ?, ?, ?)",
                (run_id, connector_id, source_id, utc_iso(), git_commit),
            )

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        requests: int = 0,
        records: int = 0,
        nbytes: int = 0,
        notes: str = "",
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE collection_runs SET finished_at=?, status=?, requests=?, records=?,"
                " bytes=?, notes=? WHERE run_id=?",
                (utc_iso(), status, requests, records, nbytes, notes, run_id),
            )

    def log_requests(self, run_id: str, source_id: str, entries: Iterable[Mapping[str, Any]]) -> int:
        rows = [
            (
                run_id, source_id, str(e.get("logged_at", "")), str(e.get("url", ""))[:2000],
                e.get("status"), int(e.get("bytes", 0) or 0), int(e.get("elapsed_ms", 0) or 0),
                int(e.get("attempts", 1) or 1), str(e.get("error", ""))[:500],
                str(e.get("note", ""))[:500],
            )
            for e in entries
        ]
        if rows:
            with self.transaction() as conn:
                conn.executemany(
                    "INSERT INTO request_log(run_id, source_id, logged_at, url, status, bytes,"
                    " elapsed_ms, attempts, error, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
        return len(rows)

    def record_raw(
        self,
        *,
        content_hash: str,
        source_id: str,
        source_url: str,
        nbytes: int,
        fetched_at: str,
        media_type: str = "application/json",
        storage_path: str = "",
        truncated: bool = False,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO raw_objects(content_hash, source_id, source_url, media_type,"
                " bytes, fetched_at, storage_path, truncated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (content_hash, source_id, source_url[:2000], media_type, nbytes, fetched_at,
                 storage_path[:500], 1 if truncated else 0),
            )

    # --------------------------------------------------------------- evidence
    def append_evidence(self, record: Mapping[str, Any], *, run_id: str = "") -> dict[str, Any]:
        """Append a version of one evidence record.  Never mutates older versions."""
        problems = ev.validate_evidence(record)
        if problems:
            raise ev.EvidenceError(f"{record.get('evidence_id')}: {'; '.join(problems)}")
        eid = str(record["evidence_id"])
        chash = str(record["content_hash"])
        time_block = record["time"]
        conn = self.connect()
        with self.transaction():
            row = conn.execute(
                "SELECT MAX(version) AS v FROM evidence WHERE evidence_id=?", (eid,)
            ).fetchone()
            latest = int(row["v"]) if row and row["v"] is not None else 0
            if latest:
                existing = conn.execute(
                    "SELECT 1 FROM evidence WHERE evidence_id=? AND content_hash=?", (eid, chash)
                ).fetchone()
                if existing:
                    return {"inserted": False, "version": latest, "evidence_id": eid}
            version = latest + 1
            conn.execute(
                "INSERT INTO evidence(evidence_id, version, content_hash, evidence_type, source_id,"
                " source_record_id, source_url, canonical_key, canonical_entity_id, event_at,"
                " source_public_at, first_observed_at, fetched_at, time_quality, identity_status,"
                " relation_status, licence_status, quality_flags, payload_json, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    eid, version, chash, record["evidence_type"], record["source_id"],
                    str(record["source_record_id"]), str(record.get("source_url", ""))[:2000],
                    record.get("canonical_key"), str(record.get("canonical_entity_id", "")),
                    time_block.get("event_at", ""), time_block.get("source_public_at", ""),
                    time_block["first_observed_at"], time_block["fetched_at"],
                    time_block.get("source_public_at_quality", "unknown"),
                    record.get("identity_resolution_status", "not_attempted"),
                    record.get("relation_status", "none"),
                    record.get("licence_status", "unknown"),
                    _json(record.get("quality_flags", [])), _json(dict(record)), run_id,
                ),
            )
            conn.execute(
                "INSERT INTO evidence_head(evidence_id, latest_version, latest_hash, evidence_type,"
                " source_id, source_record_id, canonical_key, first_observed_at, latest_observed_at,"
                " versions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)"
                " ON CONFLICT(evidence_id) DO UPDATE SET"
                "  latest_version=excluded.latest_version, latest_hash=excluded.latest_hash,"
                "  latest_observed_at=excluded.latest_observed_at,"
                "  versions=evidence_head.versions + 1",
                (
                    eid, version, chash, record["evidence_type"], record["source_id"],
                    str(record["source_record_id"]), record.get("canonical_key"),
                    time_block["first_observed_at"], time_block["fetched_at"],
                ),
            )
            for ident in record.get("identifiers", []) or []:
                conn.execute(
                    "INSERT OR REPLACE INTO evidence_identifiers(evidence_id, version, scheme, value,"
                    " issuer, scope, is_primary) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (eid, version, str(ident["scheme"]), str(ident["value"]),
                     str(ident.get("issuer", "")), str(ident.get("scope", "")),
                     1 if ident.get("is_primary") else 0),
                )
            for ref in record.get("entity_refs", []) or []:
                conn.execute(
                    "INSERT OR REPLACE INTO evidence_entity_refs(evidence_id, version, entity_type,"
                    " name_raw, firm_key, method, confidence, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (eid, version, str(ref.get("entity_type", "")), str(ref.get("name_raw", ""))[:500],
                     ref.get("firm_key") or ref.get("resolved_key"), str(ref.get("method", "none")),
                     float(ref.get("confidence", 0.0)), str(ref.get("note", ""))[:500]),
                )
        return {"inserted": True, "version": version, "evidence_id": eid}

    def get_evidence(self, evidence_id: str, version: int | None = None) -> dict[str, Any] | None:
        conn = self.connect()
        if version is None:
            row = conn.execute(
                "SELECT e.payload_json FROM evidence e JOIN evidence_head h"
                " ON h.evidence_id=e.evidence_id AND h.latest_version=e.version"
                " WHERE e.evidence_id=?", (evidence_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT payload_json FROM evidence WHERE evidence_id=? AND version=?",
                (evidence_id, version),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def iter_evidence(self, *, source_id: str = "", evidence_type: str = "") -> Iterator[dict[str, Any]]:
        sql = "SELECT payload_json FROM evidence WHERE 1=1"
        params: list[Any] = []
        if source_id:
            sql += " AND source_id=?"
            params.append(source_id)
        if evidence_type:
            sql += " AND evidence_type=?"
            params.append(evidence_type)
        for row in self.connect().execute(sql, params):
            yield json.loads(row["payload_json"])

    def evidence_for_canonical_key(self, key: str) -> list[dict[str, Any]]:
        rows = self.connect().execute(
            "SELECT evidence_id, source_id, latest_version FROM evidence_head WHERE canonical_key=?",
            (key,),
        ).fetchall()
        out = []
        for row in rows:
            record = self.get_evidence(row["evidence_id"], row["latest_version"])
            if record:
                out.append(record)
        return out

    # ---------------------------------------------------------------- entities
    def upsert_company(
        self,
        *,
        company_id: str,
        canonical_name: str,
        country: str = "",
        legal_form: str = "",
        valid_from: str = "",
        valid_to: str = "",
        parent_company_id: str = "",
        metadata: Mapping[str, Any] | None = None,
        aliases: Sequence[str] = (),
        evidence_id: str = "",
        source_id: str = "",
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO companies(company_id, canonical_name, country, legal_form, valid_from,"
                " valid_to, parent_company_id, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(company_id) DO UPDATE SET canonical_name=excluded.canonical_name,"
                " country=excluded.country, legal_form=excluded.legal_form,"
                " parent_company_id=excluded.parent_company_id, metadata_json=excluded.metadata_json",
                (company_id, canonical_name, country, legal_form, valid_from, valid_to,
                 parent_company_id, _json(dict(metadata or {}))),
            )
            for alias in [canonical_name, *aliases]:
                conn.execute(
                    "INSERT OR IGNORE INTO company_names(company_id, name, name_type, valid_from,"
                    " valid_to, source_id, evidence_id) VALUES (?, ?, 'alias', ?, ?, ?, ?)",
                    (company_id, alias, valid_from, valid_to, source_id, evidence_id),
                )

    def upsert_manufacturer(
        self,
        *,
        manufacturer_id: str,
        name: str,
        company_id: str = "",
        role: str = "legal_manufacturer",
        country: str = "",
        site: str = "",
        relationship: str = "unknown",
        valid_from: str = "",
        valid_to: str = "",
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO manufacturers(manufacturer_id, name, company_id, role, country, site,"
                " relationship, valid_from, valid_to) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(manufacturer_id) DO UPDATE SET name=excluded.name,"
                " company_id=excluded.company_id, role=excluded.role, country=excluded.country,"
                " site=excluded.site, relationship=excluded.relationship",
                (manufacturer_id, name, company_id, role, country, site, relationship,
                 valid_from, valid_to),
            )

    def upsert_device(
        self,
        *,
        device_id: str,
        canonical_name: str,
        brand_name: str = "",
        model_number: str = "",
        catalog_number: str = "",
        product_family: str = "",
        device_class: str = "",
        company_id: str = "",
        manufacturer_id: str = "",
        markets: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
        product_codes: Sequence[str] = (),
        identifiers: Iterable[Mapping[str, Any]] = (),
        evidence_id: str = "",
    ) -> None:
        meta = dict(metadata or {})
        if evidence_id and not meta.get("evidence_id"):
            meta["evidence_id"] = evidence_id
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO devices(device_id, canonical_name, brand_name, model_number,"
                " catalog_number, product_family, device_class, company_id, manufacturer_id,"
                " markets_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(device_id) DO UPDATE SET canonical_name=excluded.canonical_name,"
                " brand_name=excluded.brand_name, model_number=excluded.model_number,"
                " catalog_number=excluded.catalog_number, product_family=excluded.product_family,"
                " device_class=excluded.device_class, company_id=excluded.company_id,"
                " manufacturer_id=excluded.manufacturer_id, markets_json=excluded.markets_json,"
                " metadata_json=excluded.metadata_json",
                (device_id, canonical_name, brand_name, model_number, catalog_number,
                 product_family, device_class, company_id, manufacturer_id, _json(list(markets)),
                 _json(meta)),
            )
            for code in product_codes:
                if code:
                    conn.execute(
                        "INSERT OR IGNORE INTO device_product_codes(device_id, product_code)"
                        " VALUES (?, ?)", (device_id, str(code)),
                    )
            for ident in identifiers:
                conn.execute(
                    "INSERT OR IGNORE INTO device_identifiers(device_id, scheme, value, issuer,"
                    " is_primary, evidence_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (device_id, str(ident["scheme"]), str(ident["value"]),
                     str(ident.get("issuer", "")), 1 if ident.get("is_primary") else 0, evidence_id),
                )
                # An identifier observed in a record is also an observation of
                # the device under that field, timestamped by first observation.
                conn.execute(
                    "INSERT INTO observations(entity_ref, field, value_json, observed_at,"
                    " evidence_id) VALUES (?, ?, ?, ?, ?)",
                    (device_id, f"identifier.{ident['scheme']}",
                     _json(str(ident["value"])), utc_iso(), evidence_id),
                )

    # --------------------------------------------------------------- relations
    def add_relation(
        self,
        decision: MatchDecision,
        *,
        from_type: str = "device",
        to_type: str = "device",
        evidence_ids: Sequence[str] = (),
        run_id: str = "",
        graph_relation: str = "",
    ) -> str:
        """Persist one decision.  REJECTED decisions are kept as negative evidence."""
        relation_type = graph_relation or decision.relation_type
        relation_id = ev.deterministic_id(
            "rel", decision.left_ref, decision.right_ref, relation_type
        )
        with self.transaction() as conn:
            existing = conn.execute(
                "SELECT status, revoked_at FROM entity_relations WHERE relation_id=?",
                (relation_id,),
            ).fetchone()
            if existing and not existing["revoked_at"]:
                return relation_id
            conn.execute(
                "INSERT INTO entity_relations(relation_id, from_ref, from_type, to_ref, to_type,"
                " relation_type, status, method, authority, confidence, basis_json,"
                " contradictions_json, rejection_reason, evidence_ids_json, created_at, run_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    relation_id, decision.left_ref, from_type, decision.right_ref, to_type,
                    relation_type, decision.status, decision.method, decision.authority,
                    float(decision.confidence), _json(decision.basis),
                    _json(decision.contradictions), decision.rejection_reason,
                    _json(list(evidence_ids)), utc_iso(), run_id,
                ),
            )
            conn.execute(
                "INSERT INTO relation_events(relation_id, action, at, reason, evidence_ids_json)"
                " VALUES (?, 'created', ?, ?, ?)",
                (relation_id, utc_iso(), decision.rejection_reason, _json(list(evidence_ids))),
            )
        return relation_id

    def revoke_relation(
        self, relation_id: str, *, reason: str, evidence_ids: Sequence[str] = ()
    ) -> bool:
        """Withdraw a relation without deleting its history."""
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT revoked_at FROM entity_relations WHERE relation_id=?", (relation_id,)
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE entity_relations SET revoked_at=?, revoked_reason=? WHERE relation_id=?",
                (utc_iso(), reason, relation_id),
            )
            conn.execute(
                "INSERT INTO relation_events(relation_id, action, at, reason, evidence_ids_json)"
                " VALUES (?, 'revoked', ?, ?, ?)",
                (relation_id, utc_iso(), reason, _json(list(evidence_ids))),
            )
        return True

    def list_relations(
        self,
        *,
        relation_type: str = "",
        status: str = "",
        include_revoked: bool = False,
        entity_ref: str = "",
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM entity_relations WHERE 1=1"
        params: list[Any] = []
        if relation_type:
            sql += " AND relation_type=?"
            params.append(relation_type)
        if status:
            sql += " AND status=?"
            params.append(status)
        if not include_revoked:
            sql += " AND revoked_at=''"
        if entity_ref:
            sql += " AND (from_ref=? OR to_ref=?)"
            params.extend([entity_ref, entity_ref])
        rows = self.connect().execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    # ---------------------------------------------------------------- quality
    def add_quality_finding(
        self,
        *,
        check_id: str,
        severity: str,
        subject: str,
        detail: str,
        evidence_ids: Sequence[str] = (),
        run_id: str = "",
    ) -> str:
        finding_id = ev.deterministic_id("qf", check_id, subject, detail[:200])
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO quality_findings(finding_id, check_id, severity, subject,"
                " detail, evidence_ids_json, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (finding_id, check_id, severity, subject[:500], detail[:2000],
                 _json(list(evidence_ids)), run_id, utc_iso()),
            )
        return finding_id

    def quality_findings(self, *, check_id: str = "") -> list[dict[str, Any]]:
        sql = "SELECT * FROM quality_findings WHERE 1=1"
        params: list[Any] = []
        if check_id:
            sql += " AND check_id=?"
            params.append(check_id)
        return [dict(row) for row in self.connect().execute(sql, params)]

    def set_source_status(
        self, *, check_id: str, source_id: str, status: str, detail: str = "",
        evidence_url: str = "", run_id: str = "",
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO source_status(check_id, source_id, checked_at, status,"
                " detail, evidence_url, run_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (check_id, source_id, utc_iso(), status, detail[:2000], evidence_url[:2000], run_id),
            )

    # --------------------------------------------------------------- observation
    def observe(
        self, *, entity_ref: str, field: str, value: Any, observed_at: str = "",
        evidence_id: str = "", run_id: str = "",
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO observations(entity_ref, field, value_json, observed_at, evidence_id,"
                " run_id) VALUES (?, ?, ?, ?, ?, ?)",
                (entity_ref, field, _json(value), observed_at or utc_iso(), evidence_id, run_id),
            )

    # ------------------------------------------------------- prospective registry
    def register_prospective_candidate(
        self,
        *,
        name_raw: str,
        source_id: str,
        evidence_id: str,
        first_observed_at: str,
        company_candidate: str = "",
        known_identifiers: Sequence[Mapping[str, Any]] = (),
        notes: str = "",
    ) -> str:
        candidate_id = ev.deterministic_id("pc", source_id, name_raw, first_observed_at)
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO prospective_candidates(candidate_id, name_raw, source_id, evidence_id,"
                " first_observed_at, company_candidate, known_identifiers_json, status, version,"
                " updated_at, notes) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', 1, ?, ?)"
                " ON CONFLICT(candidate_id) DO UPDATE SET updated_at=excluded.updated_at,"
                " version=prospective_candidates.version + 1",
                (candidate_id, name_raw[:500], source_id, evidence_id, first_observed_at,
                 company_candidate[:200], _json(list(known_identifiers)), utc_iso(), notes[:1000]),
            )
            conn.execute(
                "INSERT INTO prospective_events(candidate_id, at, action, payload_json)"
                " VALUES (?, ?, 'registered', ?)",
                (candidate_id, utc_iso(), _json({"evidence_id": evidence_id})),
            )
        return candidate_id

    def prospective_candidates(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.connect().execute(
                "SELECT * FROM prospective_candidates ORDER BY first_observed_at, candidate_id"
            )
        ]

    # ---------------------------------------------------------------- reporting
    def stats(self) -> dict[str, Any]:
        conn = self.connect()
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        by_status = {
            row["status"]: row["n"]
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM entity_relations GROUP BY status"
            )
        }
        by_type = {
            row["relation_type"]: row["n"]
            for row in conn.execute(
                "SELECT relation_type, COUNT(*) AS n FROM entity_relations GROUP BY relation_type"
            )
        }
        by_source = {
            row["source_id"]: row["n"]
            for row in conn.execute(
                "SELECT source_id, COUNT(*) AS n FROM evidence_head GROUP BY source_id"
            )
        }
        return {
            "db": config.relative(self.path),
            "schema_version": self.migration_report.get("schema_version")
            or current_version(self.path),
            "evidence_ids": one("SELECT COUNT(*) FROM evidence_head"),
            "evidence_versions": one("SELECT COUNT(*) FROM evidence"),
            "companies": one("SELECT COUNT(*) FROM companies"),
            "manufacturers": one("SELECT COUNT(*) FROM manufacturers"),
            "devices": one("SELECT COUNT(*) FROM devices"),
            "device_identifiers": one("SELECT COUNT(*) FROM device_identifiers"),
            "relations_total": one("SELECT COUNT(*) FROM entity_relations"),
            "relations_confirmed": one(
                "SELECT COUNT(*) FROM entity_relations WHERE status='CONFIRMED' AND revoked_at=''"
            ),
            "relations_candidate": one(
                "SELECT COUNT(*) FROM entity_relations WHERE status='CANDIDATE' AND revoked_at=''"
            ),
            "relations_rejected": one(
                "SELECT COUNT(*) FROM entity_relations WHERE status='REJECTED' AND revoked_at=''"
            ),
            "relations_unknown": one(
                "SELECT COUNT(*) FROM entity_relations WHERE status='UNKNOWN' AND revoked_at=''"
            ),
            "relations_revoked": one("SELECT COUNT(*) FROM entity_relations WHERE revoked_at<>''"),
            "relations_by_type": by_type,
            "relations_by_status": by_status,
            "evidence_by_source": by_source,
            "quality_findings": one("SELECT COUNT(*) FROM quality_findings"),
            "collection_runs": one("SELECT COUNT(*) FROM collection_runs"),
            "request_log": one("SELECT COUNT(*) FROM request_log"),
            "raw_objects": one("SELECT COUNT(*) FROM raw_objects"),
            "prospective_candidates": one("SELECT COUNT(*) FROM prospective_candidates"),
        }

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connect().execute(sql, params)]


__all__ = ["AtlasStore"]
