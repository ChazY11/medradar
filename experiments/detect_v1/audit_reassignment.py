"""Noise-control audit: can the taxonomy manufacture a change point in this lane?

A tracked technology change must not be an artefact of product-code reassignment. Two
checks, read-only:
1. Is ``track_id`` a deterministic function of ``product_code`` in this frozen lane
   (i.e. can a mapping update insert an artificial step change into a cell's history)?
2. How stable is each cell's product-code composition over time (a cell whose codes are
   completely replaced looks like a change but may be relabelling)?
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

DB = Path("data/research.sqlite")


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select product_code, track_id, count(*) n from events "
        "where kind in ('510k','pma') and track_id is not null and track_id<>'' "
        "and product_code is not null and product_code<>'' "
        "group by product_code, track_id").fetchall()
    con.close()

    by_code: dict[str, set[str]] = defaultdict(set)
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        by_code[row["product_code"]].add(row["track_id"])
        counts[(row["product_code"], row["track_id"])] += row["n"]

    multi = {code: sorted(tracks) for code, tracks in by_code.items() if len(tracks) > 1}
    print("== check 1: product_code -> track_id determinism ==")
    print(f"  codes with a track assignment: {len(by_code)}")
    print(f"  codes mapping to more than one track: {len(multi)}")
    if multi:
        for code, tracks in list(multi.items())[:10]:
            print(f"    {code}: {tracks}")
    print("  VERDICT:", (
        "track_id is a deterministic function of product_code in this lane, so a taxonomy "
        "update cannot create a time-varying step change inside a cell's history"
        if not multi else
        "NOT deterministic: some product codes map to multiple tracks; a remap could move "
        "events between cells and manufacture apparent changes"))

    # check 2: does a cell's product-code composition turn over completely?
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    ev = con.execute(
        "select event_date, track_id, product_code, applicant_raw from events "
        "where kind in ('510k','pma') and track_id is not null and track_id<>'' "
        "and product_code is not null and product_code<>''").fetchall()
    con.close()

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402

    cells: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for row in ev:
        normalised = normalise_applicant(row["applicant_raw"])
        if not normalised:
            continue
        cells[(entity_key(normalised), row["track_id"])].append(
            (str(row["event_date"])[:7], row["product_code"]))

    flips = 0
    total = 0
    examples = []
    for key, items in cells.items():
        if len(items) < 12:
            continue
        items.sort()
        half = len(items) // 2
        early = {code for _, code in items[:half]}
        late = {code for _, code in items[half:]}
        if not early or not late:
            continue
        total += 1
        overlap = early & late
        if not overlap:
            flips += 1
            if len(examples) < 8:
                examples.append({"cell": f"{key[0]}|{key[1]}", "early_codes": len(early),
                                 "late_codes": len(late), "events": len(items)})
    print("\n== check 2: product-code turnover between the early and late half of a cell ==")
    print(f"  cells with >=12 events: {total}")
    print(f"  cells with zero code overlap between halves (complete relabelling): {flips}"
          f" ({flips / total:.1%})" if total else "  no eligible cells")
    for example in examples:
        print(f"    {example['cell']}: early={example['early_codes']} late={example['late_codes']} "
              f"events={example['events']}")
    print("  VERDICT:", (
        "no complete relabelling observed; a detected change is unlikely to be a pure code "
        "swap" if flips == 0 else
        "some cells replace their entire code set, so a change alert in those cells must be "
        "checked against product-code composition before being called a technology change"))
    payload = {"codes_total": len(by_code), "codes_multi_track": len(multi),
               "multi_track_examples": {code: tracks for code, tracks in list(multi.items())[:20]},
               "cells_checked": total, "cells_complete_relabelling": flips,
               "relabelling_examples": examples}
    Path("experiments/detect_v1/reassignment_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nwrote experiments/detect_v1/reassignment_audit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
