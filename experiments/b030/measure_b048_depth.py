"""B-048: depth check for the hosts discovered in the ATS battery."""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

CDX = "http://web.archive.org/cdx/search/cdx"
UA = "MedRadar-research/1.0"
DELAY = 0.9
LIMIT = 5000

PATTERNS = [
    ("philips", "philips.taleo.net/careersection/*"),
    ("philips", "philips.avature.net/*"),
    ("zimmer_biomet", "careers.zimmer.com/*"),
    ("zimmer_biomet", "careers.zimmer.com/*job*"),
    ("mindray", "www.mindray.com/en/careers/*"),
    ("draeger", "www.draeger.com/en-us_us/career/*"),
    ("draeger", "www.draeger.com/en_career/*"),
    ("masimo", "masimo.com/*/careers/*"),
]

STATIC = (".css", ".js", ".ico", ".png", ".jpg", ".gif", ".svg", ".pdf", ".woff")
MARKERS = ("/job/", "/jobs/", "jobdetail", "/job-", "jobid", "requisition", "-job-",
           "jobsearch", "/requisition/")


def looks_like_posting(url: str) -> bool:
    lowered = url.lower()
    if lowered.endswith(STATIC):
        return False
    return any(marker in lowered for marker in MARKERS)


def main() -> int:
    rows_out = []
    for company, pattern in PATTERNS:
        try:
            params = {"url": pattern, "output": "json", "fl": "timestamp,original",
                      "collapse": "urlkey", "from": "2015", "to": "2026", "limit": str(LIMIT)}
            url = f"{CDX}?{urllib.parse.urlencode(params)}"
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read().decode("utf-8", "replace")
            rows = json.loads(body) if body.strip().startswith("[") else []
            data = rows[1:] if rows else []
            postings = [row for row in data if looks_like_posting(str(row[1]))]
            months = Counter(str(row[0])[:6] for row in postings)
            record = {"company": company, "pattern": pattern, "urls": len(data),
                      "postings": len(postings), "months": len(months),
                      "truncated": len(data) >= LIMIT,
                      "sample": [str(row[1])[:100] for row in postings[:2]]}
        except Exception as exc:  # noqa: BLE001
            record = {"company": company, "pattern": pattern,
                      "error": f"{type(exc).__name__}: {exc}"}
        rows_out.append(record)
        if record.get("error"):
            print(f"{company:14s} {pattern:44s} ERROR {record['error'][:40]}")
        else:
            print(f"{company:14s} {pattern:44s} urls={record['urls']:5d} "
                  f"postings={record['postings']:5d} months={record['months']:3d}")
        time.sleep(DELAY)
    payload = {"design": {"purpose": "B-048 depth check for discovered hosts",
                          "limit": LIMIT, "from": "2015", "to": "2026"},
               "hosts": rows_out,
               "summary": {"hosts_with_50plus_postings":
                           sum(1 for row in rows_out if (row.get("postings") or 0) >= 50),
                           "hosts_with_24plus_months":
                           sum(1 for row in rows_out if (row.get("months") or 0) >= 24)}}
    Path("experiments/b030/depth_b048.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nsummary:", payload["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
