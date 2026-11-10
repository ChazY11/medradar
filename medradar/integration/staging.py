"""The CONVERGENCE staging database: a *new*, isolated database.

Rules this module enforces
--------------------------
* It never opens ATLAS's research database.  The path is always supplied by the
  caller and is a fresh file under ``research/convergence/staging/``.  ATLAS's
  own database under ``research/atlas/staging/`` is left untouched.
* It reuses ATLAS's append-only store (:class:`medradar.atlas.store.AtlasStore`)
  rather than re-implementing it, so imported evidence is validated by the same
  contract as ATLAS's own records and versioning/idempotency are the tested ATLAS
  semantics, not a second implementation that could drift.
* Rejected records are **retained with their payload**, never dropped.  A
  conversion that cannot happen is a fact about the data and must be auditable.
* Every run is recorded, so any run can be rolled back — and rollback refuses to
  remove evidence that a later run depends on.

Integration-specific bookkeeping lives in ``conv_*`` tables inside the same
database.  They are additive; the ATLAS tables are untouched by them.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from medradar.atlas.evidence.timeq import utc_iso
from medradar.atlas.store import AtlasStore

from .adapter import ConversionResult, HorizonToAtlasAdapter
from .licence import LicencePolicy

DEFAULT_STAGING_DB = Path("research/convergence/staging/convergence.sqlite")

_CONV_SCHEMA = """
CREATE TABLE IF NOT EXISTS conv_runs (
    run_id           TEXT PRIMARY KEY,
    export_id        TEXT NOT NULL DEFAULT '',
    manifest_sha256  TEXT NOT NULL DEFAULT '',
    contract_version TEXT NOT NULL DEFAULT '',
    mapping_version  TEXT NOT NULL DEFAULT '',
    policy_id        TEXT NOT NULL DEFAULT '',
    started_at       TEXT NOT NULL,
    finished_at      TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'running',
    records_seen     INTEGER NOT NULL DEFAULT 0,
    converted        INTEGER NOT NULL DEFAULT 0,
    degraded         INTEGER NOT NULL DEFAULT 0,
    rejected         INTEGER NOT NULL DEFAULT 0,
    evidence_inserted INTEGER NOT NULL DEFAULT 0,
    evidence_noop    INTEGER NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS conv_conversions (
    conversion_id    TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    occurrence       INTEGER NOT NULL DEFAULT 1,
    status           TEXT NOT NULL,
    reason           TEXT NOT NULL DEFAULT '',
    evidence_id      TEXT NOT NULL DEFAULT '',
    evidence_version INTEGER NOT NULL DEFAULT 0,
    canonical_key    TEXT NOT NULL DEFAULT '',
    canonical_entity TEXT NOT NULL DEFAULT '',
    licence_status   TEXT NOT NULL DEFAULT '',
    identity_status  TEXT NOT NULL DEFAULT '',
    relation_status  TEXT NOT NULL DEFAULT '',
    mapping_version  TEXT NOT NULL DEFAULT '',
    warnings_json    TEXT NOT NULL DEFAULT '[]',
    lost_fields_json TEXT NOT NULL DEFAULT '[]',
    preserved_json   TEXT NOT NULL DEFAULT '[]',
    extensions_json  TEXT NOT NULL DEFAULT '[]',
    relation_grades_json TEXT NOT NULL DEFAULT '[]',
    identifier_decisions_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS conv_rejections (
    rejection_id     TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    occurrence       INTEGER NOT NULL DEFAULT 1,
    reason           TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conv_conflicts (
    conflict_id      TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    evidence_id      TEXT NOT NULL DEFAULT '',
    canonical_key    TEXT NOT NULL DEFAULT '',
    detail_json      TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conv_dedupe (
    run_id   TEXT NOT NULL,
    layer    TEXT NOT NULL,
    key      TEXT NOT NULL,
    n        INTEGER NOT NULL,
    PRIMARY KEY (run_id, layer, key)
);

CREATE TABLE IF NOT EXISTS conv_relation_candidates (
    relation_id      TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    from_ref         TEXT NOT NULL,
    from_type        TEXT NOT NULL,
    to_ref           TEXT NOT NULL,
    to_type          TEXT NOT NULL,
    relation_type    TEXT NOT NULL,
    grade            TEXT NOT NULL,
    atlas_relation_status TEXT NOT NULL,
    may_set_confirmed_identity INTEGER NOT NULL,
    basis_json       TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_conv_src ON conv_conversions(source_id);
CREATE INDEX IF NOT EXISTS idx_conv_conv_ev ON conv_conversions(evidence_id);
CREATE INDEX IF NOT EXISTS idx_conv_conf_key ON conv_conflicts(canonical_key);
"""


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ConvergenceStore:
    """Isolated staging database plus ATLAS's append-only evidence store."""

    def __init__(self, path: Path | str = DEFAULT_STAGING_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.atlas = AtlasStore(self.path)
        self._ensure_conv_schema()

    # ---------------------------------------------------------------- schema
    def _ensure_conv_schema(self) -> None:
        # ``executescript`` issues its own COMMIT, so it must run outside
        # AtlasStore.transaction() rather than inside it.
        conn = self.atlas.connect()
        conn.executescript(_CONV_SCHEMA)
        conn.commit()

    def close(self) -> None:
        self.atlas.close()

    def __enter__(self) -> "ConvergenceStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ runs
    def begin_run(
        self,
        *,
        run_id: str,
        export_id: str = "",
        manifest_sha256: str = "",
        contract_version: str = "",
        mapping_version: str = "",
        policy_id: str = "",
        notes: str = "",
    ) -> str:
        conn = self.atlas.connect()
        with self.atlas.transaction():
            conn.execute(
                "INSERT INTO conv_runs(run_id, export_id, manifest_sha256, contract_version,"
                " mapping_version, policy_id, started_at, status, notes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)"
                " ON CONFLICT(run_id) DO UPDATE SET status='running', notes=excluded.notes",
                (
                    run_id,
                    export_id,
                    manifest_sha256,
                    contract_version,
                    mapping_version,
                    policy_id,
                    utc_iso(),
                    notes,
                ),
            )
        return run_id

    def close_run(self, run_id: str, *, status: str = "complete", notes: str = "") -> dict[str, Any]:
        conn = self.atlas.connect()
        with self.atlas.transaction():
            conn.execute(
                "UPDATE conv_runs SET finished_at=?, status=?,"
                " notes=CASE WHEN ?='' THEN notes ELSE ? END WHERE run_id=?",
                (utc_iso(), status, notes, notes, run_id),
            )
            conn.execute(
                "UPDATE conv_runs SET"
                " records_seen=(SELECT COUNT(*) FROM conv_conversions WHERE run_id=?),"
                " converted=(SELECT COUNT(*) FROM conv_conversions WHERE run_id=? AND status='converted'),"
                " degraded=(SELECT COUNT(*) FROM conv_conversions WHERE run_id=? AND status='degraded'),"
                " rejected=(SELECT COUNT(*) FROM conv_rejections WHERE run_id=?)"
                " WHERE run_id=?",
                (run_id, run_id, run_id, run_id, run_id),
            )
        return self.run_summary(run_id)

    def run_summary(self, run_id: str) -> dict[str, Any]:
        row = self.atlas.query("SELECT * FROM conv_runs WHERE run_id=?", (run_id,))
        return row[0] if row else {}

    def runs(self) -> list[dict[str, Any]]:
        return self.atlas.query("SELECT * FROM conv_runs ORDER BY started_at")

    # ----------------------------------------------------------- import loop
    def import_records(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        adapter: HorizonToAtlasAdapter,
        run_id: str,
        raw_lines: Iterable[bytes] | None = None,
    ) -> dict[str, Any]:
        """Convert and append records.  Idempotent; retains rejections."""
        summary = {
            "run_id": run_id,
            "seen": 0,
            "converted": 0,
            "degraded": 0,
            "rejected": 0,
            "evidence_inserted": 0,
            "evidence_noop": 0,
            "evidence_rows_appended": 0,
            "repeat_observations": 0,
            "conflicts": 0,
        }
        line_iter = iter(raw_lines) if raw_lines is not None else None
        occurrences: dict[tuple[str, str], int] = {}
        for record in records:
            summary["seen"] += 1
            raw_line = next(line_iter) if line_iter is not None else None
            result = adapter.adapt(record, run_id=run_id, raw_line=raw_line)
            key = (result.source_id, result.source_record_id)
            occurrences[key] = occurrences.get(key, 0) + 1
            occurrence = occurrences[key]
            if occurrence > 1:
                summary["repeat_observations"] += 1
            self.record_conversion(
                run_id, result, raw_record=record, occurrence=occurrence
            )
            if not result.ok:
                summary["rejected"] += 1
                continue
            summary[result.status] += 1
            outcome = self.atlas.append_evidence(result.evidence, run_id=run_id)
            if outcome.get("inserted"):
                summary["evidence_inserted"] += 1
            else:
                summary["evidence_noop"] += 1
            summary["conflicts"] += self._detect_conflicts(run_id, result.evidence)
        summary["evidence_rows_appended"] = summary["converted"] + summary["degraded"]
        conn = self.atlas.connect()
        with self.atlas.transaction():
            conn.execute(
                "UPDATE conv_runs SET evidence_inserted=?, evidence_noop=? WHERE run_id=?",
                (summary["evidence_inserted"], summary["evidence_noop"], run_id),
            )
        return summary

    def record_conversion(
        self,
        run_id: str,
        result: ConversionResult,
        *,
        raw_record: Mapping[str, Any] | None = None,
        occurrence: int = 1,
    ) -> None:
        """Store the conversion outcome for one source record occurrence.

        ``occurrence`` exists because the HORIZON export contains repeated
        (source_id, source_record_id) pairs — the same PMA or establishment
        record was collected once per firm slice and emitted again.  Those are
        separate *observations* of one record and must not overwrite each other
        in the audit trail, even though ATLAS correctly versions them under one
        evidence id.
        """
        conn = self.atlas.connect()
        evidence = result.evidence or {}
        manifest = result.as_manifest_row()
        conversion_id = f"{run_id}|{result.source_id}|{result.source_record_id}|{occurrence}"
        with self.atlas.transaction():
            conn.execute(
                "INSERT OR REPLACE INTO conv_conversions(conversion_id, run_id, source_id,"
                " source_record_id, occurrence, status, reason, evidence_id, evidence_version,"
                " canonical_key, canonical_entity, licence_status, identity_status,"
                " relation_status, mapping_version, warnings_json, lost_fields_json,"
                " preserved_json, extensions_json, relation_grades_json,"
                " identifier_decisions_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    conversion_id,
                    run_id,
                    result.source_id,
                    result.source_record_id,
                    occurrence,
                    result.status,
                    result.reason,
                    evidence.get("evidence_id", ""),
                    int(evidence.get("version", 0) or 0),
                    evidence.get("canonical_key") or "",
                    evidence.get("canonical_entity_id") or "",
                    evidence.get("licence_status", ""),
                    evidence.get("identity_resolution_status", ""),
                    evidence.get("relation_status", ""),
                    result.mapping_version,
                    _json(manifest["warnings"]),
                    _json(manifest["lost_fields"]),
                    _json(manifest["preserved_fields"]),
                    _json(manifest["extension_fields"]),
                    _json(manifest["relation_grades"]),
                    _json(result.identifier_decisions),
                ),
            )
            if not result.ok:
                conn.execute(
                    "INSERT OR REPLACE INTO conv_rejections(rejection_id, run_id, source_id,"
                    " source_record_id, occurrence, reason, payload_json, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"rej|{conversion_id}",
                        run_id,
                        result.source_id,
                        result.source_record_id,
                        occurrence,
                        result.reason,
                        _json(dict(raw_record or {})),
                        utc_iso(),
                    ),
                )

    def _detect_conflicts(self, run_id: str, evidence: Mapping[str, Any]) -> int:
        """Record disagreements that a re-import must not silently overwrite."""
        conn = self.atlas.connect()
        found = 0
        canonical = evidence.get("canonical_key") or ""
        if canonical:
            others = self.atlas.query(
                "SELECT DISTINCT source_id FROM evidence WHERE canonical_key=? AND source_id<>?",
                (canonical, evidence.get("source_id")),
            )
            if len(others) > 1:
                conflict_id = f"cf_{run_id}_{canonical}".replace(":", "_")
                with self.atlas.transaction():
                    conn.execute(
                        "INSERT OR REPLACE INTO conv_conflicts(conflict_id, run_id, kind,"
                        " evidence_id, canonical_key, detail_json, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            conflict_id,
                            run_id,
                            "many_sources_same_canonical_key",
                            evidence.get("evidence_id", ""),
                            canonical,
                            _json({"sources": sorted(r["source_id"] for r in others)}),
                            utc_iso(),
                        ),
                    )
                found += 1
        return found

    def record_relation_candidate(
        self,
        *,
        run_id: str,
        relation_id: str,
        from_ref: str,
        from_type: str,
        to_ref: str,
        to_type: str,
        relation_type: str,
        grade: str,
        atlas_relation_status: str,
        may_set_confirmed_identity: bool,
        basis: Mapping[str, Any],
    ) -> None:
        conn = self.atlas.connect()
        with self.atlas.transaction():
            conn.execute(
                "INSERT OR REPLACE INTO conv_relation_candidates(relation_id, run_id, from_ref,"
                " from_type, to_ref, to_type, relation_type, grade, atlas_relation_status,"
                " may_set_confirmed_identity, basis_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    relation_id,
                    run_id,
                    from_ref,
                    from_type,
                    to_ref,
                    to_type,
                    relation_type,
                    grade,
                    atlas_relation_status,
                    1 if may_set_confirmed_identity else 0,
                    _json(dict(basis)),
                    utc_iso(),
                ),
            )

    # -------------------------------------------------------------- rollback
    def rollback_run(self, run_id: str, *, force: bool = False) -> dict[str, Any]:
        """Remove one import run's rows, refusing to break later runs.

        Only the most recent run may be rolled back unless ``force`` is set,
        because ATLAS evidence is append-only and a later run may have built on
        these versions.
        """
        runs = self.runs()
        completed = [r for r in runs if r.get("status") != "running"]
        if not completed:
            return {"rolled_back": False, "reason": "no_completed_runs"}
        latest = completed[-1]["run_id"]
        if run_id != latest and not force:
            return {
                "rolled_back": False,
                "reason": f"run {run_id} is not the latest completed run ({latest})",
            }
        conn = self.atlas.connect()
        with self.atlas.transaction():
            evidence_rows = conn.execute(
                "SELECT evidence_id, version FROM evidence WHERE run_id=?", (run_id,)
            ).fetchall()
            deleted_evidence = 0
            for row in evidence_rows:
                eid, version = row["evidence_id"], row["version"]
                # ATLAS versions count upward; a row is removable only if it is
                # the newest version of that evidence id.
                newer = conn.execute(
                    "SELECT 1 FROM evidence WHERE evidence_id=? AND version=?", (eid, version + 1)
                ).fetchone()
                if newer:
                    continue
                conn.execute("DELETE FROM evidence WHERE evidence_id=? AND version=?", (eid, version))
                conn.execute("DELETE FROM evidence_identifiers WHERE evidence_id=? AND version=?", (eid, version))
                deleted_evidence += 1
                remaining = conn.execute(
                    "SELECT MAX(version) AS v, COUNT(*) AS n FROM evidence WHERE evidence_id=?",
                    (eid,),
                ).fetchone()
                if remaining["n"]:
                    conn.execute("UPDATE evidence_head SET latest_version=? WHERE evidence_id=?", (remaining["v"], eid))
                else:
                    conn.execute("DELETE FROM evidence_head WHERE evidence_id=?", (eid,))
            counts = {
                "evidence_rows_deleted": deleted_evidence,
                "conversions_deleted": conn.execute(
                    "DELETE FROM conv_conversions WHERE run_id=?", (run_id,)
                ).rowcount,
                "rejections_deleted": conn.execute(
                    "DELETE FROM conv_rejections WHERE run_id=?", (run_id,)
                ).rowcount,
                "conflicts_deleted": conn.execute(
                    "DELETE FROM conv_conflicts WHERE run_id=?", (run_id,)
                ).rowcount,
                "relation_candidates_deleted": conn.execute(
                    "DELETE FROM conv_relation_candidates WHERE run_id=?", (run_id,)
                ).rowcount,
            }
            conn.execute("UPDATE conv_runs SET status='rolled_back' WHERE run_id=?", (run_id,))
        return {"rolled_back": True, **counts}

    # ----------------------------------------------------------------- stats
    def stats(self) -> dict[str, Any]:
        base = self.atlas.stats()
        extra = {
            "conv_runs": self.atlas.query("SELECT COUNT(*) AS n FROM conv_runs")[0]["n"],
            "conv_evidence_inserted": self.atlas.query(
                "SELECT COALESCE(SUM(evidence_inserted),0) AS n FROM conv_runs"
            )[0]["n"],
            "conv_rejections": self.atlas.query("SELECT COUNT(*) AS n FROM conv_rejections")[0]["n"],
            "conv_conflicts": self.atlas.query("SELECT COUNT(*) AS n FROM conv_conflicts")[0]["n"],
            "conv_relation_candidates": self.atlas.query(
                "SELECT COUNT(*) AS n FROM conv_relation_candidates"
            )[0]["n"],
            "conv_by_source": {
                row["source_id"]: row["n"]
                for row in self.atlas.query(
                    "SELECT source_id, COUNT(*) AS n FROM conv_conversions"
                    " WHERE status IN ('converted','degraded') GROUP BY source_id ORDER BY n DESC"
                )
            },
            "conv_rejection_reasons": {
                row["reason"]: row["n"]
                for row in self.atlas.query(
                    "SELECT reason, COUNT(*) AS n FROM conv_rejections GROUP BY reason ORDER BY n DESC"
                )
            },
            "conv_identity_status": {
                row["identity_status"]: row["n"]
                for row in self.atlas.query(
                    "SELECT identity_status, COUNT(*) AS n FROM conv_conversions GROUP BY 1"
                )
            },
            "conv_licence_status": {
                row["licence_status"]: row["n"]
                for row in self.atlas.query(
                    "SELECT licence_status, COUNT(*) AS n FROM conv_conversions GROUP BY 1"
                )
            },
        }
        return {**base, **extra}


__all__ = ["ConvergenceStore", "DEFAULT_STAGING_DB"]
