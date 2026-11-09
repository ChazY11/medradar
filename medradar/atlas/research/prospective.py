"""Prospective technology-candidate registry.

This is infrastructure for *future* evaluation, not a prediction claim.  A
candidate records what MedRadar saw at a specific time, before the outcome was
known; later outcomes are appended as events, never back-filled into the
original registration.

Registration is deliberately conservative:

* a candidate is created from an evidence record that has a company link and at
  least one official identifier in exactly one market;
* it is *not* created when the device already has a confirmed cross-market
  identity (that is a present fact, not a future candidate);
* the record keeps the identifiers known **at registration time**, so a later
  identifier does not retroactively make the candidate look better informed.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from ..evidence import schema as ev
from ..evidence.timeq import utc_iso
from ..identity.pilot import device_ref
from ..store import AtlasStore

MARKETS = {"openfda_device_udi": "US", "accessgudid": "US", "canada_mdall": "CA"}


def register_cross_market_candidates(store: AtlasStore, *, limit: int = 500) -> dict[str, Any]:
    """Register single-market devices that are plausible future cross-market entries.

    A device already confirmed as cross-market is skipped: the point of the
    registry is to hold *unresolved* candidates for later evaluation.
    """
    confirmed = {
        row["from_ref"]
        for row in store.query(
            "SELECT from_ref FROM entity_relations WHERE relation_type='SAME_DEVICE_IDENTITY'"
            " AND status='CONFIRMED' AND revoked_at=''"
        )
    } | {
        row["to_ref"]
        for row in store.query(
            "SELECT to_ref FROM entity_relations WHERE relation_type='SAME_DEVICE_IDENTITY'"
            " AND status='CONFIRMED' AND revoked_at=''"
        )
    }
    created = 0
    skipped_confirmed = 0
    for record in store.iter_evidence():
        if created >= limit:
            break
        ref = device_ref(record)
        if ref in confirmed:
            skipped_confirmed += 1
            continue
        if not record.get("entity_refs"):
            continue
        official = [i for i in record.get("identifiers") or []
                    if i.get("scheme") in {"di", "licence_no", "510k", "pma"}]
        if not official:
            continue
        market = MARKETS.get(str(record.get("source_id")), "")
        if not market:
            continue
        store.register_prospective_candidate(
            name_raw=str(record.get("normalized", {}).get("brand_name")
                        or record.get("normalized", {}).get("licence_name")
                        or record.get("source_record_id")),
            source_id=str(record["source_id"]),
            evidence_id=str(record["evidence_id"]),
            first_observed_at=str(record["time"]["first_observed_at"]),
            company_candidate=str(record["entity_refs"][0].get("firm_key") or ""),
            known_identifiers=official,
            notes=f"market={market}; registered before any cross-market confirmation",
        )
        created += 1
    return {
        "registered": created,
        "skipped_already_confirmed": skipped_confirmed,
        "limit": limit,
        "note": "Candidates are observations, not predictions; no outcome is asserted.",
    }


def candidate_summary(store: AtlasStore) -> dict[str, Any]:
    rows = store.prospective_candidates()
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        by_source[row["source_id"]] = by_source.get(row["source_id"], 0) + 1
    return {
        "query": "prospective_candidates",
        "count": len(rows),
        "by_status": by_status,
        "by_source": by_source,
        "candidates": rows[:100],
        "note": "Registration is timestamped; later evidence is appended as events, never rewritten.",
    }


__all__ = ["MARKETS", "candidate_summary", "register_cross_market_candidates"]
