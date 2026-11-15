"""Attribution and coverage metrics, with the definitions the product is allowed to claim.

Why this module exists
----------------------
PRODUCT-001 reported one number - 99.92% - and called it attribution. It was Attributed Share: the
share of the *collected sample* that carries an organization attribution. It said nothing about
whether the attribution is correct, whether it was reviewed, or how much of the FDA population was
retrieved. PRODUCT-002 computes each of those things separately, at three levels (record,
applicant string, organization), and returns UNKNOWN rather than a number when the data needed for
a claim does not exist.

Every value here is derived from the loaded dataset, so the API, the exports and the UI cannot
disagree about it.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .attribution import status as status_module

ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = ROOT / "docs" / "product" / "product_002" / "validation"
PRECISION_FILE = VALIDATION_DIR / "precision.json"


def _share(numerator: int | float, denominator: int | float | None) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 6)


def _pct(value: float | None) -> str:
    return "UNKNOWN" if value is None else format(value * 100.0, ".2f") + "%"


def _level_record(dataset: Any) -> dict[str, Any]:
    events = [event for event in dataset.events if event.organization_key]
    total_collected = len(dataset.events)
    by_status: dict[str, int] = {}
    by_event_type: dict[str, dict[str, int]] = {}
    by_source: dict[str, dict[str, int]] = {}
    for event in events:
        status = event.attribution_verification
        by_status[status] = by_status.get(status, 0) + 1
        bucket = by_event_type.setdefault(event.event_type, {})
        bucket[status] = bucket.get(status, 0) + 1
        bucket["records"] = bucket.get("records", 0) + 1
        bucket["verified"] = bucket.get("verified", 0) + (1 if event.attribution_verified else 0)
        source_bucket = by_source.setdefault(event.source_id, {})
        source_bucket["records"] = source_bucket.get("records", 0) + 1
        source_bucket["verified"] = source_bucket.get("verified", 0) + (1 if event.attribution_verified else 0)
    verified = sum(1 for event in events if event.attribution_verified)
    rule_verified = sum(
        1 for event in events if event.attribution_verification == status_module.RULE_VERIFIED
    )
    proposed = sum(
        1 for event in events if event.attribution_verification in status_module.PROVISIONAL_STATUSES
    )
    return {
        "collected_records": total_collected,
        "attributed_records": len(events),
        "attributed_share": _share(len(events), total_collected),
        "verified_records": verified,
        "curated_share": _share(verified, len(events)),
        "rule_verified_records": rule_verified,
        "rule_verified_share": _share(rule_verified, len(events)),
        "provisional_records": proposed,
        "provisional_share": _share(proposed, len(events)),
        "by_status": {name: by_status.get(name, 0) for name in status_module.DECISION_STATUSES},
        "by_event_type": by_event_type,
        "by_source": by_source,
    }


def _level_applicant(dataset: Any) -> dict[str, Any]:
    rows = dataset.applicants
    registry = dataset.registry
    total_records = sum(int(row.get("records") or 0) for row in rows)
    attributed: list[tuple[str, int, str]] = []
    for row in rows:
        decision, _rejection = registry.decide(str(row.get("applicant_name") or ""))
        if decision is None:
            continue
        attributed.append((decision.applicant_name, int(row.get("records") or 0), decision.status))
    attributed_records = sum(item[1] for item in attributed)
    by_status: dict[str, int] = {}
    for _name, count, status in attributed:
        by_status[status] = by_status.get(status, 0) + count
    verified_records = sum(count for _name, count, status in attributed if status in status_module.CURATED_STATUSES)
    rule_records = sum(count for _name, count, status in attributed if status == status_module.RULE_VERIFIED)
    ordered = sorted(attributed, key=lambda item: -item[1])
    top10 = sum(count for _name, count, _status in ordered[:10])
    spelled = [item for item in registry.decisions.values()]
    verified_spellings = sum(1 for item in spelled if item.verified)
    rule_spellings = sum(1 for item in spelled if item.rule_verified)
    return {
        "applicant_strings_observed": len(rows),
        "attributed_applicant_strings": len(attributed),
        "attributed_applicant_share": _share(len(attributed), len(rows)),
        "accepted_spellings_in_registry": len(spelled),
        "verified_spellings": verified_spellings,
        "verified_spelling_share": _share(verified_spellings, len(spelled)),
        "rule_verified_spellings": rule_spellings,
        "rule_verified_spelling_share": _share(rule_spellings, len(spelled)),
        "attributed_records": attributed_records,
        "verified_record_share": _share(verified_records, attributed_records),
        "rule_verified_record_share": _share(rule_records, attributed_records),
        "top10_applicant_record_share": _share(top10, total_records),
        "largest_applicant_record_share": _share(ordered[0][1] if ordered else 0, total_records),
        "largest_applicant": ordered[0][0] if ordered else None,
        "by_status": {name: by_status.get(name, 0) for name in status_module.DECISION_STATUSES},
        "concentration_note": "Top-10 applicants carry "
        + _pct(_share(top10, total_records))
        + " of the collected records; a single applicant carries "
        + _pct(_share(ordered[0][1] if ordered else 0, total_records))
        + ". Record-weighted metrics are dominated by a few high-volume applicants, which is why applicant-level and organization-level metrics are reported separately.",
    }


def _level_organization(dataset: Any) -> dict[str, Any]:
    orgs = list(dataset.registry.organizations)
    shares: list[float] = []
    with_records = 0
    with_zero_verified = 0
    provisional_only = 0
    for org in orgs:
        stats = dataset.org_stats.get(org.key)
        records = stats.counts["records"] if stats else 0
        if not records:
            continue
        with_records += 1
        share = stats.counts.get("curated_share")
        if share is not None:
            shares.append(float(share))
        if stats.verified_records == 0:
            with_zero_verified += 1
        if stats.proposed_records == records:
            provisional_only += 1
    return {
        "tracked_organizations": len(orgs),
        "organizations_with_records": with_records,
        "organizations_with_records_share": _share(with_records, len(orgs)),
        "median_curated_share": round(statistics.median(shares), 6) if shares else None,
        "min_curated_share": round(min(shares), 6) if shares else None,
        "max_curated_share": round(max(shares), 6) if shares else None,
        "organizations_with_zero_verified_records": with_zero_verified,
        "organizations_whose_records_are_all_provisional": provisional_only,
        "note": "An organization-level share is the share of that organization's attributed records whose mapping is evidence-verified or human-reviewed. The median is used so a single high-volume applicant cannot speak for the portfolio.",
    }


def estimated_attribution_precision() -> dict[str, Any]:
    """Read the completed independent sample review, or return an explicit UNKNOWN."""
    if not PRECISION_FILE.is_file():
        return {
            "state": "unknown",
            "estimate": None,
            "confidence_interval_95": None,
            "sample_size": 0,
            "decidable_sample_size": 0,
            "undecidable": None,
            "reviewer_kind": None,
            "reason": "No completed independent sample review is recorded. Attributed Share is not a precision estimate and is never substituted for one.",
            "protocol": "docs/product/product_002/IDENTITY_REVIEW_PROTOCOL.md",
            "required_artifact": str(PRECISION_FILE.relative_to(ROOT)) if PRECISION_FILE.is_relative_to(ROOT) else str(PRECISION_FILE),
        }
    payload = json.loads(PRECISION_FILE.read_text(encoding="utf-8"))
    payload.setdefault("state", "unknown")
    return payload


def retrieval_coverage(dataset: Any) -> dict[str, Any]:
    """Retrieval coverage against a sampling frame, or UNKNOWN when no frame exists."""
    return {
        "state": "unknown",
        "value": None,
        "reason": "The product has no independent denominator for 'every FDA record that should have been retrieved for this organization': the openFDA endpoints return records by applicant-name query, and no authoritative per-organization register of expected records exists in this release. A ratio computed only from what was retrieved cannot measure what was missed.",
        "what_would_be_needed": [
            "An independent frame of expected FDA record identifiers per organization (for example an official establishment/ownership register joined to the submission identifiers).",
            "A pre-registered query strategy per source, so a recalled record can be attributed to a query rather than to the name as it appears.",
            "For 510(k)/PMA: a deterministic enumeration of official identifiers by date window, then a presence/absence check against the retrieved set.",
        ],
        "what_is_known": {
            "collected_records": len(dataset.events),
            "distinct_official_ids": len({event.official_id for event in dataset.events if event.official_id}),
            "query_count": int((dataset.manifest or {}).get("request_count") or 0),
            "organizations_queried": int((dataset.manifest or {}).get("organization_count") or 0),
            "sources": sorted({event.source_id for event in dataset.events}),
        },
        "not_the_same_as": "Attributed Share, which only measures the collected sample.",
    }


def attribution_metrics(dataset: Any) -> dict[str, Any]:
    record = _level_record(dataset)
    applicant = _level_applicant(dataset)
    organization = _level_organization(dataset)
    precision = estimated_attribution_precision()
    retrieval = retrieval_coverage(dataset)
    warnings: list[str] = []
    if record["curated_share"] is not None and record["curated_share"] < 0.5:
        warnings.append(
            "Less than half of the attributed records rest on independent verification: counted activity for most organizations is provisional at the record level."
        )
    if record["attributed_share"] is not None and record["attributed_share"] > 0.99:
        warnings.append(
            "Attributed Share is above 99% of the collected sample; this is expected because the sample was collected by querying the tracked organizations' own names. It is not a coverage or precision claim."
        )
    if precision.get("state") == "unknown":
        warnings.append(
            "Estimated Attribution Precision is UNKNOWN: no completed independent sample review exists in this release."
        )
    return {
        "snapshot": dataset.snapshot_ref(),
        "collected_at": dataset.collected_at,
        "definitions": status_module.metric_definitions(),
        "status_vocabulary": status_module.status_summary(record["by_status"]),
        "levels": {
            "record": record,
            "applicant": applicant,
            "organization": organization,
        },
        "estimated_attribution_precision": precision,
        "retrieval_coverage": retrieval,
        "ownership_basis": {
            "current_group": "default: every record attributed to the organization today, including acquired predecessor entities",
            "original_registrant": "records filed under the organization's own applicant identities only; available as a filter and in the comparison",
        },
        "warnings": warnings,
        "review_ledger": {
            "decisions_applied": getattr(dataset, "review_overlay_applied", 0),
            "db": getattr(dataset, "review_db", None),
        },
    }


def summarise(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Compact form for headers, exports and the overview page."""
    record = metrics["levels"]["record"]
    applicant = metrics["levels"]["applicant"]
    organization = metrics["levels"]["organization"]
    precision = metrics["estimated_attribution_precision"]
    return {
        "attributed_share": record["attributed_share"],
        "curated_share": record["curated_share"],
        "rule_verified_share": record["rule_verified_share"],
        "provisional_share": record["provisional_share"],
        "attributed_records": record["attributed_records"],
        "collected_records": record["collected_records"],
        "verified_records": record["verified_records"],
        "rule_verified_records": record["rule_verified_records"],
        "provisional_records": record["provisional_records"],
        "applicant_attributed_share": applicant["attributed_applicant_share"],
        "applicant_verified_spelling_share": applicant["verified_spelling_share"],
        "organization_median_curated_share": organization["median_curated_share"],
        "estimated_attribution_precision": {
            "state": precision.get("state"),
            "estimate": precision.get("estimate"),
            "confidence_interval_95": precision.get("confidence_interval_95"),
            "sample_size": precision.get("sample_size"),
            "reviewer_kind": precision.get("reviewer_kind"),
        },
        "retrieval_coverage": {"state": metrics["retrieval_coverage"]["state"], "value": None},
    }
