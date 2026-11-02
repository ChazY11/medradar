"""Build monthly activity streams per (entity, technology track) for change detection.

Input lane: the frozen research database (read-only), material events only
(510(k) clearances + original/PANEL-TRACK PMA), grouped by the deterministic legal
entity from ``medradar.intelligence.universe``.

Output: ``streams.json`` with, for each eligible cell, a monthly count series over the
fixed window 2016-11 .. 2026-10 (120 months). Eligibility is deliberately conservative:
a detector cannot be validated on cells that almost never fire.

Usage:
    python experiments/detect_v1/streams.py --db data/research.sqlite
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.universe import (  # noqa: E402
    entity_key,
    normalise_applicant,
)
from experiments.cycle2_coverage.panel import (  # noqa: E402
    load_regulatory_events,
    write_json,
)

WINDOW_START_YEAR, WINDOW_START_MONTH = 2016, 11
#: The lane ends 2026-10-15, so the final calendar month is PARTIAL (about 53% of a
#: normal month), which manufactures an apparent drop. The window is therefore
#: truncated to complete months only: 2016-11 .. 2026-09.
WINDOW_MONTHS = 119

#: Pre-registered eligibility (declared before any benchmark result was seen):
#: a cell must have enough material events to support a rate-change test and must be
#: observed in enough distinct months that a "change" is not one isolated filing.
MIN_TOTAL_EVENTS = 18
MIN_ACTIVE_MONTHS = 8


def month_index(day) -> int | None:
    """0-based month index into the fixed window, or None if outside it."""
    offset = (day.year - WINDOW_START_YEAR) * 12 + (day.month - WINDOW_START_MONTH)
    return offset if 0 <= offset < WINDOW_MONTHS else None


def month_labels() -> list[str]:
    labels = []
    for offset in range(WINDOW_MONTHS):
        total = WINDOW_START_YEAR * 12 + (WINDOW_START_MONTH - 1) + offset
        labels.append(f"{total // 12:04d}-{total % 12 + 1:02d}")
    return labels


def track_domains(config_path: Path = Path("config/tracks_device.json")) -> dict[str, str]:
    """track_id -> domain, from the curated device taxonomy."""
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    mapping = {}
    for track in payload.get("tracks", []):
        track_id = str(track.get("id") or "")
        domain = str(track.get("domain") or "")
        if track_id and domain:
            mapping[track_id] = domain
    return mapping


def load_product_codes(db_path: Path) -> dict[str, str]:
    """event_id -> product_code, read-only.

    ``panel.load_regulatory_events`` (a frozen cycle-2 helper) does not select
    ``product_code``; joining it here keeps that module untouched.
    """
    import sqlite3

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select event_id, product_code from events where kind in ('510k','pma')").fetchall()
    finally:
        con.close()
    return {str(event_id): str(code or "").strip() for event_id, code in rows}


def build_streams(db_path: Path) -> dict[str, Any]:
    events = load_regulatory_events(db_path)
    event_codes = load_product_codes(db_path)
    labels = month_labels()
    domains = track_domains()
    # Explicit {product_code: track_id} map: the bulk lane uses it first and only falls
    # back to device-text keyword matching when the code is absent. Keyword-assigned
    # tracks are not deterministic per product code, so a wording change can move events
    # between cells. They are tracked separately and excluded from the clean variant.
    try:
        code_map = json.loads(Path("config/product_code_tracks.json").read_text(encoding="utf-8"))
        if not isinstance(code_map, dict):
            code_map = {}
    except (OSError, ValueError):
        code_map = {}
    buckets: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    clean_buckets: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    domain_buckets: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    names: dict[str, str] = {}
    kinds: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    domain_kinds: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    unmapped_tracks: Counter[str] = Counter()
    assignment: Counter[str] = Counter()
    for event in events:
        normalised = normalise_applicant(event.get("applicant_raw"))
        if not normalised:
            continue
        entity = entity_key(normalised)
        track = event.get("track_id")
        index = month_index(event["day"])
        if not track or index is None:
            continue
        code = str(event_codes.get(str(event.get("event_id"))) or "").strip()
        deterministic = bool(code) and code in code_map and code_map[code] == track
        assignment["product_code" if deterministic else "keyword_fallback"] += 1
        buckets[(entity, track)][index] += 1
        if deterministic:
            clean_buckets[(entity, track)][index] += 1
        names.setdefault(entity, str(event.get("applicant_raw") or normalised))
        kinds[(entity, track)][event["kind"]] += 1
        domain = domains.get(track)
        if domain:
            domain_buckets[(entity, domain)][index] += 1
            domain_kinds[(entity, domain)][event["kind"]] += 1
        else:
            unmapped_tracks[track] += 1

    def assemble(source: dict[tuple[str, str], Counter[int]],
                 kind_source: dict[tuple[str, str], Counter[str]],
                 second: str) -> list[dict[str, Any]]:
        cells = []
        for (entity, key), counts in source.items():
            total = sum(counts.values())
            active_months = len(counts)
            if total < MIN_TOTAL_EVENTS or active_months < MIN_ACTIVE_MONTHS:
                continue
            series = [int(counts.get(index, 0)) for index in range(WINDOW_MONTHS)]
            cells.append({
                "entity": entity,
                "entity_name": names.get(entity, entity),
                second: key,
                "total_events": total,
                "active_months": active_months,
                "kinds": dict(kind_source[(entity, key)]),
                "series": series,
            })
        cells.sort(key=lambda cell: (-cell["total_events"], cell["entity"], cell[second]))
        return cells

    track_cells = assemble(buckets, kinds, "track")
    clean_cells = assemble(clean_buckets, kinds, "track")
    domain_cells = assemble(domain_buckets, domain_kinds, "domain")

    def summary(cells: list[dict[str, Any]], key: str) -> dict[str, Any]:
        totals = [cell["total_events"] for cell in cells]
        zeros = [sum(1 for value in cell["series"] if value == 0) for cell in cells]
        return {
            "cells": len(cells),
            "entities": len({cell["entity"] for cell in cells}),
            "groups": len({cell[key] for cell in cells}),
            "events": sum(totals),
            "events_per_cell": {
                "min": min(totals) if totals else None,
                "median": sorted(totals)[len(totals) // 2] if totals else None,
                "max": max(totals) if totals else None,
            },
            "zero_months_median": sorted(zeros)[len(zeros) // 2] if zeros else None,
        }

    return {
        "window": {"start": labels[0], "end": labels[-1], "months": WINDOW_MONTHS},
        "labels": labels,
        "eligibility": {
            "min_total_events": MIN_TOTAL_EVENTS,
            "min_active_months": MIN_ACTIVE_MONTHS,
            "note": ("pre-registered before the benchmark; a cell with fewer events cannot "
                     "support a rate-change test, and a cell active in fewer months cannot "
                     "distinguish a change from a single filing"),
        },
        "counts": {
            "material_events_total": len(events),
            "cells_before_eligibility": len(buckets),
            "unmapped_tracks": dict(unmapped_tracks),
            "track_assignment": dict(assignment),
            "track_level": summary(track_cells, "track"),
            "track_level_clean": summary(clean_cells, "track"),
            "domain_level": summary(domain_cells, "domain"),
        },
        "track_cells": track_cells,
        "track_cells_clean": clean_cells,
        "domain_cells": domain_cells,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--out", default="experiments/detect_v1/streams.json")
    args = parser.parse_args(argv)
    payload = build_streams(Path(args.db))
    write_json(Path(args.out), payload)
    counts = payload["counts"]
    print(f"material events: {counts['material_events_total']}")
    print(f"cells before eligibility: {counts['cells_before_eligibility']}")
    for level in ("track_level", "track_level_clean", "domain_level"):
        block = counts[level]
        print(f"{level}: {block['cells']} cells "
              f"({block['entities']} entities x {block['groups']} groups), "
              f"events={block['events']}, per-cell median={block['events_per_cell']['median']}, "
              f"zero-months median={block['zero_months_median']}/{payload['window']['months']}")
    if counts.get("track_assignment"):
        print(f"track assignment: {counts['track_assignment']}")
    if counts["unmapped_tracks"]:
        print(f"unmapped tracks: {counts['unmapped_tracks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

