"""Phase 0 pure logic for the five-firm early-signal study.

Two jobs, both testable without touching a database:

  * **source tiering** — classify each data source as Tier A (historically verifiable first-publication time),
    Tier B (conservative reconstruction), Tier C (descriptive only) or Tier D (unavailable), from evidence about
    which timestamp fields the store actually carries. A source may not be promoted on the basis that its table
    exists.
  * **coverage aggregation** — turn raw observations into the study unit the protocol fixes:
    ``company × technology track × quarter``, with explicit counts of *usable* quarters (at least one observation)
    inside the historical window, and a statement of the window each firm/domain actually supports.

Nothing here decides science; it measures what the data can support.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

#: the directive's candidate domains, mapped to the store's track ids (verified against the tracks table)
DOMAINS: dict[str, tuple[str, ...]] = {
    "patient_monitoring": ("patient_monitoring",),
    "ultrasound_imaging": ("imaging_us",),
    "advanced_imaging": ("imaging_mr_ct",),
    "respiratory_critical_care": ("respiratory",),
    "medical_ai_samd": ("medical_ai",),
}

FIVE_FIRMS = ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")

#: evidence required to call a source point-in-time usable for strict backtests
TIER_A_REQUIRES = ("published_at", "available_at")
TIER_B_REQUIRES = ("event_date",)

TIER_DESCRIPTIONS = {
    "A": "historically verifiable: a recorded first-publication or availability time independent of the event date",
    "B": "conservative reconstruction: only the event date is recorded, so availability must be reconstructed with a "
         "declared lag and checked by sensitivity analysis",
    "C": "descriptive only: no usable historical time, may not enter lead-time conclusions",
    "D": "unavailable: not present in the frozen stores or blocked by access",
}


def classify_source(*, present: bool, columns: Iterable[str],
                    first_seen_is_fetch: bool = True,
                    notes: Sequence[str] = ()) -> dict[str, Any]:
    """Assign a tier from what the store actually records.

    `first_seen_is_fetch` matters: when the ``first_seen_at`` column was written at collection time, it records *our*
    fetch date rather than the source's publication date, so it cannot substitute for a publication timestamp.
    """
    column_set = {column.lower() for column in columns}
    if not present:
        return {"tier": "D", "reasons": ["source not present in the frozen stores", *notes],
                "description": TIER_DESCRIPTIONS["D"]}
    has_a = all(field in column_set for field in TIER_A_REQUIRES)
    has_b = all(field in column_set for field in TIER_B_REQUIRES)
    usable_first_seen = "first_seen_at" in column_set and not first_seen_is_fetch
    reasons: list[str] = list(notes)
    if has_a:
        reasons.append("records both published_at and available_at")
        return {"tier": "A", "reasons": reasons, "description": TIER_DESCRIPTIONS["A"]}
    if has_b:
        if usable_first_seen:
            reasons.append("records an independent first_seen_at in addition to the event date")
            return {"tier": "A", "reasons": reasons, "description": TIER_DESCRIPTIONS["A"]}
        if "first_seen_at" in column_set:
            reasons.append("first_seen_at is the collection date, not the source's publication date")
        reasons.append("only the event date is trustworthy, so availability must be reconstructed")
        return {"tier": "B", "reasons": reasons, "description": TIER_DESCRIPTIONS["B"]}
    reasons.append("no event date or publication time recorded")
    return {"tier": "C", "reasons": reasons, "description": TIER_DESCRIPTIONS["C"]}


def quarter_of(date_string: str) -> str | None:
    """'YYYY-MM-DD...' -> 'YYYY-Qn'; returns None when the value cannot be parsed."""
    if not date_string:
        return None
    text = str(date_string).strip()
    if len(text) < 7 or text[4] != "-":
        return None
    try:
        year = int(text[:4])
        month = int(text[5:7])
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-Q{(month - 1) // 3 + 1}"


def quarters_between(start: str, end: str) -> list[str]:
    """Inclusive list of 'YYYY-Qn' labels between two ISO dates."""
    first, last = quarter_of(start), quarter_of(end)
    if not first or not last:
        return []
    start_year, start_q = int(first[:4]), int(first[-1])
    end_year, end_q = int(last[:4]), int(last[-1])
    labels = []
    year, quarter = start_year, start_q
    while (year, quarter) <= (end_year, end_q):
        labels.append(f"{year:04d}-Q{quarter}")
        quarter += 1
        if quarter == 5:
            year, quarter = year + 1, 1
    return labels


def aggregate_coverage(observations: Iterable[Mapping[str, Any]], *,
                       window: tuple[str, str],
                       domains: Mapping[str, Sequence[str]] | None = None,
                       firms: Sequence[str] = FIVE_FIRMS) -> dict[str, Any]:
    """Build company × domain coverage inside a fixed window.

    Each observation needs: company, track, date, source. Observations outside the window are counted as
    `outside_window` rather than silently dropped, because the audit must show why a cell is empty.
    """
    domain_map = dict(domains or DOMAINS)
    track_to_domain = {track: domain for domain, tracks in domain_map.items() for track in tracks}
    expected_quarters = quarters_between(window[0], window[1])

    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for firm in firms:
        for domain in domain_map:
            cells[(firm, domain)] = {"observations": 0, "sources": defaultdict(int),
                                     "quarters": set(), "outside_window": 0,
                                     "first": None, "last": None}
    unknown_track = 0
    unknown_firm = 0
    for observation in observations:
        firm = observation.get("company")
        domain = track_to_domain.get(observation.get("track"))
        if firm not in cells and firm is not None:
            unknown_firm += 1
        if domain is None:
            unknown_track += 1
            continue
        cell = cells.get((firm, domain))
        if cell is None:
            continue
        cell["sources"][observation.get("source") or "unknown"] += 1
        quarter = quarter_of(observation.get("date"))
        if quarter is None:
            continue
        if quarter < expected_quarters[0] or quarter > expected_quarters[-1]:
            cell["outside_window"] += 1
            continue
        cell["observations"] += 1
        cell["quarters"].add(quarter)
        date = str(observation.get("date"))
        cell["first"] = date if cell["first"] is None or date < cell["first"] else cell["first"]
        cell["last"] = date if cell["last"] is None or date > cell["last"] else cell["last"]

    matrix = []
    for (firm, domain), cell in sorted(cells.items()):
        matrix.append({
            "company": firm,
            "domain": domain,
            "tracks": list(domain_map[domain]),
            "observations_in_window": cell["observations"],
            "quarters_with_observation": len(cell["quarters"]),
            "expected_quarters": len(expected_quarters),
            "quarter_coverage": (round(len(cell["quarters"]) / len(expected_quarters), 3)
                                if expected_quarters else None),
            "first_observation": cell["first"],
            "last_observation": cell["last"],
            "outside_window": cell["outside_window"],
            "sources": dict(cell["sources"]),
        })

    per_firm = defaultdict(lambda: {"observations": 0, "domains_nonempty": 0})
    for row in matrix:
        per_firm[row["company"]]["observations"] += row["observations_in_window"]
        if row["observations_in_window"]:
            per_firm[row["company"]]["domains_nonempty"] += 1

    return {
        "window": {"start": window[0], "end": window[1], "quarters": len(expected_quarters)},
        "matrix": matrix,
        "per_firm": dict(per_firm),
        "unassigned": {"unknown_track": unknown_track, "unknown_firm": unknown_firm},
    }


def evaluability(matrix: Sequence[Mapping[str, Any]], *, min_observations: int,
                 min_quarters: int) -> dict[str, Any]:
    """Decide, against pre-declared floors, which cells are evaluable — and say why the others are not."""
    evaluable, not_evaluable = [], []
    for row in matrix:
        if row["observations_in_window"] >= min_observations and \
                row["quarters_with_observation"] >= min_quarters:
            evaluable.append({"company": row["company"], "domain": row["domain"],
                              "observations": row["observations_in_window"],
                              "quarters": row["quarters_with_observation"]})
        else:
            reason = ("no observations in the window" if not row["observations_in_window"]
                      else f"below floors ({row['observations_in_window']} obs, "
                           f"{row['quarters_with_observation']} quarters; "
                           f"need {min_observations}+ and {min_quarters}+)")
            not_evaluable.append({"company": row["company"], "domain": row["domain"],
                                  "reason": reason})
    return {"floors": {"min_observations": min_observations, "min_quarters": min_quarters},
            "evaluable": evaluable, "not_evaluable": not_evaluable,
            "counts": {"evaluable": len(evaluable), "not_evaluable": len(not_evaluable)}}
