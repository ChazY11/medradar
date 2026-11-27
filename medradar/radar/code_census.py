"""Compute the product-code distribution in ONE query instead of 40,731 round-trips.

The original loop called ``devices_for_submission`` once per 510(k) document, which is a
single-row SELECT on an indexed column — fine for a report, catastrophic as a per-code census:
40,731 round-trips against the same store the sweep is about to write to.

This module exists so both the pipeline and any future caller share one implementation.
"""
from __future__ import annotations

import json
from typing import Any


def product_code_census(reference) -> dict[str, int]:
    """How many registered devices sit behind each product code, in one JOIN."""
    counts: dict[str, int] = {}
    cursor = reference.conn.execute(
        """
        SELECT d.product_codes
        FROM udi_premarket p
        JOIN udi_device d ON d.device_key = p.device_key
        WHERE d.product_codes IS NOT NULL AND d.product_codes <> '[]'
        """
    )
    for row in cursor:
        try:
            codes = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if not isinstance(codes, list):
            continue
        for code in codes:
            text = str(code).strip()
            if text:
                counts[text] = counts.get(text, 0) + 1
    return counts


def swept_codes(reference) -> set[str]:
    """Codes already present in the failure index, so a restart never re-sweeps from zero.

    The table is created by :mod:`medradar.radar.failure_index`, not by the reference schema, so
    an untouched store legitimately has no such table. "No table" and "nothing swept" mean the
    same thing to a caller and must not raise.
    """
    seen: set[str] = set()
    try:
        seen = {str(row[0]) for row in reference.conn.execute(
            "SELECT DISTINCT product_code FROM maude_failure_index")}
    except Exception:  # noqa: BLE001 - sqlite3.OperationalError for a missing table
        seen = set()
    # Codes that were checked and turned out empty are not in the index, and without the sweep
    # record they would be re-swept forever and the published coverage could never reach the total.
    try:
        seen |= {str(row[0]) for row in reference.conn.execute(
            "SELECT product_code FROM failure_sweep")}
    except Exception:  # noqa: BLE001 - a store that has never run the new sweep
        pass
    return seen


def pending_codes(reference, *, max_codes: int | None = None) -> tuple[dict[str, int], list[str]]:
    census = product_code_census(reference)
    done = swept_codes(reference)
    ordered = [code for code, _ in sorted(census.items(), key=lambda kv: -kv[1])
               if code not in done]
    if max_codes is not None:
        ordered = ordered[:max_codes]
    return census, ordered


__all__ = ["pending_codes", "product_code_census", "swept_codes"]
