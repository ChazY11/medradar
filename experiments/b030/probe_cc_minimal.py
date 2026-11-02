"""Minimal Common Crawl index connectivity check: does ANY query answer?"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

TRIES = [
    ("CC-MAIN-2024-10", "example.com", "domain", 2),
    ("CC-MAIN-2024-10", "medtronic.com", "domain", 2),
    ("CC-MAIN-2023-50", "medtronic.com", "domain", 2),
    ("CC-MAIN-2020-05", "careers.medtronic.com", "domain", 2),
]


def attempt(crawl: str, target: str, match: str, limit: int) -> dict:
    index = f"https://index.commoncrawl.org/{crawl}-index"
    params = urllib.parse.urlencode({"url": target, "matchType": match,
                                     "output": "json", "limit": limit})
    url = f"{index}?{params}"
    started = time.time()
    request = urllib.request.Request(url, headers={"User-Agent": "MedRadar-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "error": f"{type(exc).__name__}: {exc}",
                "seconds": round(time.time() - started, 1)}
    lines = [line for line in body.splitlines() if line.strip().startswith("{")]
    return {"url": url, "seconds": round(time.time() - started, 1),
            "lines": len(lines), "first": json.loads(lines[0]) if lines else None}


def main() -> int:
    for crawl, target, match, limit in TRIES:
        result = attempt(crawl, target, match, limit)
        print(json.dumps({key: (str(value)[:150] if key == "first" else value)
                          for key, value in result.items()}, indent=1))
        print("-" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
