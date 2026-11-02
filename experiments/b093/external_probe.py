"""Probe whether the previously blocked external sources are reachable now (no credentials, read-only HEADs).

The study recorded patents as unavailable (403 from PatentsView) and procurement dates as unusable. Rather than repeat
those claims from memory, this probes them again and stores status codes with timestamps, so a later reader can see
what was actually blocked and when.

    python experiments/b093/external_probe.py
"""
from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TARGETS = {
    "patentsview_api": "https://api.patentsview.org/patents/query?q=%7B%22patent_number%22%3A%22%2210000000%22%7D",
    "uspto_patents_home": "https://patents.google.com/",
    "sec_edgar_companyfacts": "https://data.sec.gov/api/xbrl/companyfacts/CIK0001613103.json",
    "clinicaltrials_api": "https://clinicaltrials.gov/api/v2/studies?pageSize=1",
    "openfda_device_510k": "https://api.fda.gov/device/510k.json?limit=1",
    "europe_pmc": "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=pacemaker&format=json&pageSize=1",
}


def probe(url: str, timeout: int = 20) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "medradar-study/1.0 (research)"})
    try:
        with urllib.request.urlopen(request, timeout=timeout,
                                    context=ssl.create_default_context()) as response:
            content_type = response.headers.get("Content-Type") or ""
            # HTTP 200 is not usability: a retired API returns its landing page as text/html
            usable = "json" in content_type.lower()
            return {"status": response.status, "reachable": 200 <= response.status < 300,
                    "content_type": content_type, "usable_json": usable}
    except urllib.error.HTTPError as error:
        return {"status": error.code, "reachable": False, "error": f"HTTP {error.code}"}
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as error:
        return {"status": None, "reachable": False, "error": str(error)[:160]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="research/studies/early_signal_5firms/EXTERNAL_SOURCE_PROBE.json")
    args = parser.parse_args(argv)

    results = {}
    for name, url in TARGETS.items():
        result = probe(url)
        results[name] = {"url": url, **result}
        print(f"{name:26s} status={result['status']} reachable={result['reachable']} "
              f"usable_json={result.get('usable_json')} ctype={str(result.get('content_type'))[:24]} "
              f"{result.get('error', '')}")
    payload = {
        "schema": "external_source_probe_v1",
        "probed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "HEAD/GET probes without credentials; a 200 means the endpoint answers, not that bulk access is granted",
        "results": results,
        "verdict": {
            "patents": results["patentsview_api"]["usable_json"],
            "sec": results["sec_edgar_companyfacts"]["usable_json"],
            "ctgov": results["clinicaltrials_api"]["usable_json"],
            "openfda": results["openfda_device_510k"]["usable_json"],
            "europe_pmc": results["europe_pmc"]["usable_json"],
        },
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
