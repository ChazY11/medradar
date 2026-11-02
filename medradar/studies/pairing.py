"""Pairing logic for the lead/lag probe: pure functions, testable without a database.

A "pair" is one earlier-source record and the **first** later regulatory event strictly after the earlier record's
availability time. Only the first later event counts; the number of further events is reported as ambiguity rather
than silently dropped, because at firm level the next clearance can be days away and the pairing then carries no
information.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence

QUARTER_DAYS = 91.0


def lead_quarters(later: date, available_at: date) -> float:
    """Lead time in quarters, rounded to two decimals; negative means the later event is not actually later."""
    return round((later - available_at).days / QUARTER_DAYS, 2)


def pair_first_subsequent(earlier: Sequence[Mapping], later: Sequence[Mapping], *,
                          lag_days: int = 0, min_lead_quarters: float = 2.0) -> dict:
    """Pair each earlier record with the first later event strictly after its availability.

    Returns eligible pairs, below-threshold pairs (real pairs whose lead is shorter than the declared floor),
    the ambiguity count (further events skipped per earlier record) and the unpaired count.
    """
    pairs, below, unpaired = [], [], 0
    multiplicity = 0
    for record in sorted(earlier, key=lambda item: item["date"]):
        available = record["date"] + timedelta(days=lag_days)
        candidates = [event for event in later if event["date"] > available]
        if not candidates:
            unpaired += 1
            continue
        first = min(candidates, key=lambda event: event["date"])
        multiplicity += len(candidates) - 1
        lead = lead_quarters(first["date"], available)
        entry = {"earlier_id": record.get("event_id"), "earlier_date": record["date"].isoformat(),
                 "available_at": available.isoformat(),
                 "later_id": first.get("event_id"), "later_date": first["date"].isoformat(),
                 "lead_days": (first["date"] - available).days, "lead_quarters": lead,
                 "resolved_by": record.get("resolved_by", "company_key")}
        if lead >= min_lead_quarters:
            pairs.append(entry)
        else:
            below.append(entry)
    return {"pairs": pairs, "below_threshold": below, "multiplicity_skipped": multiplicity,
            "n_pairs": len(pairs), "n_below_threshold": len(below), "n_unpaired": unpaired}


def describe_leads(pairs: Iterable[Mapping]) -> dict:
    """Distribution summary of eligible leads; never a mean-of-successes only."""
    leads = sorted(float(entry["lead_quarters"]) for entry in pairs)
    if not leads:
        return {"n": 0, "median": None, "min": None, "max": None, "quartiles": [None, None, None]}

    def percentile(values: list[float], fraction: float) -> float:
        if not values:
            return None
        index = min(len(values) - 1, max(0, int(round(fraction * (len(values) - 1)))))
        return values[index]

    return {"n": len(leads), "median": percentile(leads, 0.5), "min": leads[0], "max": leads[-1],
            "quartiles": [percentile(leads, 0.25), percentile(leads, 0.5), percentile(leads, 0.75)]}


def gate(pair_counts: Mapping[str, int], firms_with_pairs: Mapping[str, Sequence[str]], *,
         min_pairs: int = 10, min_firms: int = 2) -> dict:
    """Apply the frozen G1 criteria to a scope's counts (one entry per lag setting)."""
    best_lag = max(pair_counts, key=lambda lag: pair_counts[lag]) if pair_counts else None
    best_pairs = pair_counts.get(best_lag, 0) if best_lag else 0
    firms = firms_with_pairs.get(best_lag, []) if best_lag else []
    if best_pairs >= min_pairs and len(firms) >= min_firms:
        verdict = "GO"
    elif best_pairs == 0:
        verdict = "NOT_EVALUABLE"
    else:
        verdict = "NO-GO"
    return {"verdict": verdict, "best_lag": best_lag, "best_pairs": best_pairs,
            "firms": list(firms), "criteria": {"min_pairs": min_pairs, "min_firms": min_firms}}
