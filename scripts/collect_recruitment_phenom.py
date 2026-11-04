"""Bounded, re-enterable collection of public R&D job postings from Phenom career sites.

Usage
-----
    python scripts/collect_recruitment_phenom.py --company ge_healthcare --limit 80 \
        --out experiments/innovation_signals_observatory/results/2026-11-04

    python scripts/collect_recruitment_phenom.py --company philips --limit 80 \
        --out experiments/innovation_signals_observatory/results/2026-11-04

What it writes (all inside ``--out``):

  ``jobs_<company>.jsonl``        one JobObservation per line (append-only snapshot)
  ``collection_<company>.json``   run report: totals, robots evidence + its interpretation,
                                  request stats, per-field availability rates, failures
  ``_httpcache_<company>/``       raw HTTP responses (audit trail; not the dataset)

Safety properties (each is a test in ``tests/test_recruitment_phenom.py``):

  * refuses to run if robots.txt is a real REP file that disallows the sitemap path; if the
    host publishes no robots.txt at all, the absence is recorded verbatim and RFC 9309's
    unavailable rule is applied explicitly (never silently);
  * bounded by ``--limit`` postings and ``--max-requests`` HTTP calls;
  * a posting page that returns 410 Gone / 404 / a network error becomes a recorded
    ``DETAIL_FAILED`` observation, never a silent drop and never "no description";
  * the source's own ``datePosted`` is kept with its precision; the midnight-timestamp
    rendering is flagged, never shifted to another day;
  * re-running writes a new snapshot; nothing is overwritten in place.

Run twice without ``--refresh`` and the second run replays from the cache: the run report
still comes from the cached bytes, but no request is made twice.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.http import Fetcher  # noqa: E402
from medradar.recruitment import records as rec  # noqa: E402
from medradar.recruitment.phenom import SOURCES, collect  # noqa: E402
from medradar.recruitment.politeness import CollectionPolicy, DEFAULT_UA  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True, choices=sorted(SOURCES))
    ap.add_argument("--out", required=True, help="results directory for this snapshot")
    ap.add_argument("--limit", type=int, default=80, help="max postings this run (hard ceiling)")
    ap.add_argument("--min-interval", type=float, default=1.0,
                    help="seconds between requests to the same host")
    ap.add_argument("--max-requests", type=int, default=1500)
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--no-cache", action="store_true", help="do not write the raw-response cache")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = None if args.no_cache else out / f"_httpcache_{args.company}"

    policy = CollectionPolicy(min_interval_s=args.min_interval, max_requests=args.max_requests,
                              max_postings=args.limit, timeout_s=args.timeout)
    fetcher = Fetcher(cache_dir=cache_dir, min_interval=args.min_interval, timeout=args.timeout,
                      max_requests=args.max_requests, ua=DEFAULT_UA)
    source = SOURCES[args.company]

    try:
        observations, report = collect(source, policy, fetcher, limit_postings=args.limit)
    except PermissionError as exc:
        payload = {"company_key": args.company, "status": "BLOCKED_BY_ROBOTS", "error": str(exc),
                   "collection_status": "BLOCKED", "policy": policy.as_dict()}
        (out / f"collection_{args.company}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"BLOCKED: {exc}")
        return 2

    jobs_path = out / f"jobs_{args.company}.jsonl"
    with jobs_path.open("w", encoding="utf-8") as fh:
        for obs in observations:
            fh.write(json.dumps(obs.to_dict(), ensure_ascii=False) + "\n")

    availability = rec.availability_counts(observations)
    payload = {
        "company_key": args.company,
        "source_label": source.label,
        "source_platform": rec.PLATFORM_PHENOM,
        "source_urls": {"sitemap_index": source.sitemap_index_url,
                        "robots": source.robots_url,
                        "listing": f"{source.base_url}{source.locale_root}/search-results"},
        "collector_version": rec.COLLECTOR_VERSION,
        "schema_version": rec.SCHEMA_VERSION,
        "policy": policy.as_dict(),
        "report": report.as_dict(),
        "availability": availability,
    }
    (out / f"collection_{args.company}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    r = availability["rates"]
    print(f"{source.label}: {availability['n']} postings written to {jobs_path.name}")
    print(f"  ids={r['posting_id']:.2f} desc={r['description_nonempty']:.2f} "
          f"source_date={r['source_date']:.2f} relative_only={r['relative_only']:.2f} "
          f"location={r['location']:.2f}")
    print(f"  details ok/failed = {report.details_ok}/{report.details_failed}; "
          f"sitemaps={report.sitemaps_read}; job urls={report.job_urls_seen}; "
          f"skipped by robots={report.skipped_robots_disallowed}")
    print(f"  requests={fetcher.stats['requests']} cache_hits={fetcher.stats['cache_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
