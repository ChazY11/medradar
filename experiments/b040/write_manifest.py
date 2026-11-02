"""Write a committed manifest for the B-040 device-trial collection.

The collected database lives under `data/` (git-ignored, regenerable). ClinicalTrials.gov is a
living registry, so re-running the collector later will not return an identical sample. This
manifest therefore records exactly what was collected, when, with which caps, and how the lane
was assembled — so the analysis that used it can be audited even though the rows themselves are
not versioned.

    python experiments/b040/write_manifest.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402

DB = Path("data/b040_device_trials.sqlite")
OUT = Path("experiments/b040/collection_manifest.json")


def main() -> int:
    if not DB.exists():
        print("collection DB missing; run collect_device_trials.py first")
        return 1
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    totals = con.execute(
        "select count(*) n, min(event_date) first, max(event_date) last, "
        "sum(case when company_key is not null and company_key<>'' then 1 else 0 end) with_company, "
        "sum(case when track_id is not null and track_id<>'' then 1 else 0 end) with_track "
        "from events where kind='trial'").fetchone()
    device = con.execute(
        "select count(*) n from events where kind='trial' "
        "and payload like '%\"device_intervention\": true%'").fetchone()["n"]
    tracks = con.execute(
        "select track_id, count(*) n from events where kind='trial' "
        "and track_id is not null and track_id<>'' group by track_id order by n desc").fetchall()
    companies = con.execute(
        "select company_key, count(*) n from events where kind='trial' "
        "and company_key is not null and company_key<>'' group by company_key "
        "order by n desc").fetchall()
    con.close()

    payload = {
        "schema": "b040_device_trials_manifest_v1",
        "written_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "name": "ClinicalTrials.gov API v2",
            "endpoint": "https://clinicaltrials.gov/api/v2/studies",
            "study_type": "INTERVENTIONAL",
            "knowledge_time": "study first-posted date",
            "licence": "public domain (US NIH registry)",
        },
        "collection": {
            "command": "python experiments/b040/collect_device_trials.py",
            "sponsor_watchlist": "config/companies_device.json (51 curated device companies)",
            "sponsor_terms_planned": 82,
            "requests_used": 107,
            "max_pages_per_term": 3,
            "max_requests_cap": 360,
            "window_months": 122,
            "reference_date": "2026-11-02",
            "collector_stats_from_log": {
                "studies_returned": 4130,
                "interventional": 2663,
                "in_window": 2663,
                "events": 2663,
                "matched": 1472,
                "match_rate": 0.5528,
                "track_matched": 1278,
                "track_match_rate": 0.4799,
                "device_trials": 1949,
                "device_track_matched": 1181,
                "truncated": False,
                "errors": 0,
            },
        },
        "stored": {
            "trial_events": totals["n"],
            "date_range": [totals["first"], totals["last"]],
            "attributable_to_curated_company": totals["with_company"],
            "mapped_to_device_track": totals["with_track"],
            "device_intervention_studies": device,
            "distinct_companies": len(companies),
            "distinct_device_tracks": len(tracks),
        },
        "top_companies": [{"company_key": row["company_key"], "events": row["n"]}
                          for row in companies[:15]],
        "tracks": {row["track_id"]: row["n"] for row in tracks},
        "regeneration_note": (
            "The rows are NOT committed (data/ is git-ignored and the registry is live). Re-running "
            "the collector reproduces the method, not the exact sample; this manifest pins what was "
            "collected on the date above so the analysis can be audited."),
        "known_limits": [
            "sponsor resolution covers 55% of returned studies",
            "device-track mapping is keyword-based and covers 48%",
            "3-page/term cap makes large sponsors a sample, not a census",
            "trials attach to a company, not to a legal sub-entity",
        ],
    }
    write_json(OUT, payload)
    print(f"wrote {OUT}: {totals['n']} trial events, {len(tracks)} device tracks, "
          f"{len(companies)} companies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
