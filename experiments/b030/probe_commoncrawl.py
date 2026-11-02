"""B-030 probe: is there a lawful, point-in-time hiring signal in Common Crawl?

Common Crawl is a public web archive with monthly crawls. Its index API is queryable without a
key and returns one JSON line per captured URL, including the crawl timestamp. If company careers
pages are captured, then the number of DISTINCT job-posting URLs under a company's career domain
in a given crawl month is a proxy for its hiring intensity at that time — historical, lawful and
reproducible, which is exactly what the retrospective design needs.

This probe fetches only the index (small JSON), never page content. One crawl, a few domains.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

CRAWL = "CC-MAIN-2024-10"
INDEX = f"https://index.commoncrawl.org/{CRAWL}-index"

DOMAINS = [
    "careers.medtronic.com/*",
    "jobs.medtronic.com/*",
    "boards.greenhouse.io/medtronic*",
    "careers.gehealthcare.com/*",
    "jobs.philips.com/*",
    "careers.philips.com/*",
    "www.draeger.com/en/careers/*",
    "careers.mindray.com/*",
    "jobs.bostonscientific.com/*",
    "careers.stryker.com/*",
]


def query(pattern: str, limit: int = 3) -> dict:
    params = urllib.parse.urlencode({"url": pattern, "output": "json", "limit": limit})
    url = f"{INDEX}?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "MedRadar-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            body = response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return {"pattern": pattern, "error": f"{type(exc).__name__}: {exc}"}
    lines = [line for line in body.splitlines() if line.strip().startswith("{")]
    records = []
    for line in lines[:limit]:
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return {"pattern": pattern, "records": len(records),
            "sample": [{"url": row.get("url"), "timestamp": row.get("timestamp"),
                        "status": row.get("status")} for row in records]}


def main() -> int:
    print(f"crawl: {CRAWL}")
    for pattern in DOMAINS:
        result = query(pattern)
        if "error" in result:
            print(f"  {pattern:44s} ERROR {result['error']}")
        else:
            print(f"  {pattern:44s} records={result['records']}")
            for row in result["sample"][:2]:
                print(f"      {row['timestamp']} {row['status']} {str(row['url'])[:110]}")
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
