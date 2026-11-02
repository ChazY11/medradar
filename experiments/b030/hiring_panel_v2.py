"""B-047: rebuild the hiring panel with per-host queries that do not silently truncate.

What went wrong in cycle 9: the collector used `collapse=urlkey` together with `limit` + `page`
pagination. That combination does not page here — it returns one capped page — so most of the
archive was invisible and the panel looked empty. A direct measurement (measure_host_depth.py) shows
the same hosts hold thousands of posting URLs: Boston Scientific 4,999 over 123 months, Medtronic
4,984 over 46, BD 4,672 over 66, Stryker 3,878.

This version:
  * queries each host ONCE with a generous limit (no pagination pretence), records whether the
    result hit the cap so truncation is visible rather than hidden;
  * merges several hosts per company (career site + ATS board);
  * keeps each posting URL's earliest capture month, so a month counts NEW postings;
  * records the posting-URL "shape" (path template) so a platform migration can be told apart from
    a hiring change.

Usage:
    python experiments/b030/hiring_panel_v2.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402

CDX = "http://web.archive.org/cdx/search/cdx"
UA = "MedRadar-research/1.0"
DELAY = 0.8
LIMIT = 5000
FROM, TO = "2014", "2026"

#: host patterns per company; discovered by probe_ats_hosts.py and measure_host_depth.py
HOSTS: dict[str, list[str]] = {
    "medtronic": ["jobs.medtronic.com/job/*", "medtronic.taleo.net/careersection/*"],
    "bd": ["jobs.bd.com/job/*", "boards.greenhouse.io/bdainc*"],
    "boston_scientific": ["jobs.bostonscientific.com/job/*"],
    "stryker": ["careers.stryker.com/jobs/*", "careers.stryker.com/job/*"],
    "dexcom": ["careers.dexcom.com/job/*", "dexcom.wd1.myworkdayjobs.com/*"],
    "abbott": ["abbott.taleo.net/careersection/*"],
    "intuitive_surgical": ["careers.intuitive.com/job/*",
                           "careers.smartrecruiters.com/intuitive*"],
    "edwards_lifesciences": ["www.edwards.com/careers/job/*"],
    "baxter": ["baxter.taleo.net/careersection/*"],
    "hologic": ["hologic.taleo.net/careersection/*"],
    "ge_healthcare": ["gehealthcare.wd5.myworkdayjobs.com/*"],
    "philips": ["philips.taleo.net/careersection/*", "philips.wd3.myworkdayjobs.com/*"],
    # B-048: boards found by archived-career-URL search and the ATS-host battery
    "draeger": ["www.draeger.com/en-us_us/career/*", "www.draeger.com/job/*",
                "draeger.taleo.net/careersection/*"],
    "mindray": ["mindray.com/careers/*", "jobs.mindray.com/*",
                "www.mindray.com/en/careers/*"],
    "zimmer_biomet": ["careers.zimmer.com/*", "zimmerbiomet.wd5.myworkdayjobs.com/*",
                      "careers.zimmerbiomet.com/job/*"],
    "masimo": ["masimo.wd1.myworkdayjobs.com/*", "www.masimo.com/careers/*"],
}

STATIC = (".css", ".js", ".ico", ".png", ".jpg", ".gif", ".svg", ".woff", ".woff2")
POSTING_MARKERS = ("/job/", "/jobs/", "jobdetail", "/job-", "careersection",
                   "myworkdayjobs.com/en-us", "gh_jid=", "/job/")


def looks_like_posting(url: str) -> bool:
    lowered = url.lower()
    if lowered.endswith(STATIC):
        return False
    return any(marker in lowered for marker in POSTING_MARKERS)


def url_shape(url: str) -> str:
    """Coarse path template: replace digits and slug words with placeholders."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    path = re.sub(r"/[^/]*\d[^/]*(?=/|$)", "/<id>", path)
    tokens = [token for token in path.split("/") if token]
    keep = [token if not re.search(r"[a-z]{4,}", token) else "<slug>" for token in tokens[:4]]
    return (parsed.netloc + "/" + "/".join(keep))[:80]


def fetch(pattern: str) -> tuple[list[list[str]], bool]:
    params = {"url": pattern, "output": "json", "fl": "timestamp,original",
              "collapse": "urlkey", "from": FROM, "to": TO, "limit": str(LIMIT)}
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read().decode("utf-8", "replace")
    rows = json.loads(body) if body.strip().startswith("[") else []
    data = rows[1:] if rows else []
    return data, len(data) >= LIMIT


def main() -> int:
    panel: dict[str, dict] = {}
    for company, patterns in HOSTS.items():
        earliest: dict[str, str] = {}
        hosts_used = []
        truncated_any = False
        for pattern in patterns:
            try:
                rows, truncated = fetch(pattern)
            except Exception as exc:  # noqa: BLE001
                print(f"{company:20s} {pattern:44s} ERROR {type(exc).__name__}")
                time.sleep(DELAY)
                continue
            truncated_any = truncated_any or truncated
            postings = [row for row in rows if looks_like_posting(str(row[1]))]
            hosts_used.append({"pattern": pattern, "urls": len(rows),
                               "postings": len(postings), "truncated": truncated})
            for row in postings:
                url, ts = str(row[1]), str(row[0])
                if url not in earliest or ts < earliest[url]:
                    earliest[url] = ts
            time.sleep(DELAY)
        if not earliest:
            panel[company] = {"hosts": hosts_used, "status": "no coverage",
                              "distinct_postings": 0, "months": 0}
            print(f"{company:20s} no coverage")
            continue
        monthly = Counter(ts[:6] for ts in earliest.values())
        shapes = Counter(url_shape(url) for url in earliest)
        shape_first: dict[str, str] = {}
        for url, ts in earliest.items():
            shape = url_shape(url)
            if shape not in shape_first or ts < shape_first[shape]:
                shape_first[shape] = ts
        panel[company] = {
            "hosts": hosts_used,
            "truncated": truncated_any,
            "distinct_postings": len(earliest),
            "months": len(monthly),
            "monthly": dict(sorted(monthly.items())),
            "depth_rank": keys_rank(monthly),
            "shapes": dict(shapes.most_common(6)),
            "shape_first_seen": dict(sorted(shape_first.items(),
                                            key=lambda item: item[1])[:12]),
            "status": "collected",
        }
        print(f"{company:20s} postings={len(earliest):5d} months={len(monthly):3d} "
              f"truncated={truncated_any} hosts={len([h for h in hosts_used if h['postings']])}")
    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-030 (supersedes the cycle-9 panel builder)",
            "source": "Wayback Machine CDX (index only, keyless)",
            "proxy": "distinct posting URLs by earliest archive capture month",
            "window": [FROM, TO],
            "limit": LIMIT,
            "truncation_policy": ("a single request per host with a generous limit; when the cap is "
                                  "hit it is recorded per host so truncation is visible, not hidden"),
            "shape_audit": "posting-URL path templates and their first-seen month, for platform "
                           "migration detection",
            "hosts": HOSTS,
        },
        "companies": panel,
        "coverage": {
            "companies_probed": len(HOSTS),
            "companies_with_postings": sum(1 for value in panel.values()
                                           if value.get("distinct_postings")),
            "companies_with_24plus_months": sum(1 for value in panel.values()
                                                 if value.get("months", 0) >= 24),
            "companies_with_50plus_postings": sum(1 for value in panel.values()
                                                   if value.get("distinct_postings", 0) >= 50),
        },
    }
    write_json(Path("experiments/b030/hiring_panel_v2.json"), payload)
    print("\ncoverage:", payload["coverage"])
    print("wrote experiments/b030/hiring_panel_v2.json")
    return 0


def keys_rank(monthly: Counter) -> int:
    for rank, (_, count) in enumerate(monthly.most_common(), start=1):
        if count < 5:
            return rank - 1
    return len(monthly)


if __name__ == "__main__":
    raise SystemExit(main())

