#!/usr/bin/env python
"""Probe: China Government Procurement Network (ccgp.gov.cn), domain F, P3.

What is tested
--------------
Two requests only: the portal home page and the keyword search endpoint that the
public site itself uses.  The point is to establish whether a compliant,
unauthenticated machine-readable path exists at all — not to scrape.

If the site answers an HTML page but refuses the search path, or if the search
page is a JS/captcha front, then the honest status is ``UNAVAILABLE`` /
``BLOCKED_BY_POLICY`` and the register must say that China procurement is a
documented-but-unverified source.  No attempt is made to defeat a challenge.

Run:  python research/data_expansion/probes/china_ccgp/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

HOME = "http://www.ccgp.gov.cn/"
SEARCH = "http://search.ccgp.gov.cn/bxsearch"
SAMPLE_DIR = ROOT / "samples" / "china_ccgp"


def _describe(r, *, name, sample_name=None):
    entry = {
        "name": name,
        "url": r.url,
        "status": r.status,
        "ok": r.ok,
        "bytes": len(r.body),
        "elapsed_ms": r.elapsed_ms,
        "attempts": r.attempts,
        "error": r.error,
        "content_type": (r.headers or {}).get("content-type", ""),
        "body_head": r.text[:180],
        "sample": None,
    }
    if r.ok and sample_name:
        entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    return entry


def probe(client, directory):
    probes = []

    r = client.get(HOME, accept="text/html")
    probes.append(_describe(r, name="portal_home", sample_name="portal_home.html"))

    r = client.get(
        SEARCH,
        params={
            "searchtype": 1,
            "page_index": 1,
            "bidSort": 0,
            "pinMu": 0,
            "bidType": 0,
            "kw": "内窥镜",
        },
        accept="text/html",
    )
    probes.append(_describe(r, name="keyword_search_neijingjing", sample_name="search.html"))

    ok = [p for p in probes if p["ok"]]
    status = "VERIFIED_PUBLIC_QUERY" if ok else "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id="china_ccgp",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in ok][:2],
        notes=(
            "Only the two endpoints the public site itself exposes were requested. "
            "Whatever the outcome, no anti-bot or login mechanism was bypassed; if the "
            "search path is not machine-readable the register records China procurement "
            "as unverified rather than as 'available with caveats'."
        ),
    )


outcome = base.run_probe("china_ccgp", ROOT, probe, budget=4, min_interval=0.9)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['bytes']:>7}B ct={p['content_type'][:24]:<24} {p['name']}  {p['error'][:50]}")
    print("      ", p["body_head"][:110].replace("\n", " "))
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
