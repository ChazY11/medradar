"""Greenhouse job-board API — hiring evidence for companies that use Greenhouse.

Endpoint
--------
``GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=false``
(verified 2026-11-09: control token returned 766 live jobs; the five target firms
all returned 404, which is a negative result, not a network failure — see
``research/data_expansion/probes/greenhouse/NOTES.md``).

Hiring-evidence discipline
--------------------------
* ``first_published`` is the **publication clock** → ``source_public_at``.
  ``updated_at`` is an *edit* time and is stored separately; using it as the
  publication date would make old postings look new.
* ``first_observed_at`` is the fetch clock.  A backfill of a 2024 posting
  collected today still has ``first_observed_at = today``.
* A posting is **not** a technology signal.  ``normalized`` carries an explicit
  interpretation warning so a downstream study cannot quietly read "more R&D
  reqs" as "new technology direction".
* There is **no department/function field** in this payload (``metadata`` was
  null on every probed posting), so the R&D / Sales / Production split cannot be
  derived from structured data here — only from titles, which is a text
  heuristic.  The function below that classifies roles is deliberately explicit
  about being a heuristic and is not used in ``normalized``.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from medradar.external_sources import base as ev_base
from medradar.external_sources import identity as ev_identity
from medradar.external_sources.procurement import common

SOURCE_ID = "greenhouse"
SOURCE_NAME = "Greenhouse job board API"
KIND = "job_posting"
LICENCE_STATUS = "unknown"
ATTRIBUTION = "Greenhouse job board API, employer-published job postings"
REDISTRIBUTION = "unknown"

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

#: The de-duplication key the hiring protocol mandates.
DEDUPE_KEY_FIELDS = ("company", "title", "location")

INTERPRETATION_WARNING = (
    "A job posting is an operational artefact, not evidence of a technology direction. "
    "Posting counts can reflect backfill, seasonality or reorganisation; they must never "
    "be read as 'new R&D focus'."
)

#: Title keywords used ONLY by :func:`classify_role_heuristic`.  This is a text
#: heuristic with no source support, so it is never written into `normalized`.
_ROLE_HINTS = {
    "rnd": ("engineer", "scientist", "research", "developer", "architect", "design", "clinical"),
    "sales": ("sales", "account", "business development", "marketing", "commercial"),
    "production": ("manufactur", "production", "operator", "assembl", "technician", "quality"),
}


def board_url(token: str) -> str:
    return BOARD_URL.format(token=token)


def classify_role_heuristic(title: Any) -> str:
    """Guess rnd/sales/production from a title — explicitly a heuristic.

    Returns ``"unknown"`` when nothing matches.  Callers must label any result of
    this function as a heuristic; it is not a source field.
    """
    text = common.clip(title, 300).lower()
    for role, hints in _ROLE_HINTS.items():
        if any(hint in text for hint in hints):
            return role
    return "unknown"


def posting_record_id(job: Mapping[str, Any]) -> str:
    job_id = job.get("id")
    if job_id is not None and str(job_id).strip():
        return str(job_id).strip()
    internal = common.clip(job.get("internal_job_id"), 120)
    if internal:
        return internal
    return "gh_" + common.digest(job.get("title"), job.get("absolute_url"), job.get("first_published"))


def to_evidence(
    raw_item: Mapping[str, Any],
    *,
    fetched_at: str = "",
    company_index: ev_identity.CompanyIndex | None = None,
    board_token: str = "",
    collection_run_id: str = "",
) -> dict[str, Any]:
    """One Greenhouse job -> one ``job_posting`` evidence record."""
    fetched = fetched_at or common.utc_iso()
    job = dict(raw_item)
    record_id = posting_record_id(job)
    location = job.get("location") or {}
    location_name = common.clip(location.get("name"), 200) if isinstance(location, Mapping) else ""
    company_name = common.clip(job.get("company_name"), 300) or common.clip(board_token, 200)

    first_published = common.clip(job.get("first_published"), 40)
    updated_at = common.clip(job.get("updated_at"), 40)

    normalized = {
        "board_token": common.clip(board_token, 200),
        "company": company_name,
        "title": common.clip(job.get("title"), 300),
        "location": location_name,
        "requisition_id": common.clip(job.get("requisition_id"), 120),
        "internal_job_id": common.clip(job.get("internal_job_id"), 120),
        "absolute_url": common.clip(job.get("absolute_url"), 500),
        "first_published": first_published,
        "updated_at": updated_at,
        "updated_at_semantics": "last edit, NOT publication",
        "department": "",
        "department_available": False,
        "department_note": (
            "the Greenhouse board payload exposes no department/function field "
            "(metadata was null on every probed posting), so an R&D/Sales/Production "
            "split cannot be taken from structured fields"
        ),
        "role_heuristic": classify_role_heuristic(job.get("title")),
        "role_heuristic_caveat": "title text heuristic, not a source field; do not count as a classification",
        "interpretation_warning": INTERPRETATION_WARNING,
    }

    raw_body = common.canonical_json_line(job).encode("utf-8")
    raw = common.raw_block(raw_body, path=f"{board_url(board_token)}#job:{record_id}")

    identifiers = common.identifier_list(
        ("greenhouse_job_id", record_id, {"is_primary": True}),
        ("requisition_id", job.get("requisition_id"), {}),
    )

    time_block = common.clock_block(
        event_at=None,
        source_public_at=first_published or None,
        fetched_at=fetched,
        quality=(common.date_quality(first_published) if first_published else "unknown"),
        notes=(
            "job posting: source_public_at = first_published (when the posting became public). "
            "updated_at is an edit time and is stored separately. event_at is null - a posting "
            "describes an open role, not a dated event. first_observed_at is the fetch clock."
        ),
    )

    refs: list[dict[str, Any]] = []
    if company_name:
        refs.append(common.resolve_company(company_index, company_name))

    return common.evidence(
        source_id=SOURCE_ID,
        kind=KIND,
        source_record_id=f"{board_token}:{record_id}" if board_token else record_id,
        source_url=board_url(board_token) if board_token else BOARD_URL,
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
    token: str,
    limit: int = 50,
    company_index: ev_identity.CompanyIndex | None = None,
    fetched_at: str = "",
    collection_run_id: str = "",
) -> list[dict[str, Any]]:
    """Fetch one board and return at most ``limit`` job-posting records.

    A single request per board: the endpoint returns the whole board, so there is
    no pagination to bound — only the number of returned records.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    fetched = fetched_at or ev_base.utc_iso()
    result = client.get(board_url(token), params={"content": "false"})
    if not result.ok:
        return []
    try:
        body = result.json() or {}
    except Exception:
        return []
    jobs = body.get("jobs") if isinstance(body, Mapping) else None
    if not isinstance(jobs, list):
        return []
    records: list[dict[str, Any]] = []
    for job in jobs[: int(limit)]:
        if not isinstance(job, Mapping):
            continue
        records.append(
            to_evidence(
                job,
                fetched_at=fetched,
                company_index=company_index,
                board_token=token,
                collection_run_id=collection_run_id,
            )
        )
    return records


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
    "BOARD_URL",
    "DEDUPE_KEY_FIELDS",
    "INTERPRETATION_WARNING",
    "KIND",
    "LICENCE_STATUS",
    "SOURCE_ID",
    "SOURCE_NAME",
    "board_url",
    "classify_role_heuristic",
    "collect",
    "duplicate_report",
    "posting_record_id",
    "to_evidence",
]
