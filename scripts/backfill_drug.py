"""Resumable full-history Drugs@FDA backfill -> ``drug_approval`` events.

Why a script instead of ``python -m medradar collect --sources drug``?

* The collector deliberately stops at ``skip`` 25 000 (openFDA's documented deep
  paging limit). The full Drugs@FDA corpus is now 26 665 applications, so the
  last ~665 documents - and their original approvals - are unreachable with a
  single ``[start TO end]`` query. This script partitions the window into
  sub-windows that are each shallow enough to page to the end (default: 5-year
  chunks), so every application is scanned.
* openFDA load-sheds broad searches with transient HTTP 500s
  (``rejected_execution_exception``), so a one-shot CLI run stops at the first
  bad page. This script caches every successful page under ``data/cache/`` and
  records failed pages without aborting the other chunks; simply re-running it
  replays cached pages for free and resumes at the first missing page.

It re-uses the tested collector helpers (``normalize_approval`` / NDA/BLA +
ORIG/AP filters / registries) and the same ``event_id`` hash, so it is
idempotent with the CLI collector - no package code is modified.

Usage::

    $env:PYTHONPATH="D:\\DEPPSKK\\medradar"
    python scripts/backfill_drug.py --db data/medradar.sqlite --months 720 --budget 120
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar.collect_drug import (  # noqa: E402
    API_URL,
    KIND,
    PAGE_LIMIT,
    SOURCE,
    is_nda_or_bla,
    normalize_approval,
    window,
)
from medradar.config import CACHE_DIR, load_companies, load_tracks  # noqa: E402
from medradar.db import DB  # noqa: E402
from medradar.http import Fetcher, NotFound  # noqa: E402
from medradar.util import parse_date, today_utc  # noqa: E402

#: openFDA refuses ``skip`` above this value (verified: skip=25000 works,
#: skip=26000 returns HTTP 400). Each chunk must therefore stay below it.
SAFE_SKIP = 25_000


def shift_months(day: date, months: int) -> date:
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def build_chunks(start: date, end: date, chunk_months: int) -> list[tuple[date, date]]:
    """Split ``[start, end]`` into consecutive inclusive sub-windows."""
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor < end:
        nxt = min(shift_months(cursor, chunk_months), end)
        chunks.append((cursor, nxt))
        if nxt == end:
            break
        cursor = nxt
    return chunks or [(start, end)]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "medradar.sqlite"))
    parser.add_argument("--months", type=int, default=720, help="lookback window (60y)")
    parser.add_argument("--budget", type=int, default=120, help="max HTTP requests (cache hits are free)")
    parser.add_argument("--chunk-months", type=int, default=60, help="sub-window size so each chunk pages out")
    parser.add_argument("--retries", type=int, default=5, help="retries per page on transient 5xx")
    parser.add_argument("--backoff", type=float, default=2.0)
    parser.add_argument("--min-interval", type=float, default=0.3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    start, end = window(args.months)
    chunks = build_chunks(start, end, max(1, args.chunk_months))

    registry = load_companies("drug")
    with DB(args.db) as db:
        db.upsert_companies(registry.all())
        db.upsert_tracks(load_tracks("drug").all())

        fetcher = Fetcher(
            cache_dir=CACHE_DIR, min_interval=args.min_interval, max_requests=args.budget
        )
        events: dict[str, dict[str, Any]] = {}
        documents = 0
        pages = 0
        failed_pages: list[dict[str, Any]] = []
        truncated = False
        chunk_reports: list[dict[str, Any]] = []
        requests_start = fetcher.stats["requests"]

        for chunk_start, chunk_end in chunks:
            search = (
                "submissions.submission_status_date:"
                f"[{chunk_start.strftime('%Y%m%d')} TO {chunk_end.strftime('%Y%m%d')}]"
            )
            chunk_docs = 0
            chunk_pages = 0
            chunk_events_before = len(events)
            total = 0
            skip = 0
            while True:
                if fetcher.stats["requests"] >= args.budget - 1:
                    truncated = True
                    break
                try:
                    payload = fetcher.get_json(
                        API_URL,
                        {"search": search, "limit": PAGE_LIMIT, "skip": skip},
                        retries=args.retries,
                        backoff=args.backoff,
                    )
                except NotFound:
                    break
                except Exception as exc:  # noqa: BLE001 - keep progress, retry next run
                    failed_pages.append(
                        {
                            "chunk": [chunk_start.isoformat(), chunk_end.isoformat()],
                            "skip": skip,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    print(
                        f"[backfill_drug] {chunk_start}..{chunk_end} skip={skip} failed: "
                        f"{type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )
                    break

                chunk_pages += 1
                pages += 1
                results = (payload or {}).get("results") or []
                total = int(
                    (((payload or {}).get("meta") or {}).get("results") or {}).get("total")
                    or total
                )
                if not results:
                    break
                chunk_docs += len(results)
                documents += len(results)
                for record in results:
                    if not isinstance(record, dict):
                        continue
                    application_number = str(record.get("application_number") or "")
                    if not is_nda_or_bla(application_number):
                        continue
                    sponsor = str(record.get("sponsor_name") or "")
                    company_key, confidence, alias = registry.resolve(sponsor)
                    for submission in record.get("submissions") or []:
                        if not isinstance(submission, dict):
                            continue
                        event = normalize_approval(
                            record,
                            submission,
                            company_key=company_key,
                            confidence=confidence,
                            alias=alias,
                        )
                        if event is None:
                            continue
                        decided = parse_date(event["event_date"])
                        if decided is None or decided < start or decided > end:
                            continue
                        events[event["event_id"]] = event
                skip += PAGE_LIMIT
                if total and skip >= total:
                    break
                if skip > SAFE_SKIP:
                    failed_pages.append(
                        {
                            "chunk": [chunk_start.isoformat(), chunk_end.isoformat()],
                            "skip": skip,
                            "error": "chunk deeper than openFDA skip cap; lower --chunk-months",
                        }
                    )
                    break
            chunk_reports.append(
                {
                    "window": [chunk_start.isoformat(), chunk_end.isoformat()],
                    "documents_total": total,
                    "documents_scanned": chunk_docs,
                    "pages": chunk_pages,
                    "events": len(events) - chunk_events_before,
                }
            )

        chosen = sorted(events.values(), key=lambda event: event["event_date"])
        inserted = db.upsert_events(chosen) if chosen else 0
        if inserted:
            db.log_run("backfill_drug", {"events": inserted, "pages": pages})

        report = {
            "source": SOURCE,
            "kind": KIND,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "chunks": len(chunks),
            "documents_scanned": documents,
            "pages": pages,
            "events_upserted": inserted,
            "failed_pages": failed_pages,
            "truncated": truncated,
            "requests": fetcher.stats["requests"] - requests_start,
            "cache_hits": fetcher.stats["cache_hits"],
            "retries": fetcher.stats["retries"],
            "per_chunk": chunk_reports,
        }
        print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
