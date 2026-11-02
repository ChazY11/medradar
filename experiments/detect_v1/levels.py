"""Extra sensitivity panels for the OBSERVE detection benchmark (DECISIONS D-017).

Written as a separate module on purpose: it never overwrites `streams.json`, so the
cycle-3 artifacts stay frozen and reproducible while the three pre-declared
sensitivities are added alongside them.

Panels produced
---------------
* ``track_no_special``   monthly, entity x track, **Special 510(k)s removed**
                         (clearance_type == "Special" = modification of the filer's own
                         cleared device, 15.01 % of lane 510(k)s).
* ``track_stable_codes`` monthly, entity x track, **events under product codes first seen
                         in 2022 or later removed** (taxonomy-churn proxy).
* ``track_quarterly``    3-month bins, entity x track, all material events (density
                         sensitivity: triples the count per bin, 39 bins).

Usage:
    python experiments/detect_v1/levels.py --db data/research.sqlite
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import (  # noqa: E402
    MIN_ACTIVE_MONTHS,
    MIN_TOTAL_EVENTS,
    WINDOW_MONTHS,
    load_product_codes,
    month_index,
    month_labels,
)

#: Pre-declared churn cut-off: a product code whose first appearance in the lane is on or
#: after this month is treated as "recent" and its events are removed in the stable panel.
CHURN_CUTOFF = "2022-01"
QUARTER_MONTHS = 3


def _payload_field(payload: str | None, field: str) -> str:
    try:
        data = json.loads(payload or "{}")
    except (TypeError, ValueError):
        return ""
    value = data.get(field)
    return str(value).strip() if value is not None else ""


def build_levels(db_path: Path) -> dict[str, Any]:
    events = load_regulatory_events(db_path)
    codes = load_product_codes(db_path)
    labels = month_labels()

    # product-code first appearance inside the lane (churn proxy, conservative: a code that
    # predates the window appears at the window start, so this can only understate age)
    first_seen: dict[str, int] = {}
    for event in events:
        code = codes.get(str(event.get("event_id")), "")
        index = month_index(event["day"])
        if not code or index is None:
            continue
        if code not in first_seen or index < first_seen[code]:
            first_seen[code] = index
    cutoff_index = None
    target = CHURN_CUTOFF
    for index, label in enumerate(labels):
        if label >= target:
            cutoff_index = index
            break
    if cutoff_index is None:
        cutoff_index = WINDOW_MONTHS
    recent_codes = {code for code, index in first_seen.items() if index >= cutoff_index}

    clearance: Counter[str] = Counter()
    resolved: list[dict[str, Any]] = []
    for event in events:
        normalised = normalise_applicant(event.get("applicant_raw"))
        track = event.get("track_id")
        index = month_index(event["day"])
        if not normalised or not track or index is None:
            continue
        code = codes.get(str(event.get("event_id")), "")
        kind = event["kind"]
        ctype = _payload_field(event.get("payload"), "clearance_type") if kind == "510k" else ""
        if kind == "510k":
            clearance[ctype or "(missing)"] += 1
        resolved.append({
            "entity": entity_key(normalised),
            "entity_name": str(event.get("applicant_raw") or normalised),
            "track": track,
            "kind": kind,
            "month": index,
            "code": code,
            "clearance_type": ctype,
            "recent_code": code in recent_codes,
        })

    def assemble(filt: Callable[[dict[str, Any]], bool], period: int) -> dict[str, Any]:
        bins = WINDOW_MONTHS // period
        buckets: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
        names: dict[str, str] = {}
        for row in resolved:
            if not filt(row):
                continue
            bucket = row["month"] // period
            if bucket >= bins:
                continue
            buckets[(row["entity"], row["track"])][bucket] += 1
            names.setdefault(row["entity"], row["entity_name"])
        cells = []
        for (entity, track), counts in buckets.items():
            total = sum(counts.values())
            if total < MIN_TOTAL_EVENTS or len(counts) < MIN_ACTIVE_MONTHS:
                continue
            cells.append({
                "entity": entity,
                "entity_name": names[entity],
                "track": track,
                "total_events": total,
                "active_months": len(counts),
                "series": [int(counts.get(index, 0)) for index in range(bins)],
            })
        cells.sort(key=lambda cell: (-cell["total_events"], cell["entity"], cell["track"]))
        totals = [cell["total_events"] for cell in cells]
        zeros = [sum(1 for value in cell["series"] if value == 0) for cell in cells]
        return {
            "cells": cells,
            "summary": {
                "cells": len(cells),
                "entities": len({cell["entity"] for cell in cells}),
                "tracks": len({cell["track"] for cell in cells}),
                "events": sum(totals),
                "median_events_per_cell": sorted(totals)[len(totals) // 2] if totals else None,
                "median_zero_bins": sorted(zeros)[len(zeros) // 2] if zeros else None,
                "bins": bins,
                "bin_months": period,
            },
        }

    no_special = assemble(lambda row: not (row["kind"] == "510k"
                                          and row["clearance_type"] == "Special"), 1)
    stable_codes = assemble(lambda row: not row["recent_code"], 1)
    quarterly = assemble(lambda row: True, QUARTER_MONTHS)

    quarter_labels = []
    for index in range(WINDOW_MONTHS // QUARTER_MONTHS):
        start = index * QUARTER_MONTHS
        quarter_labels.append(f"{labels[start]}+{QUARTER_MONTHS}m")

    return {
        "schema": "detect_levels_v1",
        "decision": "research/DECISIONS.md D-017 (pre-declared before these runs)",
        "filters": {
            "special_removed": "510(k) rows with payload.clearance_type == 'Special'",
            "churn_removed": (f"events whose product_code first appears in the lane on or after "
                              f"{CHURN_CUTOFF}"),
            "churn_cutoff": CHURN_CUTOFF,
            "churn_recent_codes": len(recent_codes),
            "churn_recent_events": sum(1 for row in resolved if row["recent_code"]),
            "clearance_type_distribution": dict(clearance),
        },
        "labels": labels,
        "quarter_labels": quarter_labels,
        "track_no_special": no_special["cells"],
        "track_no_special_summary": no_special["summary"],
        "track_stable_codes": stable_codes["cells"],
        "track_stable_codes_summary": stable_codes["summary"],
        "track_quarterly": quarterly["cells"],
        "track_quarterly_summary": quarterly["summary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/detect_v1/streams_ext.json")
    args = parser.parse_args(argv)
    payload = build_levels(Path(args.db))
    write_json(Path(args.out), payload)
    filters = payload["filters"]
    print("clearance types:", filters["clearance_type_distribution"])
    print(f"churn: {filters['churn_recent_codes']} recent codes, "
          f"{filters['churn_recent_events']} events removed")
    for key in ("track_no_special_summary", "track_stable_codes_summary",
                "track_quarterly_summary"):
        summary = payload[key]
        print(f"{key.replace('_summary',''):22s} cells={summary['cells']:3d} "
              f"entities={summary['entities']:3d} events={summary['events']:5d} "
              f"median/cell={summary['median_events_per_cell']} "
              f"median zero bins={summary['median_zero_bins']}/{summary['bins']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
