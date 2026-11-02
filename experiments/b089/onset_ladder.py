"""Positive-class incidence ladder: is the zero onsets a property of the corpus or of the definition?

The frozen definition (>=12 months silence, then >=2 events within 4 quarters) produced zero onsets in every one of
the 16 study cells over 2017-2025. Before writing that up, this script distinguishes the two possible causes by
re-counting candidate quarters under progressively looser definitions. It reports **incidence only** — how often the
positive class exists — and no detection outcome, so the frozen protocol is not being amended by looking at results.

    python experiments/b089/onset_ladder.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.concurrent import quarter_index, quarter_label  # noqa: E402
from medradar.studies.coverage import quarter_of  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
INVENTORY = Path("research/studies/early_signal_5firms/CELL_INVENTORY.json")
OUT_DIR = Path("research/studies/early_signal_5firms")
SERIES = ("2017-Q1", "2025-Q4")
SILENCE_OPTIONS = (4, 8)          # 12 months, 24 months
EPISODE_OPTIONS = (4, 6, 8)       # quarters inside which the episode must carry its events
MIN_EVENTS_OPTIONS = (2, 3)


def quarters_between(start: str, end: str) -> list[str]:
    labels, index = [], quarter_index(start)
    while quarter_label(index) <= end:
        labels.append(quarter_label(index))
        index += 1
    return labels


def load_counts(con: sqlite3.Connection, firm: str, track: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for (event_date,) in con.execute(
            "select event_date from events where kind in ('510k','pma') and company_key=? and track_id=? "
            "and event_date between ? and ?", (firm, track, "2016-01-01", "2025-12-31")):
        label = quarter_of(event_date)
        if label and SERIES[0] <= label <= SERIES[1]:
            counts[label] += 1
    return dict(counts)


def ladder(counts: dict[str, int]) -> dict:
    labels = quarters_between(*SERIES)
    first, last = quarter_index(labels[0]), quarter_index(labels[-1])
    activity = sum(counts.values())
    active_quarters = len([label for label in labels if counts.get(label)])
    out = {"activity": activity, "active_quarters": active_quarters, "total_quarters": len(labels),
           "definitions": {}}
    for silence in SILENCE_OPTIONS:
        for episode in EPISODE_OPTIONS:
            for min_events in MIN_EVENTS_OPTIONS:
                key = f"silence{silence}q_episode{episode}q_min{min_events}"
                hits, candidates = 0, 0
                index = first
                while index <= last:
                    if index - silence < first:
                        index += 1
                        continue
                    silent = all(counts.get(quarter_label(index - offset), 0) == 0
                                 for offset in range(1, silence + 1))
                    if not silent:
                        index += 1
                        continue
                    window = [quarter_label(index + offset) for offset in range(episode)]
                    if quarter_index(window[-1]) > last:
                        index += 1
                        continue
                    candidates += 1
                    if counts.get(quarter_label(index), 0) >= 1 and \
                            sum(counts.get(label, 0) for label in window) >= min_events:
                        hits += 1
                        index += episode
                    else:
                        index += 1
                out["definitions"][key] = {"candidate_quarters_after_silence": candidates,
                                           "qualifying_onsets": hits}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=str(INVENTORY))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    cells = [{"company": entry["company"], "track": entry["track"], "set": "primary"}
             for entry in inventory["both_streams"]]
    cells += [{"company": entry["company"], "track": entry["track"], "set": "secondary"}
              for entry in inventory["regulatory_only"]]

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    per_cell = {}
    for cell in cells:
        counts = load_counts(con, cell["company"], cell["track"])
        per_cell[f"{cell['company']}|{cell['track']}"] = {
            "set": cell["set"], **ladder(counts)}
    con.close()

    keys = list(next(iter(per_cell.values()))["definitions"]) if per_cell else []
    totals = {}
    for key in keys:
        totals[key] = {
            "onsets": sum(cell["definitions"][key]["qualifying_onsets"] for cell in per_cell.values()),
            "candidates": sum(cell["definitions"][key]["candidate_quarters_after_silence"]
                              for cell in per_cell.values()),
            "cells_with_onset": sum(1 for cell in per_cell.values()
                                    if cell["definitions"][key]["qualifying_onsets"] > 0),
        }

    payload = {
        "schema": "onset_ladder_v1",
        "purpose": "distinguish 'the corpus has no sustained changes' from 'the frozen definition is too strict'",
        "series": list(SERIES), "cells": len(per_cell),
        "frozen_definition": "silence4q_episode4q_min2",
        "totals_by_definition": totals, "per_cell": per_cell,
        "note": ("incidence only: no detector is run here, so the frozen protocol is not amended by inspecting "
                 "these numbers; a looser definition would have to be pre-registered as a new study"),
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ONSET_LADDER.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print(f"cells: {len(per_cell)}")
    print(f"{'definition':34s} {'candidates':>10s} {'onsets':>7s} {'cells':>6s}")
    for key, block in totals.items():
        frozen = "  <- frozen" if key == payload["frozen_definition"] else ""
        print(f"{key:34s} {block['candidates']:>10d} {block['onsets']:>7d} {block['cells_with_onset']:>6d}{frozen}")
    print(f"wrote {out_dir}/ONSET_LADDER.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
