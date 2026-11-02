"""Probe the legacy full-history DB for an independent trial signal (B-033).

The research lane has no trials table, but the legacy main checkout DB carries a
ClinicalTrials.gov lane. Question: can it serve as an INDEPENDENT confirmation source
(different registry from FDA filings) for detected regulatory changes, at the legal-entity
granularity used by the detection panel?

Read-only. Reports field availability, time coverage, entity-mappability and overlap with
the detection panel's cells.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402

LEGACY = Path(r"D:\DEPPSKK\medradar\data\medradar.sqlite")


def main() -> int:
    if not LEGACY.exists():
        print("legacy DB missing")
        return 1
    con = sqlite3.connect(f"file:{LEGACY}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    print("== trial lane overview ==")
    row = con.execute(
        "select count(*) n, min(event_date) first, max(event_date) last, "
        "sum(case when track_id is not null and track_id<>'' then 1 else 0 end) with_track, "
        "sum(case when company_key is not null and company_key<>'' then 1 else 0 end) with_company, "
        "sum(case when applicant_raw is not null and applicant_raw<>'' then 1 else 0 end) with_applicant "
        "from events where kind='trial'").fetchone()
    print(f"  rows={row['n']}  {row['first']} .. {row['last']}")
    print(f"  with track_id: {row['with_track']} ({row['with_track']/row['n']:.1%})")
    print(f"  with company_key: {row['with_company']} ({row['with_company']/row['n']:.1%})")
    print(f"  with applicant_raw: {row['with_applicant']} ({row['with_applicant']/row['n']:.1%})")

    print("\n== distinct sponsors and their legal-entity mapping ==")
    rows = con.execute(
        "select applicant_raw, count(*) n from events where kind='trial' "
        "and applicant_raw is not null and applicant_raw<>'' group by applicant_raw").fetchall()
    print(f"  distinct sponsor strings: {len(rows)}")
    resolved = 0
    unresolved = 0
    entity_events: Counter[str] = Counter()
    for row in rows:
        normalised = normalise_applicant(row["applicant_raw"])
        if normalised:
            resolved += 1
            entity_events[entity_key(normalised)] += row["n"]
        else:
            unresolved += 1
    print(f"  normalisable: {resolved}  non-normalisable: {unresolved}")
    print(f"  distinct legal entities among trial sponsors: {len(entity_events)}")
    print(f"  events from the top 20 entities: {sum(n for _, n in entity_events.most_common(20))}")

    print("\n== track coverage among trials ==")
    tracks = con.execute(
        "select track_id, count(*) n from events where kind='trial' "
        "and track_id is not null and track_id<>'' group by track_id order by n desc").fetchall()
    print(f"  distinct tracks: {len(tracks)}")
    for row in tracks[:15]:
        print(f"    {row['track_id']:24s} {row['n']}")

    print("\n== overlap with the detection panel cells ==")
    import json
    streams_path = Path("experiments/detect_v1/streams.json")
    if not streams_path.exists():
        print("  streams.json missing; cannot compute overlap")
        con.close()
        return 0
    streams = json.loads(streams_path.read_text(encoding="utf-8"))
    cells = {(cell["entity"], cell["track"]) for cell in streams["track_cells"]}
    print(f"  detection cells: {len(cells)}")
    trial_cell_events: Counter[tuple[str, str]] = Counter()
    trial_rows = con.execute(
        "select applicant_raw, track_id, event_date from events where kind='trial' "
        "and track_id is not null and track_id<>''").fetchall()
    for row in trial_rows:
        normalised = normalise_applicant(row["applicant_raw"])
        if not normalised:
            continue
        trial_cell_events[(entity_key(normalised), row["track_id"])] += 1
    covered = cells & set(trial_cell_events)
    print(f"  detection cells with >=1 trial event: {len(covered)} ({len(covered)/len(cells):.1%})")
    entities_cells = {entity for entity, _ in cells}
    entities_trials = {entity for entity, _ in trial_cell_events}
    print(f"  detection entities: {len(entities_cells)}; entities also in trial lane: "
          f"{len(entities_cells & entities_trials)}")
    for (entity, track), n in trial_cell_events.most_common(10):
        if (entity, track) in cells:
            print(f"    cell in panel: {entity[:40]:40s} {track:20s} trials={n}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
