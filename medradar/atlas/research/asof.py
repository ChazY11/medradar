"""Historical-state queries (``as_of``) with explicit epistemic labels.

A single snapshot cannot be replayed into a point-in-time database.  This module
therefore answers three *different* questions and never merges them:

``observed``
    Records whose ``first_observed_at`` is at or before T.  This is what
    MedRadar had actually seen.
``public_inferred``
    Records whose ``source_public_at`` is at or before T **and** whose date
    quality is ``exact``/``day``.  This is what a third party *could* have seen;
    it is inference, not observation, and it is labelled that way.
``unprovable``
    Records with no usable public date (missing, coarse, derived or unknown).
    They are reported as unprovable rather than silently placed on one side.

The function also refuses to pretend a backfill is a history: if T precedes the
earliest observation in the database, the answer is "nothing was observable by
MedRadar at T", with the boundary date stated.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..evidence.timeq import parse_datetime, utc_iso
from ..store import AtlasStore

OBSERVED = "observed"
PUBLIC_INFERRED = "public_inferred"
UNPROVABLE = "unprovable"
BASES = frozenset({OBSERVED, PUBLIC_INFERRED})


def as_of(store: AtlasStore, timestamp: str, *, basis: str = OBSERVED) -> dict[str, Any]:
    """Return the evidence set knowable at ``timestamp`` under one explicit basis."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {sorted(BASES)}, got {basis!r}")
    moment = parse_datetime(timestamp)
    if moment is None:
        raise ValueError(f"unparseable timestamp: {timestamp!r}")
    t = moment.isoformat().replace("+00:00", "Z")

    earliest = store.query("SELECT MIN(first_observed_at) AS t FROM evidence_head")[0]["t"]
    boundary = {
        "requested_at": t,
        "basis": basis,
        "earliest_observation_in_db": earliest or "",
        "capture_starts_at": earliest or "",
    }
    # The capture boundary only answers the *observed* question.  Public
    # visibility can still be inferred before the capture began, which is
    # precisely why the two bases must never be merged.
    if basis == OBSERVED and earliest and str(earliest) > t:
        boundary["answer"] = "nothing could have been observed by MedRadar at this time"
        boundary["records"] = []
        return {
            "schema": "medradar.atlas.as_of.v1",
            "boundary": boundary,
            "counts": {"observed": 0, "public_inferred": 0, "unprovable": 0, "total": 0},
            "by_source": {},
            "by_type": {},
            "sample": [],
            "caveats": [
                "The database begins after the requested date; this is a capture boundary, not a history."
            ],
        }

    versions = store.query(
        "SELECT e.evidence_id, e.version, e.source_id, e.evidence_type, e.source_public_at,"
        " e.first_observed_at, e.fetched_at, e.time_quality, e.payload_json, h.latest_version"
        " FROM evidence e JOIN evidence_head h ON h.evidence_id=e.evidence_id"
        " ORDER BY e.evidence_id, e.version"
    )
    # Choose, per evidence id, the latest version known.  For the *observed*
    # basis a version fetched after T is not yet known and is excluded; for the
    # *public* basis the fetch clock is irrelevant — what matters is whether
    # the source record was public by T.
    chosen: dict[str, dict[str, Any]] = {}
    for row in versions:
        if basis == OBSERVED and str(row["fetched_at"] or "") > t:
            continue
        chosen[str(row["evidence_id"])] = dict(row)

    observed: list[dict[str, Any]] = []
    public_inferred: list[dict[str, Any]] = []
    unprovable: list[dict[str, Any]] = []
    for row in chosen.values():
        public = str(row["source_public_at"] or "")
        quality = str(row["time_quality"] or "unknown")
        if public and quality in {"exact", "day"} and public <= t:
            public_inferred.append(row)
        elif public and quality in {"coarse", "derived"} and public <= t:
            unprovable.append(row)
        elif not public:
            unprovable.append(row)
        if str(row["first_observed_at"] or "") <= t:
            observed.append(row)

    primary = observed if basis == OBSERVED else public_inferred
    other = public_inferred if basis == OBSERVED else observed
    payload = [json.loads(row["payload_json"]) for row in primary]
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for record in payload:
        by_source[record["source_id"]] = by_source.get(record["source_id"], 0) + 1
        by_type[record["evidence_type"]] = by_type.get(record["evidence_type"], 0) + 1
    return {
        "schema": "medradar.atlas.as_of.v1",
        "boundary": boundary,
        "counts": {
            "observed": len(observed),
            "public_inferred": len(public_inferred),
            "unprovable": len(unprovable),
            "total_versions_known_by_t": len(chosen),
            "primary_basis_count": len(primary),
            "alternative_basis_count": len(other),
        },
        "by_source": dict(sorted(by_source.items())),
        "by_type": dict(sorted(by_type.items())),
        "sample": [
            {
                "evidence_id": r["evidence_id"],
                "source_id": r["source_id"],
                "evidence_type": r["evidence_type"],
                "source_public_at": r["time"]["source_public_at"],
                "first_observed_at": r["time"]["first_observed_at"],
            }
            for r in payload[:25]
        ],
        "caveats": [
            "observed = first_observed_at <= T; it is a fetch clock, not a publication clock.",
            "public_inferred = source_public_at <= T with exact/day quality; it is what a third party could have seen, not proof that MedRadar saw it.",
            "records with coarse/derived/missing public dates are kept in 'unprovable' and are never promoted.",
            "one database capture cannot replay source revisions that were never observed.",
        ],
    }


def evidence_history(store: AtlasStore, evidence_id: str) -> dict[str, Any]:
    rows = store.query(
        "SELECT version, content_hash, fetched_at, first_observed_at, source_public_at,"
        " time_quality, identity_status, relation_status FROM evidence"
        " WHERE evidence_id=? ORDER BY version",
        (evidence_id,),
    )
    records = []
    for row in rows:
        record = store.get_evidence(evidence_id, int(row["version"]))
        records.append(
            {
                **dict(row),
                "quality_flags": record.get("quality_flags", []) if record else [],
                "normalized": record.get("normalized", {}) if record else {},
            }
        )
    return {
        "query": "evidence_history",
        "evidence_id": evidence_id,
        "versions": len(records),
        "timeline": records,
        "note": "Versions are append-only; a content change adds a version rather than overwriting.",
    }


__all__ = ["BASES", "OBSERVED", "PUBLIC_INFERRED", "UNPROVABLE", "as_of", "evidence_history"]
