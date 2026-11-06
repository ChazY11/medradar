#!/usr/bin/env python3
"""PHOENIX experimental evidence contract for auditable temporal research.

This module is intentionally independent of MedRadar's production models. It does
not assert that legacy rows already satisfy the contract; it gives restored-data
runs a strict validation and lineage-partition target.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

REQUIRED_IDENTITY_FIELDS = ("matched_alias", "match_rule", "confidence", "ownership_valid_from")
TIME_QUALITIES = {"observed", "estimated", "unknown"}


def _day(value: str) -> date:
    if not isinstance(value, str):
        raise ValueError("dates must be ISO YYYY-MM-DD strings")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date: {value!r}") from exc


def validate_event(record: dict, cutoff: str, *, prospective: bool = False) -> None:
    """Validate one event without changing it or inferring missing provenance.

    ``prospective=True`` is the category-4 gate: estimated/unknown time quality
    and any availability after the cutoff are hard failures.
    """
    for field in ("source_event_id", "source_locator", "lineage_id", "event_date", "available_at", "timestamp_quality"):
        if not record.get(field):
            raise ValueError(f"missing required field: {field}")
    event_day, available_day, cutoff_day = _day(record["event_date"]), _day(record["available_at"]), _day(cutoff)
    if available_day < event_day:
        raise ValueError("available_at precedes event_date")
    if available_day > cutoff_day:
        raise ValueError("event is not available at the information cutoff")
    quality = record["timestamp_quality"]
    if quality not in TIME_QUALITIES:
        raise ValueError(f"unsupported timestamp_quality: {quality}")
    if prospective and quality != "observed":
        raise ValueError("category-4 validation requires observed timestamp_quality")

    if record.get("company_key"):
        for field in REQUIRED_IDENTITY_FIELDS:
            if record.get(field) in (None, ""):
                raise ValueError(f"company-linked event lacks {field}")
        confidence = record["confidence"]
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be a number in [0,1]")
        ownership_start = _day(record["ownership_valid_from"])
        if record.get("ownership_valid_to"):
            ownership_end = _day(record["ownership_valid_to"])
            if ownership_end < ownership_start:
                raise ValueError("ownership interval is inverted")
            if not ownership_start <= event_day <= ownership_end:
                raise ValueError("event falls outside the alias ownership interval")
        elif event_day < ownership_start:
            raise ValueError("event predates alias ownership")
    if record.get("track_id") and not record.get("taxonomy_version"):
        raise ValueError("track-linked event lacks taxonomy_version")


def assert_lineage_disjoint(train: Iterable[dict], validation: Iterable[dict]) -> None:
    """Refuse shared source/derived lineages across train and validation."""
    train_ids = {row["lineage_id"] for row in train}
    validation_ids = {row["lineage_id"] for row in validation}
    shared = sorted(train_ids & validation_ids)
    if shared:
        raise ValueError(f"lineage leakage across partitions: {shared}")


def coverage_counts(events: Iterable[dict]) -> dict:
    """Report event rows separately from independent lineages and coverage."""
    rows = list(events)
    return {
        "event_rows": len(rows),
        "independent_lineages": len({row["lineage_id"] for row in rows}),
        "company_linked_rows": sum(bool(row.get("company_key")) for row in rows),
        "track_linked_rows": sum(bool(row.get("track_id")) for row in rows),
        "fully_linked_rows": sum(bool(row.get("company_key") and row.get("track_id")) for row in rows),
        "observed_time_rows": sum(row.get("timestamp_quality") == "observed" for row in rows),
    }
