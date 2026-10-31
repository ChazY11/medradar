"""Fetch daily bars for corpus tickers that still lack usable price history.

The case library skips an event when its ticker has fewer than ten price rows, so
this script targets exactly those tickers instead of re-downloading everything.
Yahoo 404s (delisted or renamed symbols) are reported, not retried forever.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from medradar.cases import corpus_tickers
from medradar.config import CACHE_DIR
from medradar.db import DB
from medradar.http import Fetcher
from medradar.prices import fetch_prices


def main(corpus_path: str, db_path: str, budget: int = 900) -> int:
    tickers = corpus_tickers(corpus_path)
    with DB(db_path) as db:
        rows = db.query("SELECT ticker, COUNT(*) AS n FROM prices GROUP BY ticker")
        counts = {row["ticker"]: int(row["n"]) for row in rows}
        missing = [ticker for ticker in tickers if counts.get(ticker, 0) < 10]
        print(f"corpus tickers={len(tickers)} missing_or_short={len(missing)}")
        if not missing:
            return 0
        fetcher = Fetcher(cache_dir=CACHE_DIR, min_interval=0.5, max_requests=budget)
        result = fetch_prices(db, fetcher, missing[:budget], years=10, benchmarks=())
    payload = {
        "attempted": len(missing[:budget]),
        "ok": len(result.get("ok") or []),
        "failed": len(result.get("failed") or []),
        "failed_sample": (result.get("failed") or [])[:10],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    corpus = sys.argv[1] if len(sys.argv) > 1 else "data/edgar_corpus/corpus_v2.jsonl"
    database = sys.argv[2] if len(sys.argv) > 2 else "data/medradar.sqlite"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 900
    raise SystemExit(main(corpus, database, limit))
