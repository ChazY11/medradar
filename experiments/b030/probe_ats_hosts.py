"""B-047 probe: find each company's REAL job-board host via ATS providers.

The previous round guessed `jobs.<domain>` / `careers.<domain>` and missed eight firms. Large
medtech firms overwhelmingly post on applicant-tracking systems (Workday, Greenhouse, Lever,
SmartRecruiters, iCIMS, Taleo), which are crawlable and often archived. This probe checks a bounded
set of ATS host patterns per company.

CDX answers 200 with an empty body for an unknown host, so a hit means the host exists in the archive.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

CDX = "http://web.archive.org/cdx/search/cdx"
UA = "MedRadar-research/1.0"
DELAY = 0.7

COMPANY_KEYS = {
    "medtronic": "medtronic",
    "ge_healthcare": "gehealthcare",
    "philips": "philips",
    "draeger": "draeger",
    "mindray": "mindray",
    "boston_scientific": "bostonscientific",
    "stryker": "stryker",
    "abbott": "abbott",
    "bd": "bd",
    "baxter": "baxter",
    "zimmer_biomet": "zimmerbiomet",
    "edwards_lifesciences": "edwards",
    "intuitive_surgical": "intuitive",
    "dexcom": "dexcom",
    "masimo": "masimo",
    "hologic": "hologic",
}

TEMPLATES = (
    "https://{key}.wd1.myworkdayjobs.com/*",
    "https://{key}.wd3.myworkdayjobs.com/*",
    "https://{key}.wd5.myworkdayjobs.com/*",
    "https://boards.greenhouse.io/{key}*",
    "https://jobs.lever.co/{key}*",
    "https://careers.smartrecruiters.com/{key}*",
    "https://careers-{key}.icims.com/*",
    "https://{key}.taleo.net/*",
    "https://jobs-{key}.icims.com/*",
)


def probe(pattern: str, limit: int = 5) -> dict:
    params = {"url": pattern, "output": "json", "limit": str(limit),
              "fl": "timestamp,original", "collapse": "urlkey"}
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return {"pattern": pattern, "error": f"{type(exc).__name__}"}
    rows = json.loads(body) if body.strip().startswith("[") else []
    data = rows[1:] if rows else []
    return {"pattern": pattern, "n": len(data),
            "sample": [row[1] for row in data[:2]]}


def main() -> int:
    hits: dict[str, list[dict]] = {}
    for company, key in COMPANY_KEYS.items():
        found = []
        for template in TEMPLATES:
            pattern = template.format(key=key)
            result = probe(pattern)
            time.sleep(DELAY)
            if result.get("n"):
                found.append({"pattern": pattern, "n": result["n"],
                              "sample": result.get("sample")})
        hits[company] = found
        if found:
            print(f"{company:22s} hits={len(found)}")
            for hit in found[:3]:
                print(f"    {hit['n']:3d} {hit['pattern'][:70]}  {str(hit['sample'])[:80]}")
        else:
            print(f"{company:22s} no ATS host found")
    print(json.dumps({"hits": hits}, indent=1)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
