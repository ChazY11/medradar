"""Strict four-clock conversion for imported evidence.

ATLAS's own :func:`medradar.atlas.evidence.timeq.build_time` defaults a missing
``first_observed_at`` to ``fetched_at``.  For ATLAS's own connectors that is
defensible — the connector really is the first observer.

It is **not** defensible for CONVERGENCE.  These records were observed by
HORIZON on 2026-11-09 and are being imported later; stamping the import time as
the first observation would fabricate an observation history and silently break
every ``as_of`` query that depends on it.  This module therefore keeps
``first_observed_at`` empty when the source has no observation log, and records
*why* it is empty.

It also refuses the other direction of the same error: deriving
``first_observed_at`` or ``source_public_at`` from ``event_at``.  A 1999 Health
Canada licence date does not tell us the record became public in 1999, and it
certainly does not tell us when MedRadar first saw it.
"""

from __future__ import annotations

from typing import Any, Mapping

from medradar.atlas.evidence.timeq import (
    check_ordering,
    implied_quality,
    iso,
    parse_date,
    parse_datetime,
)

from .contract import NON_PUBLICATION_HINTS, TIME_EVIDENCE_FIELDS

#: Basis strings recorded with each clock so the provenance of the value is
#: legible months later.
BASIS_SOURCE_RECORDED = "source_recorded_observation_log"
BASIS_FETCH_CLOCK = "fetch_clock_only"
BASIS_UNKNOWN = "unknown_no_observation_log"
BASIS_NOT_APPLICABLE = "not_applicable_no_publication_date"
BASIS_SOURCE_PUBLIC = "source_reported_public_availability"
BASIS_DERIVED_NOT_ALLOWED = "rejected_derivation_attempted"


def _is_non_publication(note: str | None) -> bool:
    if not note:
        return False
    low = str(note).lower()
    return any(hint in low for hint in NON_PUBLICATION_HINTS)


def build_time_block(
    record: Mapping[str, Any],
    *,
    import_run_started_at: str,
) -> tuple[dict[str, Any], list[str]]:
    """Build the ATLAS time block for one HORIZON record.

    Returns ``(time_block, warnings)``.  The block always contains all four
    clocks (ATLAS requires the keys to exist); a missing clock is the empty
    string, never a substitute date.
    """
    warnings: list[str] = []
    attributes = record.get("attributes") or {}
    temporal_note = attributes.get("temporal_note")
    clock_class = attributes.get("clock_class")

    event_raw = record.get("event_at")
    public_raw = record.get("source_public_at")
    observed_raw = record.get("first_observed_at")
    fetched_raw = record.get("fetched_at")

    event = parse_date(event_raw)
    public = parse_date(public_raw)
    observed = parse_datetime(observed_raw)
    fetched = parse_datetime(fetched_raw)

    # --- first_observed_at -------------------------------------------------
    # Three legal cases: the source logged it; the source ran no observation log
    # (unknown); or the record is being imported and we can only say "we saw this
    # copy now", which is the fetch clock and must be labelled as such.
    if observed is not None:
        observed_iso = iso(observed)
        observed_basis = BASIS_SOURCE_RECORDED
    elif fetched is not None:
        observed_iso = ""
        observed_basis = BASIS_UNKNOWN
        warnings.append(
            "first_observed_at_unknown_source_ran_no_observation_log"
        )
    else:  # pragma: no cover - fetched_at is required by the source contract
        observed_iso = ""
        observed_basis = BASIS_UNKNOWN
        warnings.append("first_observed_at_unknown_and_fetched_at_missing")

    # --- source_public_at --------------------------------------------------
    if public is not None:
        quality = implied_quality(public_raw)
        if _is_non_publication(temporal_note):
            # The source's own note says this field is not a publication date.
            # Keep the date but refuse to call it a public-availability clock.
            warnings.append("source_public_at_contradicts_temporal_note")
            public_iso = ""
            quality = "unknown"
            public_basis = BASIS_DERIVED_NOT_ALLOWED
        else:
            public_iso = iso(public)
            public_basis = BASIS_SOURCE_PUBLIC
    else:
        public_iso = ""
        quality = "unknown"
        public_basis = BASIS_NOT_APPLICABLE

    # --- event_at ----------------------------------------------------------
    event_iso = iso(event) if event is not None else ""
    if event is None and public is not None and clock_class == "PUBLICATION_ONLY":
        # Nothing to do; recorded for the audit trail only.
        pass

    block: dict[str, Any] = {
        "event_at": event_iso,
        "source_public_at": public_iso,
        "first_observed_at": observed_iso,
        "fetched_at": iso(fetched) if fetched is not None else import_run_started_at,
        "source_public_at_quality": quality,
        "observation_basis": observed_basis,
        "source_public_at_basis": public_basis,
        "notes": "",
    }
    # Preserve the source's own temporal claims so a reader can audit them.
    for field in TIME_EVIDENCE_FIELDS:
        value = attributes.get(field)
        if value not in (None, "", []):
            block[f"source_{field}"] = value

    for problem in check_ordering(block):
        warnings.append(f"clock_ordering:{problem}")

    # Record the relationship between the two substantive clocks.  This is *not*
    # a per-record error: a patent legitimately files years before it publishes,
    # and for a journal article the "event" often *is* the publication.  Storing
    # the relation lets EXP-C4 quantify how many records can support a lead-time
    # claim at all, instead of the adapter guessing per record.
    block["clock_relation"] = _clock_relation(event, public)
    if block["clock_relation"] == "public_before_event":
        # Publication before the event it is supposed to precede is the one
        # pattern that is almost always a misassigned clock, so it is surfaced.
        warnings.append("source_public_at_precedes_event_at")

    return block, sorted(set(warnings))


def _clock_relation(event, public) -> str:  # noqa: ANN001 - date | None
    """Classify how the substantive clocks relate, for downstream analysis."""
    if event is None and public is None:
        return "no_dates"
    if event is not None and public is None:
        return "event_only"
    if event is None and public is not None:
        return "public_only"
    if public == event:
        return "event_equals_public"
    return "event_before_public" if event < public else "public_before_event"


def public_availability_basis(block: Mapping[str, Any]) -> str:
    """Human-readable statement of what the public clock actually rests on."""
    if not block.get("source_public_at"):
        return "no_source_public_at"
    return str(block.get("source_public_at_basis") or BASIS_SOURCE_PUBLIC)


__all__ = [
    "BASIS_FETCH_CLOCK",
    "BASIS_NOT_APPLICABLE",
    "BASIS_SOURCE_PUBLIC",
    "BASIS_SOURCE_RECORDED",
    "BASIS_UNKNOWN",
    "build_time_block",
    "public_availability_basis",
]
