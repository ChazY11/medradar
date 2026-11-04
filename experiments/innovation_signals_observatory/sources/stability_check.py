"""Collection stability check: run the same bounded collection twice and compare.

Why this exists
---------------
`PROTOCOL.md` §8 makes two things preconditions for any 90-day observation:

  * the identity key must be stable across repeated collection of the same source
    (otherwise "new posting" counts measure collection noise), and
  * `first_seen_at` must not move when the same posting is observed again.

This script measures the first one directly: it runs the collector twice against the
same source and compares the two snapshots by posting identity. It is a *measurement*,
not an assertion — a low overlap is reported, not hidden.

It also reports, per snapshot, what the identity keys look like, so a change in the
source's id scheme is visible as a change in key *shape* rather than as a change in
"hiring".

Usage:
    python experiments/innovation_signals_observatory/sources/stability_check.py \
        --company medtronic --limit 200 --out experiments/innovation_signals_observatory/results/2026-11-04
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from medradar.http import Fetcher  # noqa: E402
from medradar.recruitment import records as rec  # noqa: E402
from medradar.recruitment.politeness import CollectionPolicy, DEFAULT_UA  # noqa: E402
from medradar.recruitment.store import ObservationStore  # noqa: E402
from medradar.recruitment.workday import SOURCES, collect  # noqa: E402


def key_shape(posting_ids: list[str]) -> dict[str, int]:
    """Coarse shape census of identity keys (opaque hash vs slug vs requisition)."""
    shapes = {"opaque_hex": 0, "slug_with_req": 0, "bare_req": 0, "other": 0}
    for pid in posting_ids:
        if len(pid) == 32 and all(c in "0123456789abcdef" for c in pid):
            shapes["opaque_hex"] += 1
        elif "_R" in pid or "-R" in pid:
            shapes["slug_with_req"] += 1
        elif pid.startswith("R") and pid[1:].isdigit():
            shapes["bare_req"] += 1
        else:
            shapes["other"] += 1
    return shapes


def run_once(company: str, limit: int, min_interval: float, cache_dir: Path | None):
    source = SOURCES[company]
    policy = CollectionPolicy(min_interval_s=min_interval, max_postings=limit, max_requests=3000)
    fetcher = Fetcher(cache_dir=cache_dir, min_interval=min_interval, max_requests=3000, ua=DEFAULT_UA)
    observations, report = collect(source, policy, fetcher, limit_postings=limit, refresh=True)
    return observations, report, fetcher


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="medtronic", choices=sorted(SOURCES))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--min-interval", type=float, default=0.8)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "_httpcache_stability"

    print(f"run 1: {args.limit} postings ...")
    obs1, rep1, fetcher1 = run_once(args.company, args.limit, args.min_interval, cache / "run1")
    # Ingest run 1 into the append-only store: that is what fixes first_seen_at.
    store = ObservationStore(out / "stability_store")
    first_run_summary = store.ingest(obs1, complete_snapshot=False,
                                     run_meta={"phase": "stability_run1", "limit": args.limit})
    print(f"run 2: {args.limit} postings ...")
    obs2, rep2, fetcher2 = run_once(args.company, args.limit, args.min_interval, cache / "run2")
    second_run_summary = store.ingest(obs2, complete_snapshot=False,
                                      run_meta={"phase": "stability_run2", "limit": args.limit})
    current = store.current()

    ids1 = {o.posting_id for o in obs1}
    ids2 = {o.posting_id for o in obs2}
    common = ids1 & ids2
    obs2_by_id = {o.posting_id: o for o in obs2}
    obs1_by_id = {o.posting_id: o for o in obs1}
    hash_stable = sum(1 for pid in common
                      if obs1_by_id[pid].content_sha256 == obs2_by_id[pid].content_sha256)
    # The store is the authority on first_seen_at: every posting from run 1 must still
    # carry run 1's clock after run 2 has been ingested.
    first_seen_run1 = {o.obs_id: obs1_by_id[o.posting_id].first_seen_at for o in obs1}
    first_seen_preserved = sum(1 for obs_id, seen in first_seen_run1.items()
                               if current.get(obs_id, {}).get("first_seen_at") == seen)

    payload = {
        "check": "recruitment_collection_stability",
        "company": args.company,
        "limit": args.limit,
        "min_interval_s": args.min_interval,
        "run1": {
            "n": len(obs1),
            "listing_total_reported": rep1.listing_total_reported,
            "details_ok": rep1.details_ok,
            "details_failed": rep1.details_failed,
            "duplicate_listing_rows": rep1.duplicate_listing_rows,
            "requests": fetcher1.stats,
            "started_at": rep1.started_at,
            "finished_at": rep1.finished_at,
            "id_shapes": key_shape(sorted(ids1)),
            "availability": rec.availability_counts(obs1)["rates"],
        },
        "run2": {
            "n": len(obs2),
            "listing_total_reported": rep2.listing_total_reported,
            "details_ok": rep2.details_ok,
            "details_failed": rep2.details_failed,
            "duplicate_listing_rows": rep2.duplicate_listing_rows,
            "requests": fetcher2.stats,
            "started_at": rep2.started_at,
            "finished_at": rep2.finished_at,
            "id_shapes": key_shape(sorted(ids2)),
            "availability": rec.availability_counts(obs2)["rates"],
        },
        "comparison": {
            "n_ids_run1": len(ids1),
            "n_ids_run2": len(ids2),
            "n_common": len(common),
            "identity_overlap_run1": round(len(common) / len(ids1), 4) if ids1 else None,
            "identity_overlap_run2": round(len(common) / len(ids2), 4) if ids2 else None,
            "content_hash_stable_among_common": round(hash_stable / len(common), 4) if common else None,
            "first_seen_preserved_after_second_run": first_seen_preserved,
            "first_seen_preserved_fraction": (round(first_seen_preserved / len(first_seen_run1), 4)
                                              if first_seen_run1 else None),
            "only_in_run1": sorted(ids1 - ids2)[:20],
            "only_in_run2": sorted(ids2 - ids1)[:20],
            "note": ("The two runs observe the same ordered listing with the same limit, so a "
                     "materially lower overlap than 1.0 would mean the listing order is unstable "
                     "or the site changed between runs; a lower content-hash stability would mean "
                     "descriptions are being edited between runs. first_seen_at is read back from "
                     "the append-only store after the second ingest, which is the only place it "
                     "can be proven not to have moved."),
        },
        "store": {"summary": store.summary(),
                  "run1": first_run_summary,
                  "run2": second_run_summary},
        "caps": {"max_requests_per_run": 3000},
    }
    path = out / "stability_check.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    c = payload["comparison"]
    print(f"wrote {path}")
    print(f"  ids run1/run2 = {c['n_ids_run1']}/{c['n_ids_run2']} common={c['n_common']} "
          f"overlap={c['identity_overlap_run1']}")
    print(f"  content hash stable among common = {c['content_hash_stable_among_common']}")
    print(f"  first_seen preserved = {c['first_seen_preserved_fraction']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
