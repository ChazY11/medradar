"""B-030 probe: Wayback Machine CDX API as a point-in-time hiring proxy.

The Wayback Machine is a public web archive. Its CDX endpoint lists captures (URL + timestamp)
without a key. If a company's careers domain is archived, the number of DISTINCT job-posting URLs
captured in a given month is a proxy for hiring activity at that time — historical, lawful and
reproducible. This probe issues a few bounded queries only.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

CDX = "http://web.archive.org/cdx/search/cdx"

TARGETS = [
    "careers.medtronic.com",
    "jobs.medtronic.com",
    "careers.gehealthcare.com",
    "jobs.philips.com",
    "careers.bostonscientific.com",
    "careers.stryker.com",
]


def query(domain: str, limit: int = 12) -> dict:
    params = {
        "url": f"{domain}/*",
        "output": "json",
        "from": "2022",
        "to": "2023",
        "collapse": "timestamp:6",
        "limit": limit,
        "fl": "timestamp,original,statuscode",
    }
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    started = time.time()
    request = urllib.request.Request(url, headers={"User-Agent": "MedRadar-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return {"domain": domain, "error": f"{type(exc).__name__}: {exc}",
                "seconds": round(time.time() - started, 1)}
    try:
        rows = json.loads(body) if body.strip().startswith("[") else []
    except ValueError:
        rows = []
    header, data = (rows[0], rows[1:]) if rows else ([], [])
    return {"domain": domain, "seconds": round(time.time() - started, 1),
            "rows": len(data), "header": header,
            "sample": data[:4]}


def main() -> int:
    print("CDX endpoint:", CDX)
    for domain in TARGETS:
        result = query(domain)
        if "error" in result:
            print(f"  {domain:32s} ERROR {result['error']} ({result['seconds']}s)")
        else:
            print(f"  {domain:32s} rows={result['rows']} ({result['seconds']}s)")
            for row in result["sample"][:3]:
                print(f"      {row}")
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
