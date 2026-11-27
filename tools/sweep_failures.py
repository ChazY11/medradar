#!/usr/bin/env python3
"""Sweep the MAUDE failure corpus for product codes that have never been covered.

Why this exists
---------------
`/sources` has said for weeks: "失效记录只扫了 838 个产品码，注册表里共有 5,229 个". That sentence was
true and permanent, because nothing in the deployment ever advanced it - `build_failure_index` had no
caller outside the tests. A coverage number that can never move is not a caveat, it is a standing
apology.

This tool sweeps a bounded number of un-swept codes per run, in the order of how many registered
devices carry each code, so the codes that affect the most dossiers come first. It is meant to run
from the nightly job: ten minutes a night, at a request rate the openFDA endpoint tolerates.

Every run records what it covered, so the next run continues rather than repeating.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medradar.radar.code_census import pending_codes, product_code_census  # noqa: E402
from medradar.radar.failure_index import build_failure_index, index_summary  # noqa: E402
from medradar.radar.http import HostPolicy, PoliteFetcher  # noqa: E402
from medradar.radar.reference import UdiReference  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--codes", type=int, default=40,
                        help="how many un-swept product codes to cover in this run")
    parser.add_argument("--pages-per-code", type=int, default=3,
                        help="pages of 1,000 events per code; the openFDA skip cap is 25,000")
    parser.add_argument("--rate", type=float, default=3.0, help="requests per second to openFDA")
    parser.add_argument("--since", default="2015-01-01")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    store = UdiReference(args.db)
    started = time.time()
    report: dict = {"ok": False, "codes": [], "errors": []}
    try:
        census, pending = pending_codes(store, max_codes=args.codes)
        report["registered_codes"] = len(census)
        report["pending_before"] = len(pending)
        if not pending:
            report.update(ok=True, swept=0, note="every registered product code has already been swept")
            print(json.dumps(report, ensure_ascii=False) if args.json else "无可扫产品码")
            return 0

        fetcher = PoliteFetcher(
            policies={"api.fda.gov": HostPolicy(requests_per_second=max(0.1, args.rate))},
            max_requests=max(20, args.codes * args.pages_per_code * 2),
        )
        stats = build_failure_index(fetcher, store, pending,
                                    since=args.since,
                                    max_pages_per_code=args.pages_per_code)
        report.update(ok=True, swept=len(pending), codes=pending,
                      events_seen=stats.events_seen, rows_written=stats.rows_written,
                      pages=stats.pages, elapsed_seconds=round(time.time() - started, 1))
        summary = index_summary(store)
        report["index"] = summary
    except Exception as error:  # noqa: BLE001 - the nightly job must never die on one sweep
        report["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass

    if args.json:
        print(json.dumps(report, ensure_ascii=False, default=str))
    else:
        if report.get("swept"):
            print(f"扫描 {report['swept']} 个产品码，写入 {report.get('rows_written', 0)} 行，"
                  f"用时 {report.get('elapsed_seconds')}s")
        for line in report.get("errors") or []:
            print(f"错误: {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
