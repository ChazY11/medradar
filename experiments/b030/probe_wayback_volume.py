"""B-030 probe 3: how much job-posting history does the Wayback CDX hold for one firm?

Uses showNumPages to size the query before fetching, so the run stays bounded and polite.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

CDX = "http://web.archive.org/cdx/search/cdx"


def fetch(params: dict, timeout: int = 90) -> str:
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "MedRadar-research/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def main() -> int:
    for pattern in ("jobs.medtronic.com/job/*", "jobs.medtronic.com/job/*/",
                    "careers.medtronic.com/*"):
        params = {"url": pattern, "showNumPages": "true"}
        try:
            body = fetch(params)
            pages = int(body.strip())
            print(f"{pattern:36s} index_pages={pages}  (~{pages * 15000} captures max)")
        except Exception as exc:  # noqa: BLE001
            print(f"{pattern:36s} numPages FAILED {type(exc).__name__}: {exc}")
            continue
        # sample one page of distinct URLs to see whether real postings dominate
        try:
            body = fetch({"url": pattern, "output": "json", "collapse": "urlkey",
                          "limit": "20", "fl": "timestamp,original,statuscode"})
            rows = json.loads(body) if body.strip().startswith("[") else []
            data = rows[1:] if rows else []
            print(f"    sample distinct urls: {len(data)}")
            for row in data[:5]:
                print(f"      {row}")
        except Exception as exc:  # noqa: BLE001
            print(f"    sample FAILED {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
