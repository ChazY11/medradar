"""Automated data-quality checks.

A quality check exists to stop two specific mistakes:

1. **Silence read as absence.**  A failed request must produce a finding, never
   "zero new events".  ``check_collection_completeness`` compares the database's
   run log against the evidence it produced.
2. **Confident-looking disagreement.**  Two records can assert the same official
   identifier while disagreeing on the device's name/model; that is a
   contradiction to surface, not to average away.

Every check returns findings; the runner persists them and writes a machine
report.  Checks are deterministic and read only the database, so an independent
process can rerun them.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..evidence import schema as ev
from ..store import AtlasStore


@dataclass(frozen=True)
class Finding:
    check_id: str
    severity: str  # info | warning | error
    subject: str
    detail: str
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "subject": self.subject,
            "detail": self.detail,
            "evidence_ids": list(self.evidence_ids),
        }


def check_duplicate_records(store: AtlasStore) -> list[Finding]:
    """Same-source duplicates are a data-quality defect; cross-source ones are
    the expected upstream dedupe and are reported once, in aggregate."""
    out: list[Finding] = []
    same_source = store.query(
        "SELECT canonical_key, source_id, COUNT(*) AS n, GROUP_CONCAT(evidence_id) AS ids"
        " FROM evidence_head WHERE canonical_key IS NOT NULL"
        " GROUP BY canonical_key, source_id HAVING n > 1"
    )
    for row in same_source[:50]:
        out.append(
            Finding(
                "duplicate_same_source", "warning", str(row["canonical_key"]),
                f"{row['n']} records from {row['source_id']} share canonical key {row['canonical_key']}",
                tuple(str(row["ids"]).split(",")),
            )
        )
    cross = store.query(
        "SELECT canonical_key, COUNT(DISTINCT source_id) AS sources, COUNT(*) AS n"
        " FROM evidence_head WHERE canonical_key IS NOT NULL"
        " GROUP BY canonical_key HAVING sources > 1"
    )
    if cross:
        out.append(
            Finding(
                "duplicate_cross_source_expected", "info", "canonical_key",
                f"{len(cross)} canonical keys appear in more than one source; "
                "these are deduplicated upstream observations, not independent corroboration",
            )
        )
    return out


def check_missing_fields(store: AtlasStore) -> list[Finding]:
    """Aggregate per source: 5,000 identical rows is one finding, not 5,000."""
    out: list[Finding] = []
    for row in store.query(
        "SELECT source_id, COUNT(*) AS n FROM evidence_head WHERE canonical_key IS NULL"
        " GROUP BY source_id"
    ):
        out.append(
            Finding("missing_primary_identifier", "warning", str(row["source_id"]),
                    f"{row['n']} records from {row['source_id']} have no authoritative identifier")
        )
    for row in store.query(
        "SELECT h.source_id AS source_id, COUNT(*) AS n FROM evidence_head h WHERE h.evidence_id NOT IN"
        " (SELECT DISTINCT evidence_id FROM evidence_entity_refs WHERE method<>'none')"
        " GROUP BY h.source_id"
    ):
        out.append(
            Finding("missing_company_link", "info", str(row["source_id"]),
                    f"{row['n']} records from {row['source_id']} have no resolved target-firm company "
                    "(expected for records outside the five-firm pilot)")
        )
    return out


def check_time_anomalies(store: AtlasStore) -> list[Finding]:
    """Impossible orderings and clock fabrication."""
    out: list[Finding] = []
    rows = store.query(
        "SELECT evidence_id, event_at, source_public_at, first_observed_at, fetched_at,"
        " time_quality FROM evidence WHERE 1=1"
    )
    for row in rows:
        public = str(row["source_public_at"] or "")
        fetched = str(row["fetched_at"] or "")
        observed = str(row["first_observed_at"] or "")
        if public and fetched and public[:10] > fetched[:10]:
            out.append(Finding("time_public_after_fetch", "error", str(row["evidence_id"]),
                               f"source_public_at {public} is after fetched_at {fetched}"))
        if observed and fetched and observed[:10] > fetched[:10]:
            out.append(Finding("time_observed_after_fetch", "error", str(row["evidence_id"]),
                               f"first_observed_at {observed} is after fetched_at {fetched}"))
        if row["time_quality"] == "unknown" and public:
            out.append(Finding("time_quality_unknown_with_date", "warning", str(row["evidence_id"]),
                               f"public date {public} recorded with quality=unknown"))
        # A record whose first_observed_at equals its event date is almost
        # always a backfill that copied the event clock into the observation
        # clock.  Only flag it when the two agree exactly and the event is old.
        event = str(row["event_at"] or "")
        if event and observed and event[:10] == observed[:10] and event[:4] < observed[:4]:
            out.append(Finding("possible_clock_copy", "warning", str(row["evidence_id"]),
                               "event_at and first_observed_at share a date but not a year"))
    return out


def check_identity_contradictions(store: AtlasStore) -> list[Finding]:
    out: list[Finding] = []
    rows = store.query(
        "SELECT relation_id, contradictions_json, confidence FROM entity_relations"
        " WHERE contradictions_json NOT IN ('[]','') AND revoked_at=''"
    )
    for row in rows:
        out.append(
            Finding("identity_contradiction", "error", str(row["relation_id"]),
                    f"relation has contradictions: {row['contradictions_json']}")
        )
    return out


def check_alias_conflicts(store: AtlasStore) -> list[Finding]:
    """One company name string resolving to more than one canonical company."""
    rows = store.query(
        "SELECT name, COUNT(DISTINCT company_id) AS n, GROUP_CONCAT(company_id) AS ids"
        " FROM company_names GROUP BY name HAVING n > 1"
    )
    return [
        Finding("company_name_conflict", "error", str(row["name"]),
                f"name maps to {row['n']} companies: {row['ids']}")
        for row in rows
    ]


def check_collection_completeness(store: AtlasStore) -> list[Finding]:
    """Failed runs and unsuccessful requests are findings, not empty results."""
    out: list[Finding] = []
    for row in store.query(
        "SELECT run_id, connector_id, status, requests, records, notes FROM collection_runs"
        " WHERE status NOT IN ('ok')"
    ):
        out.append(
            Finding("collection_run_not_ok", "error", str(row["run_id"]),
                    f"{row['connector_id']} status={row['status']} requests={row['requests']}"
                    f" records={row['records']} notes={row['notes']}")
        )
    for row in store.query(
        "SELECT run_id, COUNT(*) AS n FROM request_log WHERE status IS NULL OR status>=400"
        " GROUP BY run_id"
    ):
        out.append(
            Finding("request_failures", "warning", str(row["run_id"]),
                    f"{row['n']} failed requests recorded in this run")
        )
    for row in store.query(
        "SELECT run_id, source_id, records, requests FROM collection_runs WHERE status='ok'"
        " AND records=0 AND requests>0"
    ):
        out.append(
            Finding("zero_records_with_requests", "warning", str(row["run_id"]),
                    f"{row['source_id']}: {row['requests']} requests produced 0 records")
        )
    return out


def check_source_availability(store: AtlasStore) -> list[Finding]:
    out: list[Finding] = []
    for row in store.query("SELECT check_id, source_id, status, detail FROM source_status"):
        if row["status"] not in {"VERIFIED_API", "VERIFIED_BULK_DOWNLOAD", "VERIFIED_PUBLIC_QUERY"}:
            out.append(
                Finding("source_not_available", "warning", str(row["check_id"]),
                        f"{row['source_id']}: {row['status']} {row['detail']}")
            )
    return out


def check_growth_anomaly(store: AtlasStore) -> list[Finding]:
    """Flag a run that produced an implausibly large share of all evidence."""
    totals = store.query(
        "SELECT run_id, COUNT(*) AS n FROM evidence GROUP BY run_id ORDER BY n DESC"
    )
    if not totals:
        return []
    counts = [int(r["n"]) for r in totals]
    total = sum(counts)
    if total < 100:
        return []
    median = statistics.median(counts)
    out = []
    for row in totals:
        if int(row["n"]) > max(20 * median, 0.9 * total):
            out.append(
                Finding("run_growth_anomaly", "warning", str(row["run_id"]),
                        f"run produced {row['n']} of {total} evidence rows (median run {median})")
            )
    return out


def check_licence_restrictions(store: AtlasStore) -> list[Finding]:
    out = []
    for row in store.query(
        "SELECT h.evidence_id AS evidence_id, h.source_id AS source_id,"
        " e.licence_status AS licence_status FROM evidence_head h JOIN evidence e"
        " ON e.evidence_id=h.evidence_id AND e.version=h.latest_version"
        " WHERE e.licence_status='restricted'"
    ):
        out.append(
            Finding("restricted_source_record", "error", str(row["evidence_id"]),
                    f"{row['source_id']} is restricted; raw content must not be published")
        )
    return out


CHECKS = (
    check_duplicate_records,
    check_missing_fields,
    check_time_anomalies,
    check_identity_contradictions,
    check_alias_conflicts,
    check_collection_completeness,
    check_source_availability,
    check_growth_anomaly,
    check_licence_restrictions,
)


def run_checks(store: AtlasStore, *, run_id: str = "") -> dict[str, Any]:
    findings: list[Finding] = []
    for check in CHECKS:
        try:
            findings.extend(check(store))
        except Exception as exc:  # a broken check must not hide the dataset
            findings.append(
                Finding(
                    f"check_failed:{check.__name__}", "error", check.__name__,
                    f"check raised {type(exc).__name__}: {exc}",
                )
            )
    for finding in findings:
        store.add_quality_finding(
            check_id=finding.check_id,
            severity=finding.severity,
            subject=finding.subject,
            detail=finding.detail,
            evidence_ids=finding.evidence_ids,
            run_id=run_id,
        )
    by_severity: dict[str, int] = {}
    by_check: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
        by_check[finding.check_id] = by_check.get(finding.check_id, 0) + 1
    return {
        "schema": "medradar.atlas.quality_report.v1",
        "checks_run": [check.__name__ for check in CHECKS],
        "findings": [f.to_dict() for f in findings],
        "counts": {"total": len(findings), "by_severity": by_severity, "by_check": by_check},
        "note": "A failed collection produces an error finding; it is never reported as zero events.",
    }


__all__ = ["CHECKS", "Finding", "run_checks"]
