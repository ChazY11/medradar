"""Bounded, re-enterable collection of public job postings from a Beesite job board.

Usage
-----
    python scripts/collect_recruitment_beesite.py --company draeger --limit 80 \
        --out experiments/innovation_signals_observatory/results/2026-11-04

What it writes (all inside ``--out``):

  ``jobs_<company>.jsonl``        one JobObservation per line (append-only snapshot)
  ``collection_<company>.json``   run report: totals, robots evidence for both hosts,
                                  request stats, per-field availability rates, failures
  ``_httpcache_<company>/``       raw HTTP responses (audit trail; not the dataset)

Safety properties (each is tested in ``tests/test_recruitment_beesite.py``):

  * both hosts' robots.txt answers are recorded verbatim before the first data request;
    the Beesite host publishes none (HTTP 404) and the RFC 9309 unavailable rule is
    applied explicitly, never assumed away;
  * bounded by ``--limit`` postings and ``--max-requests`` HTTP calls;
  * a posting page that fails is kept as a ``DETAIL_FAILED`` observation that still carries
    the search API's own title/date/organisation — a fetch failure is never "no description";
  * the source's own ``datePosted`` (or, on failure, ``PublicationStartDate``) is kept with
    day precision; nothing is invented; ``ParentOrganizationName`` is recorded as the
    source's claim, not resolved to a universe entity key.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.http import Fetcher  # noqa: E402
from medradar.recruitment import records as rec  # noqa: E402
from medradar.recruitment.beesite import SOURCES, collect  # noqa: E402
from medradar.recruitment.politeness import CollectionPolicy, DEFAULT_UA  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True, choices=sorted(SOURCES))
    ap.add_argument("--out", required=True, help="results directory for this snapshot")
    ap.add_argument("--limit", type=int, default=80, help="max postings this run (hard ceiling)")
    ap.add_argument("--min-interval", type=float, default=1.0,
                    help="seconds between requests to the same host")
    ap.add_argument("--max-requests", type=int, default=400)
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
        "source_platform": rec.PLATFORM_BEESITE,
        "source_urls": {"search_api": source.search_base + source.search_path,
                        "search_url_masked": source.search_base + source.search_path + "?data=<json>",
                        "jobad_page": source.portal_base + "/index.php?ac=jobad&id=<id>",
                        "robots": list(source.robots_urls)},
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
          f"location={r['location']:.2f} legal_entity={r['legal_entity']:.2f}")
    print(f"  details ok/failed = {report.details_ok}/{report.details_failed}; "
          f"search total reported={report.search_result_count_all} "
          f"(this page {report.search_result_count}); items={report.items_returned}")
    print(f"  requests={fetcher.stats['requests']} cache_hits={fetcher.stats['cache_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
