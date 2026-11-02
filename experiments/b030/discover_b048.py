"""B-048: discover career/job boards for the five uncovered device firms.

Rather than guessing host names again, this asks the archive what it has: for each company's main
domain it queries the CDX index with a regex filter for career/job URLs, and reports the distinct
hosts and path prefixes that actually appear. Those observed patterns are then measured for depth.
"""
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

TARGETS = {
    "philips": "philips.com",
    "draeger": "draeger.com",
    "mindray": "mindray.com",
    "zimmer_biomet": "zimmerbiomet.com",
    "masimo": "masimo.com",
}


def cdx(params: dict, timeout: int = 120) -> list[list[str]]:
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
    rows = json.loads(body) if body.strip().startswith("[") else []
    return rows[1:] if rows else []


def discover(company: str, domain: str) -> dict:
    """Ask the archive which career/job URLs exist under the main domain."""
    rows = cdx({"url": f"{domain}/*", "output": "json", "fl": "timestamp,original",
                "collapse": "urlkey", "filter": "original:.*(career|jobs?|stellen|vacature).*",
                "limit": "300", "from": "2015", "to": "2026"})
    by_host: Counter = Counter()
    by_prefix: Counter = Counter()
    samples: dict[str, list[str]] = {}
    for row in rows:
        url = str(row[1])
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        segments = [part for part in parsed.path.split("/") if part][:2]
        prefix = "/".join(segments)
        by_host[host] += 1
        by_prefix[f"{host}/{prefix}"] += 1
        samples.setdefault(host, []).append(url)
    return {"company": company, "domain": domain, "urls": len(rows),
            "hosts": dict(by_host.most_common(8)),
            "prefixes": dict(by_prefix.most_common(10)),
            "samples": {host: urls[:3] for host, urls in list(samples.items())[:5]}}


def main() -> int:
    results = []
    for company, domain in TARGETS.items():
        try:
            result = discover(company, domain)
        except Exception as exc:  # noqa: BLE001
            print(f"{company:16s} ERROR {type(exc).__name__}: {exc}")
            results.append({"company": company, "domain": domain,
                            "error": f"{type(exc).__name__}: {exc}"})
            time.sleep(DELAY)
            continue
        results.append(result)
        print(f"\n{company} ({domain}): {result['urls']} career/job URLs")
        for prefix, count in result["prefixes"].items():
            print(f"   {count:4d}  {prefix[:100]}")
        time.sleep(DELAY)
    Path("experiments/b030/discovery_b048.json").write_text(
        json.dumps({"targets": TARGETS, "results": results}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("\nwrote experiments/b030/discovery_b048.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
