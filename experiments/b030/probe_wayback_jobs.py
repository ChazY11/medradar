"""B-030 probe 2: are individual job-posting URLs archived (not just careers homepages)?

If yes, counting distinct posting URLs captured per month gives a real hiring-intensity proxy.
If no, the Wayback route collapses to a crawl-density proxy and cannot measure hiring.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

CDX = "http://web.archive.org/cdx/search/cdx"

PATTERNS = [
    ("jobs.medtronic.com/job/*", 2022, 2024),
    ("jobs.medtronic.com/*job*", 2022, 2024),
    ("careers.stryker.com/job/*", 2022, 2024),
    ("careers.stryker.com/*job*", 2022, 2024),
    ("jobs.philips.com/*", 2019, 2021),
    ("www.medtronic.com/us-en/about/careers.html", 2019, 2021),
    ("boards.greenhouse.io/medtronic*", 2022, 2024),
    ("www.indeed.com/q-medtronic*", 2019, 2021),
]


def query(pattern: str, start: int, end: int, limit: int = 8) -> dict:
    params = {
        "url": pattern,
        "output": "json",
        "from": str(start),
        "to": str(end),
        "limit": limit,
        "fl": "timestamp,original,statuscode",
        "collapse": "urlkey",
    }
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    started = time.time()
    request = urllib.request.Request(url, headers={"User-Agent": "MedRadar-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return {"pattern": pattern, "error": f"{type(exc).__name__}: {exc}",
                "seconds": round(time.time() - started, 1)}
    rows = json.loads(body) if body.strip().startswith("[") else []
    data = rows[1:] if rows else []
    return {"pattern": pattern, "seconds": round(time.time() - started, 1),
            "urls": len(data), "sample": data[:5]}


def main() -> int:
    for pattern, start, end in PATTERNS:
        result = query(pattern, start, end)
        if "error" in result:
            print(f"  {pattern:44s} ERROR {result['error']}")
        else:
            print(f"  {pattern:44s} distinct_urls={result['urls']} "
                  f"({result['seconds']}s)")
            for row in result["sample"][:3]:
                print(f"      {row}")
        time.sleep(0.8)
    return 0


if __name__ == "__main__":
    sys.exit(main())
