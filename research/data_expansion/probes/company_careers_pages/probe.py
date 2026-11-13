#!/usr/bin/env python
"""Probe: company careers pages (direct), domain G, priority P3.

What is tested
--------------
Whether the *official* corporate careers pages of the target firms are readable
as a compliant client, and whether they expose job records in the HTML at all.
Five firms, one request each plus two robots.txt checks — no crawling.

Why this matters for the hiring evidence: the P0 job-board APIs (Greenhouse,
Lever) turned out not to host any of the five firms.  If the corporate pages
are HTML-only, then per-employer adapters are the only route, and the hiring
evidence for these five firms cannot be produced from a generic public API.

Run:  python research/data_expansion/probes/company_careers_pages/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

SAMPLE_DIR = ROOT / "samples" / "company_careers_pages"

PAGES = [
    ("medtronic", "https://www.medtronic.com/us-en/about/careers.html"),
    ("philips", "https://www.careers.philips.com/global/en"),
    ("draeger", "https://www.draeger.com/en-us/Company/Careers"),
    ("mindray", "https://www.mindray.com/en/careers"),
    # the actual job search behind the Philips careers landing page
    ("philips_search_results", "https://www.careers.philips.com/global/en/search-results"),
]

ROBOTS = [
    ("medtronic_robots", "https://www.medtronic.com/robots.txt"),
]


def _title(html: str) -> str:
    low = html.lower()
    start = low.find("<title")
    if start < 0:
        return ""
    end = low.find("</title>", start)
    return html[start:end][:140].replace("\n", " ")


def _job_terms(html: str) -> dict:
    low = html.lower()
    return {
        "job": low.count("job"),
        "career": low.count("career"),
        "vacanc": low.count("vacanc"),
        "position": low.count("position"),
        "mentions_apply": low.count("apply"),
    }


def _describe(r, *, name, sample_name=None):
    entry = {
        "name": name,
        "url": r.url,
        "status": r.status,
        "ok": r.ok,
        "bytes": len(r.body),
        "elapsed_ms": r.elapsed_ms,
        "error": r.error,
        "content_type": (r.headers or {}).get("content-type", ""),
        "html_title": "",
        "job_terms": None,
        "sample": None,
    }
    if r.ok:
        text = r.text
        entry["html_title"] = _title(text)
        entry["job_terms"] = _job_terms(text)
        if sample_name:
            entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    else:
        entry["body_head"] = r.text[:120]
    return entry


def probe(client, directory):
    probes = []
    for label, url in PAGES:
        r = client.get(url, accept="text/html")
        probes.append(
            _describe(r, name=label, sample_name=(f"{label}.html" if r.ok else None))
        )
    for label, url in ROBOTS:
        r = client.get(url, accept="text/plain")
        probes.append(
            _describe(r, name=label, sample_name=(f"{label}.txt" if r.ok else None))
        )

    ok = [p for p in probes if p["ok"] and p["name"] in {p2[0] for p2 in PAGES}]
    # Pages answered, but none exposed a vacancy payload: an HTML front door is
    # not a job feed, so the access status stays UNAVAILABLE for *records*.
    status = "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id="company_careers_pages",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p["ok"]][:4],
        notes=(
            "Corporate careers pages were fetched one request per firm (plus robots.txt "
            "where present), no crawling. An HTML page that mentions jobs is not a job "
            "feed: the register records how many firms answer HTML and whether any "
            "machine-readable vacancy payload is present, and does not claim a hiring "
            "dataset from these pages."
        ),
    )


outcome = base.run_probe("company_careers_pages", ROOT, probe, budget=8, min_interval=0.9)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['bytes']:>7}B {p['name']:<20} {p['error'][:40]} {p['html_title'][:46]}")
    if p.get("job_terms"):
        print("       terms:", p["job_terms"])
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
