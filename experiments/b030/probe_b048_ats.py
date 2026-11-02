"""B-048 probe 2: broader ATS-host battery for the five uncovered firms.

Career-site discovery returned only marketing pages, so the boards may live on ATS domains that were
never linked from an archived page. This probes a wider set of ATS host patterns per company and
reports any host with archived URLs. An absence is recorded as a measured absence with the exact
patterns tried, not as a guess.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CDX = "http://web.archive.org/cdx/search/cdx"
UA = "MedRadar-research/1.0"
DELAY = 0.7

KEYS = {
    "philips": ["philips"],
    "draeger": ["draeger", "draegermedical"],
    "mindray": ["mindray", "mindrayglobal"],
    "zimmer_biomet": ["zimmerbiomet", "zimmer"],
    "masimo": ["masimo"],
}

PODS = ["wd1", "wd3", "wd5", "wd12", "wd103"]
TEMPLATES = (
    ["https://{key}.{pod}.myworkdayjobs.com/*" for pod in PODS]
    + ["https://careers.{key}.com/*", "https://jobs.{key}.com/*",
       "https://{key}.taleo.net/*", "https://careers-{key}.icims.com/*",
       "https://jobs-{key}.icims.com/*", "https://{key}.successfactors.com/*",
       "https://career4.successfactors.com/*",
       "https://{key}.avature.net/*", "https://{key}.jobvite.com/*",
       "https://careers.smartrecruiters.com/{key}*",
       "https://boards.greenhouse.io/{key}*", "https://jobs.lever.co/{key}*",
       "https://{key}.eightfold.ai/*", "https://www.{key}.com/careers/job/*",
       "https://www.{key}.com/en/careers/*"]
)


def probe(pattern: str, limit: int = 3) -> int:
    params = {"url": pattern, "output": "json", "limit": str(limit),
              "fl": "timestamp,original", "collapse": "urlkey"}
    url = f"{CDX}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8", "replace")
    rows = json.loads(body) if body.strip().startswith("[") else []
    data = rows[1:] if rows else []
    return len(data)


def main() -> int:
    report: dict[str, list[dict]] = {}
    for company, keys in KEYS.items():
        hits = []
        tried = 0
        for key in keys:
            for template in TEMPLATES:
                pattern = template.format(key=key, pod="{pod}") if "{pod}" in template else \
                    template.format(key=key)
                if "{pod}" in pattern:
                    continue
                tried += 1
                try:
                    count = probe(pattern)
                except Exception:  # noqa: BLE001
                    time.sleep(DELAY)
                    continue
                if count:
                    hits.append({"pattern": pattern, "urls": count})
                time.sleep(DELAY)
            # Workday pods need their own loop because of the {pod} placeholder
            for pod in PODS:
                pattern = f"https://{key}.{pod}.myworkdayjobs.com/*"
                tried += 1
                try:
                    count = probe(pattern)
                except Exception:  # noqa: BLE001
                    time.sleep(DELAY)
                    continue
                if count:
                    hits.append({"pattern": pattern, "urls": count})
                time.sleep(DELAY)
        report[company] = hits
        print(f"{company:16s} tried={tried:3d} hits={len(hits)}")
        for hit in hits[:6]:
            print(f"    {hit['urls']:3d}  {hit['pattern'][:86]}")
    Path("experiments/b030/ats_battery_b048.json").write_text(
        json.dumps({"keys": KEYS, "patterns_per_company": len(TEMPLATES) + len(PODS),
                    "hits": report}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nwrote experiments/b030/ats_battery_b048.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
