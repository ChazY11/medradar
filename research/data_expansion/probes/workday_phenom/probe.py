#!/usr/bin/env python
"""Probe: Workday / Phenom careers adapters, domain G, priority P2.

What is tested
--------------
There is no vendor-neutral public API here.  Each employer runs its own tenant
(Workday: ``<tenant>.wdN.myworkdayjobs.com/wday/cxs/...``) or a hosted careers
product (Phenom: ``jobs.<company>.com``).  The question is narrow and honest:
*can a compliant, unauthenticated request to one such endpoint return real job
records, or is per-employer reverse engineering required?*

Findings this probe is designed to separate
-------------------------------------------
* **TLS**: ``jobs.medtronic.com`` resolves but presents a certificate whose name
  does not match the host.  A client is *not* allowed to disable verification
  to work around that, so the honest answer is "not fetchable as a compliant
  client", and the probe records it as a transport failure rather than a 404.
* **Workday CXS**: public careers sites call
  ``POST /wday/cxs/<tenant>/<site>/jobs``.  One tenant is tested; whatever it
  answers is recorded verbatim.  A per-employer result is not a general API.

``max_retries=0`` is deliberate: three attempts against a broken TLS endpoint
would burn the whole budget on one host.

Run:  python research/data_expansion/probes/workday_phenom/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

SAMPLE_DIR = ROOT / "samples" / "workday_phenom"

PHENOM_HOST = "https://jobs.medtronic.com/"
WORKDAY_CXS_PHILIPS = "https://philips.wd3.myworkdayjobs.com/wday/cxs/philips/Philips_Careers/jobs"
WORKDAY_CXS_GEHC = "https://gehc.wd5.myworkdayjobs.com/wday/cxs/gehc/GEHC/jobs"
WORKDAY_PRODUCT_PAGE = "https://www.workday.com/en-us/products/talent-acquisition.html"


def _title(html: str) -> str:
    low = html.lower()
    start = low.find("<title")
    if start < 0:
        return ""
    end = low.find("</title>", start)
    return html[start:end][:160].replace("\n", " ")


def _mentions_jobs(html: str) -> bool:
    low = html.lower()
    return sum(low.count(t) for t in ("job", "career", "vacanc", "position")) >= 5


def _describe(r, *, name, sample_name=None, extra=None):
    entry = {
        "name": name,
        "url": r.url,
        "method": r.method,
        "status": r.status,
        "ok": r.ok,
        "bytes": len(r.body),
        "elapsed_ms": r.elapsed_ms,
        "attempts": r.attempts,
        "error": r.error,
        "content_type": (r.headers or {}).get("content-type", ""),
        "structure": None,
        "sample": None,
    }
    if r.ok:
        ctype = entry["content_type"] or ""
        if "json" in ctype:
            try:
                payload = r.json()
                entry["structure"] = base.json_shape(payload)
                if isinstance(payload, dict):
                    entry["top_keys"] = sorted(payload.keys())[:20]
                if sample_name:
                    entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
            except json.JSONDecodeError:
                entry["error"] = "declared JSON but did not parse"
        else:
            text = r.text
            entry["html_title"] = _title(text)
            entry["looks_like_job_list"] = _mentions_jobs(text)
            if sample_name:
                entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    else:
        entry["body_head"] = r.text[:160]
    if extra:
        entry.update(extra)
    return entry


def probe(client, directory):
    probes = []

    r = client.get(PHENOM_HOST, accept="text/html")
    probes.append(_describe(r, name="phenom_host_medtronic"))
    if r.ok:
        probes[-1]["sample"] = base.write_sample(
            SAMPLE_DIR, "phenom_medtronic.html", r.body
        )

    r = client.post_json(
        WORKDAY_CXS_PHILIPS,
        {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": ""},
        headers={"Accept": "application/json"},
    )
    probes.append(_describe(r, name="workday_cxs_philips", sample_name="workday_philips.json"))

    r = client.post_json(
        WORKDAY_CXS_GEHC,
        {"appliedFacets": {}, "limit": 5, "offset": 0, "searchText": ""},
        headers={"Accept": "application/json"},
    )
    probes.append(_describe(r, name="workday_cxs_gehc", sample_name="workday_gehc.json"))

    r = client.get(WORKDAY_PRODUCT_PAGE, accept="text/html")
    probes.append(_describe(r, name="workday_product_page"))

    ok_any = [p for p in probes if p["ok"]]
    ok_json = [p for p in probes if p["ok"] and "json" in (p["content_type"] or "")]
    status = "VERIFIED_PUBLIC_QUERY" if ok_any else "UNAVAILABLE"
    tls_fail = [p["name"] for p in probes if "CERTIFICATE_VERIFY_FAILED" in (p["error"] or "")]
    return base.ProbeOutcome(
        source_id="workday_phenom",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in ok_any][:4],
        notes=(
            "No vendor-neutral public API exists; each employer exposes its own tenant. "
            f"Per-employer JSON endpoints answering: {[p['name'] for p in ok_json] or 'none'}. "
            f"TLS hostname-mismatch failures: {tls_fail or 'none'} — TLS verification was not "
            "disabled to work around them. A working tenant endpoint is site-specific, not a "
            "generalisable job-postings API."
        ),
    )


outcome = base.run_probe(
    "workday_phenom", ROOT, probe, budget=6, min_interval=0.9, max_retries=0
)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['method']:5} {p['bytes']:>7}B ct={p['content_type'][:20]:<20} {p['name']}  {p['error'][:44]} {p.get('html_title','')[:34]}")
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
