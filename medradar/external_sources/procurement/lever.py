"""Lever postings API — hiring evidence with a department field (sometimes).

Endpoint
--------
``GET https://api.lever.co/v0/postings/<company>?mode=json``
(verified 2026-11-09: control token ``leverdemo`` returned 10 postings; the five
target firms all returned 404 — a negative result, see
``research/data_expansion/probes/lever/NOTES.md``).

Two source-specific traps handled here
--------------------------------------
1. **``createdAt`` is epoch milliseconds.**  Read as seconds it yields a 1970
   date.  :func:`common.epoch_millis_to_iso` is the single conversion point and
   returns the value with its quality.
2. **There is no ``updatedAt``.**  An edit is indistinguishable from a new
   posting, so ``createdAt`` is the only defensible publication clock — which is
   exactly ``source_public_at``.

Unlike Greenhouse, Lever *does* expose ``categories.department`` — but it was
``null`` for some postings in the control board, so the department coverage rate
is measured and reported rather than assumed.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from medradar.external_sources import base as ev_base
from medradar.external_sources import identity as ev_identity
from medradar.external_sources.procurement import common

SOURCE_ID = "lever"
SOURCE_NAME = "Lever postings API"
KIND = "job_posting"
LICENCE_STATUS = "unknown"
ATTRIBUTION = "Lever postings API, employer-published job postings"
REDISTRIBUTION = "unknown"

POSTINGS_URL = "https://api.lever.co/v0/postings/{company}"

DEDUPE_KEY_FIELDS = ("company", "title", "location")

INTERPRETATION_WARNING = (
    "A job posting is an operational artefact, not a technology signal. Posting volume can "
    "reflect backfill, seasonality or reorganisation and must not be read as a change in "
    "technology direction."
)

#: Department strings that map onto the three role families the task requires.
_DEPARTMENT_ROLES = {
    "rnd": ("engineering", "research", "product", "design", "science", "clinical", "quality"),
    "sales": ("sales", "marketing", "business development", "commercial", "customer success"),
    "production": ("manufacturing", "production", "operations", "supply chain", "logistics"),
}


def postings_url(company: str) -> str:
    return POSTINGS_URL.format(company=company)


def department_role(department: Any) -> str:
    """Map a Lever department string onto rnd/sales/production, or ``unknown``.

    This reads a *real source field* (unlike a title heuristic), but only where
    the employer filled it in.
    """
    text = common.clip(department, 200).lower()
    if not text:
        return "unknown"
    for role, hints in _DEPARTMENT_ROLES.items():
        if any(hint in text for hint in hints):
            return role
    return "unknown"


def posting_record_id(posting: Mapping[str, Any]) -> str:
    posting_id = posting.get("id")
    if posting_id is not None and str(posting_id).strip():
        return str(posting_id).strip()
    return "lever_" + common.digest(posting.get("text"), posting.get("hostedUrl"), posting.get("createdAt"))


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    fetched_at: str = "",
    company_index: ev_identity.CompanyIndex | None = None,
    company_token: str = "",
    collection_run_id: str = "",
) -> dict[str, Any]:
    """One Lever posting -> one ``job_posting`` evidence record."""
    fetched = fetched_at or common.utc_iso()
    posting = dict(raw_item)
    record_id = posting_record_id(posting)
    categories = posting.get("categories") or {}
    if not isinstance(categories, Mapping):
        categories = {}

    created_iso, created_quality = common.epoch_millis_to_iso(posting.get("createdAt"))
    department = common.clip(categories.get("department"), 200)
    company_name = common.clip(company_token, 200)

    normalized = {
        "company_token": company_name,
        "company": company_name,
        "title": common.clip(posting.get("text"), 300),
        "location": common.clip(categories.get("location"), 200),
        "team": common.clip(categories.get("team"), 200),
        "commitment": common.clip(categories.get("commitment"), 120),
        "department": department,
        "department_available": bool(department),
        "department_role": department_role(department),
        "department_note": (
            "categories.department is a real source field but was null for some postings; "
            "the coverage rate must be measured before any role-mix claim"
        ),
        "workplace_type": common.clip(posting.get("workplaceType"), 80),
        "created_at_iso": created_iso,
        "created_at_raw_epoch_ms": posting.get("createdAt"),
        "hosted_url": common.clip(posting.get("hostedUrl"), 500),
        "updated_at": "",
        "updated_at_note": "Lever exposes no updatedAt; an edit cannot be distinguished from a new posting",
        "interpretation_warning": INTERPRETATION_WARNING,
    }

    raw_body = common.canonical_json_line(posting).encode("utf-8")
    raw = common.raw_block(raw_body, path=f"{postings_url(company_token)}#posting:{record_id}")

    identifiers = common.identifier_list(("lever_posting_id", record_id, {"is_primary": True}))

    time_block = common.clock_block(
        event_at=None,
        source_public_at=created_iso or None,
        fetched_at=fetched,
        quality=created_quality,
        notes=(
            "job posting: source_public_at = createdAt converted from epoch milliseconds. "
            "There is no updatedAt, so an edit is invisible. event_at is null. "
            "first_observed_at is the fetch clock."
        ),
    )

    refs: list[dict[str, Any]] = []
    if company_name:
        refs.append(common.resolve_company(company_index, company_name))

    return common.evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=f"{company_token}:{record_id}" if company_token else record_id,
        source_url=postings_url(company_token) if company_token else POSTINGS_URL,
        normalized=normalized,
        raw=raw,
        time_block=time_block,
        identifiers=identifiers,
        entity_refs=refs,
        source_name=SOURCE_NAME,
        licence_status=LICENCE_STATUS,
        attribution=ATTRIBUTION,
        redistribution=REDISTRIBUTION,
        fetched_at=fetched,
        collection_run_id=collection_run_id,
    )


def collect(
    client: Any,
    *,
    company: str,
    limit: int = 50,
    company_index: ev_identity.CompanyIndex | None = None,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Fetch one company's postings and return at most ``limit`` records."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    fetched = fetched_at or ev_base.utc_iso()
    result = client.get(postings_url(company), params={"mode": "json"})
    if not result.ok:
        return []
    try:
        body = result.json()
    except Exception:
        return []
    if not isinstance(body, list):
        return []
    records: list[dict[str, Any]] = []
    for posting in body[: int(limit)]:
        if not isinstance(posting, Mapping):
            continue
        records.append(
            to_evidence(
                posting,
                fetched_at=fetched,
                company_index=company_index,
                company_token=company,
                collection_run_id=collection_run_id,
            )
        )
    return records


def department_coverage(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """How many postings actually carry a usable department — measured, not assumed."""
    total = 0
    with_department = 0
    roles: dict[str, int] = {}
    for record in records:
        normalized = record.get("normalized") or {}
        if not isinstance(normalized, Mapping):
            continue
        total += 1
        if normalized.get("department_available"):
            with_department += 1
            role = str(normalized.get("department_role") or "unknown")
            roles[role] = roles.get(role, 0) + 1
    return {
        "n_postings": total,
        "n_with_department": with_department,
        "coverage_rate": round(with_department / total, 4) if total else 0.0,
        "role_counts_over_covered_postings": roles,
        "note": "role mix may only be reported for the covered subset, and that subset must be stated",
    }


def duplicate_report(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Duplicate rate over ``(company, title, location)`` for collected postings."""
    rows = []
    for record in records:
        normalized = record.get("normalized") or {}
        if isinstance(normalized, Mapping):
            rows.append({field: normalized.get(field) for field in DEDUPE_KEY_FIELDS})
    return common.dedupe_report(rows, DEDUPE_KEY_FIELDS)


__all__ = [
    "ATTRIBUTION",
    "DEDUPE_KEY_FIELDS",
    "INTERPRETATION_WARNING",
    "KIND",
    "LICENCE_STATUS",
    "POSTINGS_URL",
    "SOURCE_ID",
    "SOURCE_NAME",
    "collect",
    "department_coverage",
    "department_role",
    "duplicate_report",
    "posting_record_id",
    "postings_url",
    "to_evidence",
]
