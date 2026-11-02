"""B-040: collect ClinicalTrials.gov DEVICE trials mapped to the device track taxonomy.

Why: cycle 4 measured that the shipped spine has no source that can independently confirm a
detected regulatory change — the existing trial lane is mapped to *drug* tracks, which are
disjoint from the device tracks used by the detection panel (0 of 104 cells matchable).

This script closes that gap the cheapest lawful way: reuse the repository's existing, tested
device-trial collector (`medradar.clinical.collect_trials`), which already filters to
DEVICE/DIAGNOSTIC_TEST interventions and maps studies to the **device** track registry, but point
it at a NEW, disposable database so that the frozen research lane is never touched.

Collection characteristics (all inherited from the audited collector, not re-invented):
  * ClinicalTrials.gov API v2, interventional studies only, window = last 122 months
    (≈2016-09 .. 2026-11, covering the detection window);
  * sponsor queries planned from the curated device watchlist (name + one distinct alias);
  * hard caps: 3 pages per sponsor term and 360 requests per run, so the run is bounded;
  * knowledge time = study first-posted date (the registry's own publication date);
  * per-study match evidence stored in the payload (match_confidence, matched_alias,
    device_intervention).

Output: data/b040_device_trials.sqlite (git-ignored, disposable, never the frozen lane).

Usage:
    python experiments/b040/collect_device_trials.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.clinical import collect_trials  # noqa: E402
from medradar.config import (  # noqa: E402
    CompanyRegistry,
    load_companies,
    load_tracks,
)
from medradar.db import DB  # noqa: E402
from medradar.http import Fetcher  # noqa: E402

OUT_DB = Path("data/b040_device_trials.sqlite")
CACHE = Path("data/cache/b040")
TODAY = date(2026, 11, 2)
MONTHS = 122          # ≈2016-09 .. 2026-11
MAX_REQUESTS = 420    # > the collector's own 360-term cap, so the cap binds first


def main() -> int:
    companies = load_companies("device").all()
    tracks = load_tracks("device")
    print(f"device watchlist: {len(companies)} companies; device tracks: {len(tracks.ids())}")
    db = DB(OUT_DB)
    fetcher = Fetcher(cache_dir=CACHE, min_interval=0.25, max_requests=MAX_REQUESTS)
    stats = collect_trials(
        db,
        fetcher,
        months=MONTHS,
        registry=CompanyRegistry(companies),
        tracks=tracks,
        companies=companies,
        today=TODAY,
    )
    print("collector stats:", {key: value for key, value in stats.items()
                              if not isinstance(value, (list, dict))})
    for key in ("warnings", "unmatched_sponsors", "sponsor_totals"):
        if key in stats:
            value = stats[key]
            print(f"  {key}: {value if not isinstance(value, (list, dict)) else (list(value)[:5] if isinstance(value, list) else list(value.items())[:5])}")

    rows = db.conn.execute(
        "select count(*) n, "
        "sum(case when track_id is not null and track_id<>'' then 1 else 0 end) with_track, "
        "sum(case when company_key is not null and company_key<>'' then 1 else 0 end) with_company, "
        "min(event_date) first, max(event_date) last "
        "from events where kind='trial'").fetchone()
    print(f"\ntrial events stored: {rows['n']}  {rows['first']} .. {rows['last']}")
    print(f"  with device track: {rows['with_track']}  with company: {rows['with_company']}")
    device_flag = db.conn.execute(
        "select sum(case when payload like '%\"device_intervention\": true%' then 1 else 0 end) n "
        "from events where kind='trial'").fetchone()["n"]
    print(f"  studies with a device intervention: {device_flag}")
    per_track = db.conn.execute(
        "select track_id, count(*) n from events where kind='trial' "
        "and track_id is not null and track_id<>'' group by track_id order by n desc").fetchall()
    print(f"  distinct device tracks: {len(per_track)}")
    for row in per_track[:12]:
        print(f"    {row['track_id']:24s} {row['n']}")
    print(f"\nrequests used: {fetcher.stats['requests']}  cache hits: {fetcher.stats['cache_hits']}  "
          f"errors: {fetcher.stats['errors']}")
    db.conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
