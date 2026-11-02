"""A1 of the expanded design: which firm x track cells carry BOTH streams above the frozen floors?

Design input only. This script deliberately reports coverage quantities (event counts, quarters with activity,
per-stream availability) and **never** onset counts or detection outcomes — the point is to choose cells before
seeing results, so that later performance cannot influence selection.

Floors are the ones already frozen in PROTOCOL.md / DOMAIN_AMENDMENT_001.md: >=40 observations and >=12 quarters with
observation inside 2017-2025, applied **per stream** (regulatory: 510(k)+PMA; recall: device_recall).

    python experiments/b087/cell_inventory.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.coverage import quarter_of  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
OUT_DIR = Path("research/studies/early_signal_5firms")
WINDOW = ("2017-01-01", "2025-12-31")
FIVE_FIRMS = ("medtronic", "ge_healthcare", "philips", "mindray", "draeger")
FLOOR_OBS, FLOOR_QUARTERS = 40, 12
STREAMS = {"regulatory": ("510k", "pma"), "recall": ("device_recall",)}


def connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    con = connect()
    cells: dict[tuple[str, str], dict] = defaultdict(lambda: {stream: {"observations": 0, "quarters": set()}
                                                             for stream in STREAMS})
    for stream, kinds in STREAMS.items():
        placeholders = ",".join("?" for _ in kinds)
        rows = con.execute(
            f"select company_key, track_id, event_date from events where kind in ({placeholders}) "
            f"and event_date between ? and ? and company_key is not null and track_id is not null",
            [*kinds, *WINDOW]).fetchall()
        for firm, track, event_date in rows:
            if firm not in FIVE_FIRMS:
                continue
            quarter = quarter_of(event_date)
            if quarter is None:
                continue
            block = cells[(firm, track)][stream]
            block["observations"] += 1
            block["quarters"].add(quarter)
    con.close()

    inventory = []
    for (firm, track), block in sorted(cells.items()):
        entry = {"company": firm, "track": track}
        for stream, values in block.items():
            entry[f"{stream}_observations"] = values["observations"]
            entry[f"{stream}_quarters"] = len(values["quarters"])
            entry[f"{stream}_meets_floor"] = (values["observations"] >= FLOOR_OBS
                                              and len(values["quarters"]) >= FLOOR_QUARTERS)
        entry["both_streams"] = all(entry[f"{stream}_meets_floor"] for stream in STREAMS)
        inventory.append(entry)

    both = [entry for entry in inventory if entry["both_streams"]]
    regulatory_only = [entry for entry in inventory
                       if entry["regulatory_meets_floor"] and not entry["recall_meets_floor"]]
    payload = {
        "schema": "cell_inventory_v1",
        "purpose": "design input for the expanded O1 design; contains no outcome quantities",
        "window": list(WINDOW), "floors": {"observations": FLOOR_OBS, "quarters": FLOOR_QUARTERS},
        "counts": {"cells_with_any_stream": len(inventory), "both_streams": len(both),
                   "regulatory_only": len(regulatory_only)},
        "both_streams": both,
        "regulatory_only": regulatory_only,
        "all_cells": inventory,
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CELL_INVENTORY.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print(f"cells with any stream: {len(inventory)}")
    print(f"cells meeting floors for BOTH streams: {len(both)}")
    for entry in both:
        print(f"  {entry['company']:14s} {entry['track']:22s} "
              f"reg={entry['regulatory_observations']:>4}/{entry['regulatory_quarters']:>2}q "
              f"rec={entry['recall_observations']:>4}/{entry['recall_quarters']:>2}q")
    print(f"regulatory-only cells: {len(regulatory_only)}")
    for entry in regulatory_only[:12]:
        print(f"  {entry['company']:14s} {entry['track']:22s} "
              f"reg={entry['regulatory_observations']:>4}/{entry['regulatory_quarters']:>2}q "
              f"rec={entry['recall_observations']:>4}")
    print(f"wrote {out_dir}/CELL_INVENTORY.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
