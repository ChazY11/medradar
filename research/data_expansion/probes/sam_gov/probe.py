#!/usr/bin/env python
"""Probe: SAM.gov opportunities API, domain F, priority P1.

What is tested
--------------
The documented public endpoint is
``GET https://api.sam.gov/opportunities/v2/search`` and the documentation
marks ``api_key`` as **required** (query parameter, "Public Key of users").

Three requests:
1. without any key,
2. with a syntactically valid but non-existent key,
3. the official documentation page (so ``evidence_urls`` is a page actually
   opened, not a search result).

Observed behaviour is recorded verbatim: the gateway answers **404 with an empty
body** in both cases, not 401/403.  That distinction matters — a 404 is not a
"needs registration" signal on its own, so the register must state that the
registration requirement comes from the *documentation*, while the live
observation is "unauthenticated request is refused by the gateway".

Run:  python research/data_expansion/probes/sam_gov/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
DOCS_URL = "https://open.gsa.gov/api/get-opportunities-public-api/"
SAMPLE_DIR = ROOT / "samples" / "sam_gov"
BOGUS_KEY = "0" * 40


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
        "server": (r.headers or {}).get("server", ""),
        "body_head": r.text[:200],
        "sample": None,
    }
    if r.ok and sample_name:
        entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    if extra:
        entry.update(extra)
    return entry


def probe(client, directory):
    probes = []

    r = client.get(SEARCH_URL, params={"limit": 1})
    probes.append(
        _describe(r, name="search_no_key", extra={"api_key_sent": False})
    )

    r = client.get(SEARCH_URL, params={"limit": 1, "api_key": BOGUS_KEY})
    probes.append(
        _describe(r, name="search_invalid_key", extra={"api_key_sent": True})
    )

    r = client.get(DOCS_URL, accept="text/html")
    probes.append(_describe(r, name="official_docs_page", sample_name="official_docs.html"))

    docs_ok = any(p["name"] == "official_docs_page" and p["ok"] for p in probes)
    api_ok = any(p["ok"] and "api.sam.gov" in p["url"] for p in probes)
    if api_ok:
        status = "VERIFIED_API"
    elif docs_ok:
        status = "REQUIRES_REGISTRATION"
    else:
        status = "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id="sam_gov",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p["ok"]][:3] + [DOCS_URL],
        notes=(
            "SAM.gov documents api_key as mandatory for /opportunities/v2/search. "
            "Unauthenticated requests (with and without a bogus key) were answered by "
            "the istio-envoy gateway with 404 and an empty body - not the 401/403 the "
            "protocol expects, so the registration requirement is a DOCUMENTED fact "
            "while the live observation only proves the endpoint refuses anonymous "
            "callers. No key was registered."
        ),
    )


outcome = base.run_probe("sam_gov", ROOT, probe, budget=5, min_interval=0.9)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['bytes']:>7}B server={p['server'][:16]:<16} {p['name']}  {p['body_head'][:60]}")
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
