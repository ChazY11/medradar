"""Profile one recruitment snapshot: the WP2 first-layer (source feasibility) evidence.

A posting count alone says nothing about whether a source is usable. This script turns a
snapshot file into the measurements `PROTOCOL.md` §4 asks for:

  * how many postings, and how many *distinct* posting identities;
  * field availability rates: identity, title, description, location, source date;
  * the source's own date quality mix and the range of dates it published;
  * description length distribution (a "description" of 40 characters is not a description);
  * duplicate structure: the same requisition appearing as several postings (multi-city /
    re-advertisement) — visible as postings sharing `raw.job_req_id`;
  * how many postings the source reported but we did not capture (truncation honesty).

Output: <out>/snapshot_profile.json and a compact Markdown table on stdout.

Usage:
    python experiments/innovation_signals_observatory/sources/profile_snapshot.py \
        --jobs results/2026-11-04/jobs_medtronic.jsonl \
        --collection results/2026-11-04/collection_medtronic.json \
        --out results/2026-11-04
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from medradar.recruitment import records as rec  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def profile(rows: list[dict], collection: dict | None) -> dict:
    n = len(rows)
    ids = [r.get("posting_id") for r in rows]
    distinct = len({i for i in ids if i})
    slugs = [(r.get("raw") or {}).get("job_posting_id_slug") for r in rows]
    reqs = [(r.get("raw") or {}).get("job_req_id") for r in rows]
    req_counts = Counter(r for r in reqs if r)
    slug_counts = Counter(s for s in slugs if s)
    dates = [r.get("source_posted_at") for r in rows if r.get("source_posted_at")]
    lens = [len(r.get("job_description") or "") for r in rows]
    qualities = Counter(r.get("source_posted_quality") for r in rows)
    statuses = Counter(r.get("collection_status") for r in rows)
    titles = Counter((r.get("job_title") or "").strip() for r in rows)
    locations = Counter((r.get("job_location") or "").strip() for r in rows)
    first_seen = [r.get("first_seen_at") for r in rows if r.get("first_seen_at")]

    def rate(pred) -> float:
        return round(sum(1 for r in rows if pred(r)) / n, 4) if n else 0.0

    return {
        "n_postings": n,
        "distinct_posting_ids": distinct,
        "distinct_rate": round(distinct / n, 4) if n else 0.0,
        "identity_availability": rate(lambda r: bool(r.get("posting_id"))),
        "title_availability": rate(lambda r: bool(r.get("job_title"))),
        "description_availability": rate(lambda r: bool(r.get("job_description"))),
        "location_availability": rate(lambda r: bool(r.get("job_location"))),
        "source_date_availability": rate(lambda r: bool(r.get("source_posted_at"))),
        "first_seen_availability": rate(lambda r: bool(r.get("first_seen_at"))),
        "legal_entity_availability": rate(lambda r: bool(r.get("legal_entity"))),
        "source_posted_quality": dict(qualities),
        "collection_status": dict(statuses),
        "source_date_min": min(dates) if dates else None,
        "source_date_max": max(dates) if dates else None,
        "first_seen_min": min(first_seen) if first_seen else None,
        "first_seen_max": max(first_seen) if first_seen else None,
        "description_length": {
            "n_nonempty": sum(1 for x in lens if x),
            "median": int(statistics.median([x for x in lens if x])) if any(lens) else 0,
            "min": min(lens) if lens else 0,
            "max": max(lens) if lens else 0,
            "n_under_200_chars": sum(1 for x in lens if 0 < x < 200),
        },
        "duplicate_structure": {
            "requisitions_shared_by_several_postings": sum(1 for c in req_counts.values() if c > 1),
            "max_postings_per_requisition": max(req_counts.values()) if req_counts else 0,
            "example_shared_requisitions": [k for k, c in req_counts.most_common(5) if c > 1],
            "slug_repeats": sum(1 for c in slug_counts.values() if c > 1),
        },
        "top_titles": titles.most_common(10),
        "n_distinct_locations": len([k for k in locations if k]),
        "top_locations": locations.most_common(10),
        "collection": {
            "listing_total_reported": ((collection or {}).get("report") or {}).get("listing_total_reported"),
            "postings_written": n,
            "truncated_at_ceiling": ((collection or {}).get("report") or {}).get("truncated_at_ceiling"),
            "details_failed": ((collection or {}).get("report") or {}).get("details_failed"),
            "duplicate_listing_rows": ((collection or {}).get("report") or {}).get("duplicate_listing_rows"),
            "requests_made": sum(int(v) for v in (((collection or {}).get("report") or {})
                                                  .get("request_stats") or {}).values()),
            "robots_hosts": list((((collection or {}).get("policy") or {}).get("robots_evidence") or {}).keys()),
        },
        "note": ("availability rates are about what this source exposed to us, not about what the "
                 "company has; a missing legal entity is expected because career sites publish a brand"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--collection", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    rows = load_jsonl(Path(args.jobs))
    collection = None
    if args.collection and Path(args.collection).exists():
        collection = json.loads(Path(args.collection).read_text(encoding="utf-8"))
    payload = profile(rows, collection)
    payload["source_file"] = str(Path(args.jobs).name)
    payload["schema_version"] = rec.SCHEMA_VERSION
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"snapshot_profile_{Path(args.jobs).stem.replace('jobs_', '')}.json"
    path = out / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in (
        "n_postings", "distinct_posting_ids", "identity_availability", "description_availability",
        "source_date_availability", "source_date_min", "source_date_max",
        "source_posted_quality", "duplicate_structure", "collection")}, ensure_ascii=False, indent=2))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
