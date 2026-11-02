"""Panel builder for the bin-width sweep (B-038, DECISIONS D-017/D-018 follow-up).

Builds entity x track count panels at several bin widths (1, 2, 3, 4, 6 months) from the
same material-event lane and the same deterministic legal-entity assignment used by
`streams.py`, so the only thing that changes between panels is the aggregation width.

Kept in its own module so that `streams.py` / `streams_ext.json` stay byte-identical and
the frozen cycle-3 artifacts remain reproducible.

Usage:
    python experiments/detect_v1/widths.py --db data/research.sqlite
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import (  # noqa: E402
    MIN_ACTIVE_MONTHS,
    MIN_TOTAL_EVENTS,
    WINDOW_MONTHS,
    month_index,
    month_labels,
)

#: Bin widths tested, in months. Chosen to be divisors of the 12-month horizon where
#: possible so the horizon is a whole number of bins (12/1, 12/2, 12/3, 12/4, 12/6).
WIDTHS = (1, 2, 3, 4, 6)


def resolve_events(db_path: Path) -> list[dict[str, Any]]:
    """(entity, track, month) for every material event inside the window."""
    events = load_regulatory_events(db_path)
    resolved: list[dict[str, Any]] = []
    for event in events:
        normalised = normalise_applicant(event.get("applicant_raw"))
        track = event.get("track_id")
        index = month_index(event["day"])
        if not normalised or not track or index is None:
            continue
        resolved.append({
            "entity": entity_key(normalised),
            "entity_name": str(event.get("applicant_raw") or normalised),
            "track": track,
            "month": index,
        })
    return resolved


def panel_for_width(resolved: list[dict[str, Any]], width: int,
                    labels: list[str]) -> dict[str, Any]:
    """Aggregate resolved events into ``width``-month bins and build eligible cells."""
    bins = WINDOW_MONTHS // width
    buckets: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    names: dict[str, str] = {}
    for row in resolved:
        bucket = row["month"] // width
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
            "active_bins": len(counts),
            "series": [int(counts.get(index, 0)) for index in range(bins)],
        })
    cells.sort(key=lambda cell: (-cell["total_events"], cell["entity"], cell["track"]))
    per_cell = [cell["total_events"] / bins for cell in cells]
    per_cell_sorted = sorted(per_cell)
    totals = [cell["total_events"] for cell in cells]
    return {
        "bin_months": width,
        "bins": bins,
        "labels": [f"{labels[index * width]}+{width}m" for index in range(bins)],
        "cells": cells,
        "summary": {
            "cells": len(cells),
            "entities": len({cell["entity"] for cell in cells}),
            "tracks": len({cell["track"] for cell in cells}),
            "events": sum(totals),
            "median_events_per_cell": (sorted(totals)[len(totals) // 2] if totals else None),
            "median_expected_events_per_bin": (per_cell_sorted[len(per_cell_sorted) // 2]
                                               if per_cell_sorted else None),
            "mean_expected_events_per_bin": (sum(per_cell) / len(per_cell) if per_cell else None),
        },
    }


def build_widths(db_path: Path) -> dict[str, Any]:
    labels = month_labels()
    resolved = resolve_events(db_path)
    panels = {str(width): panel_for_width(resolved, width, labels) for width in WIDTHS}
    return {
        "schema": "detect_widths_v1",
        "decision": ("research/DECISIONS.md D-017 (sensitivity family) and D-018 (the "
                     "resolution reversal this sweep must explain); pre-declared before the run"),
        "window": {"start": labels[0], "end": labels[-1], "months": WINDOW_MONTHS},
        "widths": list(WIDTHS),
        "eligibility": {"min_total_events": MIN_TOTAL_EVENTS,
                        "min_active_bins": MIN_ACTIVE_MONTHS},
        "panels": panels,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/detect_v1/widths.json")
    args = parser.parse_args(argv)
    payload = build_widths(Path(args.db))
    write_json(Path(args.out), payload)
    for width, panel in payload["panels"].items():
        summary = panel["summary"]
        print(f"width {width:>2}m: {summary['cells']:3d} cells, {panel['bins']:3d} bins, "
              f"median events/cell={summary['median_events_per_cell']}, "
              f"median expected events/bin={summary['median_expected_events_per_bin']:.3f}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
