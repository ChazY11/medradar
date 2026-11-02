"""B-047 measurement: does the archive actually hold enough job-level URLs?

Host discovery found ATS boards for seven more firms. The open question is whether archive DEPTH,
not domain guessing, is the binding constraint. This measures, per host, the number of distinct
job-posting-like URLs in 2014-2026 and the number of distinct months they span.

One bounded request per host (collapse=urlkey, generous limit), so the run is short and polite.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

CDX = "http://web.archive.org/cdx/search/cdx"
UA = "MedRadar-research/1.0"
DELAY = 0.8
LIMIT = "5000"

#: (company, pattern, kind) discovered by probe_ats_hosts.py and the earlier panel run.
HOSTS = [
    ("medtronic", "jobs.medtronic.com/job/*", "careers-host"),
    ("medtronic", "medtronic.taleo.net/careersection/*", "ats"),
    ("bd", "jobs.bd.com/job/*", "careers-host"),
    ("bd", "boards.greenhouse.io/bdainc*", "ats"),
    ("boston_scientific", "jobs.bostonscientific.com/job/*", "careers-host"),
    ("dexcom", "careers.dexcom.com/job/*", "careers-host"),
    ("dexcom", "dexcom.wd1.myworkdayjobs.com/*", "ats"),
    ("edwards_lifesciences", "www.edwards.com/careers/job/*", "careers-host"),
    ("intuitive_surgical", "careers.intuitive.com/job/*", "careers-host"),
    ("intuitive_surgical", "careers.smartrecruiters.com/intuitive*", "ats"),
    ("stryker", "careers.stryker.com/jobs/*", "careers-host"),
    ("ge_healthcare", "gehealthcare.wd5.myworkdayjobs.com/*", "ats"),
    ("abbott", "abbott.taleo.net/careersection/*", "ats"),
    ("baxter", "baxter.taleo.net/careersection/*", "ats"),
    ("hologic", "hologic.taleo.net/careersection/*", "ats"),
]


def looks_like_posting(url: str) -> bool:
    lowered = url.lower()
    if lowered.endswith((".css", ".js", ".ico", ".png", ".jpg", ".gif")):
        return False
    markers = ("/job/", "/jobs/", "jobdetail", "/job-", "careersection", "myworkdayjobs.com/en-us")
    return any(marker in lowered for marker in markers)


def fetch(pattern: str) -> list[list[str]]:
    params = {"url": pattern, "output": "json", "fl": "timestamp,original",
              "collapse": "urlkey", "from": "2014", "to": "2026", "limit": LIMIT}
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read().decode("utf-8", "replace")
    rows = json.loads(body) if body.strip().startswith("[") else []
    return rows[1:] if rows else []


def main() -> int:
    results = []
    for company, pattern, kind in HOSTS:
        try:
            rows = fetch(pattern)
            postings = [row for row in rows if looks_like_posting(str(row[1]))]
            months = Counter(str(row[0])[:6] for row in postings)
            results.append({
                "company": company, "pattern": pattern, "kind": kind,
                "distinct_urls": len(rows), "posting_urls": len(postings),
                "months": len(months),
                "months_with_5plus": sum(1 for count in months.values() if count >= 5),
                "first": str(postings[0][0]) if postings else None,
                "last": str(postings[-1][0]) if postings else None,
            })
            print(f"{company:20s} {kind:13s} urls={len(rows):5d} postings={len(postings):5d} "
                  f"months={len(months):3d} months>=5={results[-1]['months_with_5plus']:3d} "
                  f"{results[-1]['first']}..{results[-1]['last']}")
        except Exception as exc:  # noqa: BLE001
            results.append({"company": company, "pattern": pattern, "kind": kind,
                            "error": f"{type(exc).__name__}: {exc}"})
            print(f"{company:20s} {kind:13s} ERROR {type(exc).__name__}")
        time.sleep(DELAY)

    payload = {
        "design": {
            "purpose": ("decide whether the hiring lane's coverage limit is domain discovery or "
                        "archive depth"),
            "method": "one bounded CDX request per host; collapse=urlkey; 2014-2026",
            "posting_filter": "URL contains /job/, /jobs/, jobdetail, /job-, careersection or a "
                              "Workday job path; static assets excluded",
        },
        "hosts": results,
        "summary": {
            "hosts_measured": len(results),
            "hosts_with_50plus_postings": sum(1 for row in results
                                              if (row.get("posting_urls") or 0) >= 50),
            "hosts_with_24plus_months": sum(1 for row in results
                                            if (row.get("months") or 0) >= 24),
            "max_posting_urls": max((row.get("posting_urls") or 0) for row in results),
        },
    }
    from pathlib import Path
    Path("experiments/b030/host_depth.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nsummary:", payload["summary"])
    print("wrote experiments/b030/host_depth.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
