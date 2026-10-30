"""Deep, resumable ClinicalTrials.gov backfill -> ``trial`` events.

Why a script instead of ``python -m medradar collect --sources trials``?

* The collector's documented cap is 3 pages (300 newest studies) per sponsor term
  and 360 requests per run, which only reaches the last ~5-8 years for a big
  pharma sponsor - not the 60-year window requested for the full-history build.
* This script pages the same CT.gov v2 queries (identical URL parameters, so it
  shares ``data/cache/`` with the collector) much deeper, round-robin across
  every sponsor term so large sponsors cannot starve the small ones, and stops
  exactly at the request budget.
* Each page is normalised with the package helpers and upserted immediately, so
  the run is idempotent and resumable: re-running replays cached pages for free
  and continues from the first uncached page.

Nothing in ``medradar/`` is modified; all normalisation / attribution /
payload-contract logic is imported from ``medradar.clinical``.

Usage::

    $env:PYTHONPATH="D:\\DEPPSKK\\medradar"
    python scripts/backfill_trials.py --db data/medradar.sqlite --months 720 --budget 900
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar import clinical  # noqa: E402
from medradar.config import CACHE_DIR, CompanyRegistry, load_companies, load_tracks  # noqa: E402
from medradar.db import DB  # noqa: E402
from medradar.http import Fetcher  # noqa: E402
from medradar.util import parse_date, today_utc  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "medradar.sqlite"))
    parser.add_argument("--months", type=int, default=720, help="lookback window (60y)")
    parser.add_argument("--budget", type=int, default=900, help="max HTTP requests (cache hits free)")
    parser.add_argument("--min-interval", type=float, default=0.3)
    parser.add_argument("--per-term-cap", type=int, default=200, help="max pages per sponsor term")
    return parser.parse_args(argv)


def load_pool() -> list[dict[str, Any]]:
    """Drug pool first, then device pool (same merge order as collect_trials)."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for kind in ("drug", "device"):
        for company in load_companies(kind).all():
            if company["key"] not in seen:
                seen.add(company["key"])
                merged.append(company)
    return merged


def page_params(term: str, start: date, end: date, token: str | None) -> dict[str, Any]:
    """Mirror ``clinical._fetch_term`` parameter order so cache URLs match."""
    params: dict[str, Any] = {
        "query.spons": term,
        "pageSize": clinical.PAGE_SIZE,
        "countTotal": "true",
        "fields": clinical.FIELDS,
        "sort": "StudyFirstPostDate:desc",
        "filter.advanced": (
            f"AREA[StudyFirstPostDate]RANGE[{start.isoformat()},{end.isoformat()}]"
        ),
    }
    if token:
        params["pageToken"] = token
    return params


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    start, end = clinical.window(args.months)
    as_of = today_utc().isoformat()
    companies = load_pool()
    registry = CompanyRegistry(companies)
    drug_tracks = load_tracks("drug")
    device_tracks = load_tracks("device")
    terms = clinical.plan_terms(companies)

    counters = {
        "studies": 0,
        "interventional": 0,
        "out_of_window": 0,
        "unmatched_company": 0,
        "matched_company": 0,
        "track_matched": 0,
        "events_written": 0,
        "failed_pages": [],
    }
    seen_events: set[str] = set()
    term_state: dict[str, dict[str, Any]] = {
        term: {"token": None, "total": 0, "pages": 0, "done": False, "bytes": 0}
        for term in terms
    }

    with DB(args.db) as db:
        db.upsert_companies(registry.all())
        db.upsert_tracks(drug_tracks.all())
        db.upsert_tracks(device_tracks.all())
        fetcher = Fetcher(
            cache_dir=CACHE_DIR, min_interval=args.min_interval, max_requests=args.budget
        )
        requests_start = fetcher.stats["requests"]
        cache_start = fetcher.stats["cache_hits"]

        def fetch_page(term: str) -> int:
            """Fetch one page for ``term``; returns number of studies processed."""
            state = term_state[term]
            if state["done"] or fetcher.stats["requests"] >= args.budget - 2:
                return 0
            try:
                payload = fetcher.get_json(
                    clinical.API_URL,
                    page_params(term, start, end, state["token"]),
                    retries=5,
                    backoff=2.0,
                )
            except Exception as exc:  # noqa: BLE001 - record and move on, resumable
                state["done"] = True
                counters["failed_pages"].append(
                    f"{term} (token={'yes' if state['token'] else 'first'}): "
                    f"{type(exc).__name__}: {exc}"
                )
                print(f"[backfill_trials] {term} failed: {exc}", file=sys.stderr)
                return 0

            state["pages"] += 1
            batch = (payload or {}).get("studies") or []
            state["total"] = int((payload or {}).get("totalCount") or state["total"] or 0)
            state["token"] = (payload or {}).get("nextPageToken")
            if len(batch) < clinical.PAGE_SIZE or not state["token"]:
                state["done"] = True
            events: dict[str, dict[str, Any]] = {}
            for study in batch:
                if not isinstance(study, Mapping):
                    continue
                counters["studies"] += 1
                normalized = clinical.normalize_study(study)
                if normalized is None:
                    continue
                counters["interventional"] += 1
                posted = parse_date(normalized["first_posted"])
                if posted is None or posted < start or posted > end:
                    counters["out_of_window"] += 1
                    continue
                lead = normalized.get("lead_sponsor") or ""
                company_key, confidence, alias = registry.resolve(lead)
                if company_key:
                    counters["matched_company"] += 1
                else:
                    counters["unmatched_company"] += 1
                track_id = drug_tracks.match_text(" ".join(normalized.get("conditions") or []))
                if track_id:
                    counters["track_matched"] += 1
                event = clinical.build_event(
                    normalized,
                    company_key=company_key,
                    confidence=confidence,
                    alias=alias,
                    track_id=track_id,
                    as_of=as_of,
                )
                events[event["event_id"]] = event
                seen_events.add(event["event_id"])
            if events:
                counters["events_written"] += db.upsert_events(events.values())
            return len(batch)

        # Pass 0 (discovery): one page per sponsor term, fair to everyone.
        for index, term in enumerate(terms, start=1):
            if fetcher.stats["requests"] >= args.budget - 2:
                break
            fetch_page(term)
            if index % 25 == 0:
                print(
                    f"[backfill_trials] discovery {index}/{len(terms)} terms, "
                    f"{counters['studies']} studies, {fetcher.stats['requests']} requests",
                    file=sys.stderr,
                )

        # Remaining passes: one more page per unfinished term each round.
        while fetcher.stats["requests"] < args.budget - 2:
            progress = 0
            for term in terms:
                state = term_state[term]
                if state["done"] or state["pages"] >= args.per_term_cap:
                    state["done"] = True
                    continue
                if fetcher.stats["requests"] >= args.budget - 2:
                    break
                if fetch_page(term):
                    progress += 1
            if progress == 0:
                break
            print(
                f"[backfill_trials] pass done: {counters['studies']} studies, "
                f"{counters['events_written']} upserts, {fetcher.stats['requests']} requests",
                file=sys.stderr,
            )
            time.sleep(0.0)

        pages = sum(state["pages"] for state in term_state.values())
        depths = [state["pages"] for state in term_state.values()]
        unfinished = [term for term, state in term_state.items() if not state["done"]]
        report = {
            "source": clinical.SOURCE,
            "kind": clinical.KIND,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "sponsor_terms": len(terms),
            "pages": pages,
            "terms_complete": len(terms) - len(unfinished),
            "terms_unfinished": len(unfinished),
            "depth_pages": {
                "min": min(depths) if depths else 0,
                "median": median(depths) if depths else 0,
                "max": max(depths) if depths else 0,
            },
            "studies_seen": counters["studies"],
            "interventional": counters["interventional"],
            "out_of_window": counters["out_of_window"],
            "events_upserted": counters["events_written"],
            "unique_events": len(seen_events),
            "matched_company": counters["matched_company"],
            "unmatched_company": counters["unmatched_company"],
            "match_rate": round(
                counters["matched_company"] / counters["interventional"], 4
            )
            if counters["interventional"]
            else 0.0,
            "track_matched": counters["track_matched"],
            "track_match_rate": round(
                counters["track_matched"] / counters["interventional"], 4
            )
            if counters["interventional"]
            else 0.0,
            "requests": fetcher.stats["requests"] - requests_start,
            "cache_hits": fetcher.stats["cache_hits"] - cache_start,
            "failed_pages": counters["failed_pages"],
            "truncated": bool(unfinished) and fetcher.stats["requests"] >= args.budget - 2,
        }
        db.log_run("backfill_trials", {"events": counters["events_written"], "pages": pages})
        print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
