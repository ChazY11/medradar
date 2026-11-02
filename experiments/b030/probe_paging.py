"""B-047 probe: does CDX paging work with pageSize/page (vs limit/page)?"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

CDX = "http://web.archive.org/cdx/search/cdx"
UA = "MedRadar-research/1.0"
PATTERN = "medtronic.taleo.net/careersection/*"


def run(params: dict, timeout: int = 90) -> list[list[str]]:
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
    rows = json.loads(body) if body.strip().startswith("[") else []
    return rows[1:] if rows else []


def main() -> int:
    base = {"url": PATTERN, "output": "json", "fl": "timestamp,original",
            "collapse": "urlkey", "from": "2016", "to": "2026"}
    print("== variant A: limit + page (what the previous collector used) ==")
    for page in (0, 1):
        try:
            rows = run({**base, "limit": "200", "page": str(page)}, timeout=60)
            print(f"  page={page} rows={len(rows)} first={rows[0] if rows else None}")
        except Exception as exc:  # noqa: BLE001
            print(f"  page={page} FAILED {type(exc).__name__}")
        time.sleep(0.6)
    print("== variant B: pageSize + page ==")
    for page in (0, 1, 2):
        try:
            rows = run({**base, "pageSize": "500", "page": str(page)}, timeout=90)
            print(f"  page={page} rows={len(rows)} "
                  f"first={rows[0][1][:80] if rows else None}")
        except Exception as exc:  # noqa: BLE001
            print(f"  page={page} FAILED {type(exc).__name__}")
        time.sleep(0.6)
    print("== variant C: showNumPages ==")
    try:
        url = f"{CDX}?{urllib.parse.urlencode({**base, 'showNumPages': 'true'})}"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}),
                                    timeout=60) as response:
            print("  numPages:", response.read().decode().strip())
    except Exception as exc:  # noqa: BLE001
        print("  numPages FAILED", type(exc).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
