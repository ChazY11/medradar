"""B-030: build a point-in-time hiring panel from the Wayback Machine CDX archive.

Why this is lawful and reproducible: the Wayback Machine is a public web archive; its CDX
endpoint lists captures (URL + timestamp) without a key. We never fetch page content — only the
index — and we issue bounded, rate-limited queries. Each row is one distinct posting URL with its
earliest capture timestamp, so aggregating by month yields "new job postings first archived that
month", a hiring-intensity proxy that exists historically (the archive predates our analysis window
by years, so there is no look-ahead from our own collection).

Discovery + collection in one bounded pass:
  1. for each company, try a small list of career-domain / job-path patterns;
  2. keep patterns that return real posting URLs (URL contains a job id or '/job');
  3. paginate the index for the survivors inside 2014-01..2026-12 and aggregate to monthly counts.

Output: experiments/b030/hiring_panel.json (coverage + monthly series per company).

Usage:
    python experiments/b030/hiring_panel.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.panel import write_json  # noqa: E402

CDX = "http://web.archive.org/cdx/search/cdx"
FROM, TO = "2014", "2026"
USER_AGENT = "MedRadar-research/1.0"
DELAY = 1.0
MAX_PAGES = 16
PAGE_LIMIT = 4000

#: (company_key, main domain) for the device watchlist; candidate career hosts are derived.
COMPANIES = [
    ("medtronic", "medtronic.com"),
    ("ge_healthcare", "gehealthcare.com"),
    ("philips", "philips.com"),
    ("draeger", "draeger.com"),
    ("mindray", "mindray.com"),
    ("boston_scientific", "bostonscientific.com"),
    ("stryker", "stryker.com"),
    ("abbott", "abbott.com"),
    ("bd", "bd.com"),
    ("baxter", "baxter.com"),
    ("zimmer_biomet", "zimmerbiomet.com"),
    ("edwards_lifesciences", "edwards.com"),
    ("intuitive_surgical", "intuitive.com"),
    ("dexcom", "dexcom.com"),
    ("masimo", "masimo.com"),
    ("hologic", "hologic.com"),
]

PATTERN_TEMPLATES = (
    "jobs.{domain}/job/*",
    "careers.{domain}/job/*",
    "www.{domain}/careers/job/*",
    "www.{domain}/careers/*job*",
    "jobs.{domain}/jobs/*",
    "www.{domain}/job/*",
    "careers.{domain}/jobs/*",
    "jobs.{domain}/*",
    "www.{domain}/careers/*",
    "{domain}/careers/*",
)


def cdx(params: dict, timeout: int = 90) -> str:
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def looks_like_posting(url: str) -> bool:
    lowered = url.lower()
    if "job-detail" in lowered or lowered.endswith(".css") or lowered.endswith(".js"):
        return False
    return "/job" in lowered or "/jobs/" in lowered


def discover(company: str, domain: str) -> list[dict]:
    """Try candidate patterns; return those with real posting URLs."""
    hits = []
    for template in PATTERN_TEMPLATES:
        pattern = template.format(domain=domain)
        try:
            body = cdx({"url": pattern, "output": "json", "from": FROM, "to": TO,
                        "collapse": "urlkey", "limit": "40",
                        "fl": "timestamp,original"})
        except Exception:  # noqa: BLE001 - a dead pattern is not an error
            time.sleep(DELAY)
            continue
        rows = json.loads(body) if body.strip().startswith("[") else []
        data = rows[1:] if rows else []
        postings = [row for row in data if looks_like_posting(str(row[1]))]
        if postings:
            hits.append({"pattern": pattern, "sample_postings": len(postings)})
        time.sleep(DELAY)
    return hits


def collect(pattern: str) -> list[dict]:
    """Paginate one pattern; return [timestamp, url] rows for distinct URLs."""
    rows: list[dict] = []
    for page in range(MAX_PAGES):
        try:
            body = cdx({"url": pattern, "output": "json", "from": FROM, "to": TO,
                        "collapse": "urlkey", "fl": "timestamp,original",
                        "limit": str(PAGE_LIMIT), "page": str(page)})
        except Exception:  # noqa: BLE001
            break
        if not body.strip():
            break
        parsed = json.loads(body) if body.strip().startswith("[") else []
        data = parsed[1:] if parsed else []
        if not data:
            break
        rows.extend({"timestamp": str(row[0]), "url": str(row[1])}
                    for row in data if looks_like_posting(str(row[1])))
        if len(data) < PAGE_LIMIT:
            break
        time.sleep(DELAY)
    # de-duplicate by URL, keeping the earliest capture
    earliest: dict[str, str] = {}
    for row in rows:
        url = row["url"]
        if url not in earliest or row["timestamp"] < earliest[url]:
            earliest[url] = row["timestamp"]
    return [{"url": url, "timestamp": ts} for url, ts in sorted(earliest.items())]


def main() -> int:
    panel: dict[str, dict] = {}
    for company, domain in COMPANIES:
        hits = discover(company, domain)
        if not hits:
            print(f"{company:24s} no posting URLs found in candidate patterns")
            panel[company] = {"domain": domain, "patterns": [], "status": "no coverage"}
            continue
        best = max(hits, key=lambda hit: hit["sample_postings"])
        postings = collect(best["pattern"])
        monthly = Counter(entry["timestamp"][:6] for entry in postings)
        months_covered = len(monthly)
        panel[company] = {
            "domain": domain,
            "patterns": hits,
            "pattern_used": best["pattern"],
            "distinct_postings": len(postings),
            "months_covered": months_covered,
            "banked_postings": sum(1 for count in monthly.values() if count > 0),
            "monthly": dict(sorted(monthly.items())),
            "status": "collected" if len(postings) >= 20 else "thin",
        }
        print(f"{company:24s} {best['pattern']:38s} postings={len(postings):5d} "
              f"months={months_covered:3d} status={panel[company]['status']}")
        time.sleep(DELAY)
    usable = {key: value for key, value in panel.items() if value.get("status") == "collected"}
    payload = {
        "design": {
            "source": "Wayback Machine CDX API (public web archive; index only, no page content)",
            "proxy": "distinct job-posting URLs whose earliest archive capture falls in a month",
            "window": [FROM, TO],
            "from_to": [FROM, TO],
            "delay_seconds": DELAY,
            "max_pages_per_pattern": MAX_PAGES,
            "page_limit": PAGE_LIMIT,
            "note": ("lawful and keyless; queries are bounded and rate-limited. The archive "
                     "predates the analysis, so the signal is genuinely point-in-time. Coverage "
                     "is uneven because it depends on which career sites have been archived."),
        },
        "coverage": {
            "companies_tried": len(COMPANIES),
            "companies_with_postings": sum(1 for value in panel.values() if value.get("distinct_postings")),
            "companies_usable": len(usable),
            "usable_keys": sorted(usable),
        },
        "companies": panel,
    }
    write_json(Path("experiments/b030/hiring_panel.json"), payload)
    print(f"\nusable companies: {payload['coverage']['usable_keys']}")
    print("wrote experiments/b030/hiring_panel.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

