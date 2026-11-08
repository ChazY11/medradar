#!/usr/bin/env python
"""Probe: Lever postings API, domain G, priority P0.

What is tested
--------------
``GET https://api.lever.co/v0/postings/<company>?mode=json`` for one control
token plus the five target firms.

Same design as the Greenhouse probe: a control token proves the endpoint is
reachable and the 404s mean "no such board", not "network broken".  Request
count is capped deliberately — enumerating tokens is not an access strategy.

Run:  python research/data_expansion/probes/lever/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

POSTINGS_URL = "https://api.lever.co/v0/postings/{company}"
SAMPLE_DIR = ROOT / "samples" / "lever"

TOKENS = [
    ("control_leverdemo", "leverdemo"),
    ("medtronic", "medtronic"),
    ("ge_healthcare", "gehealthcare"),
    ("philips", "philips"),
    ("draeger", "draeger"),
    ("mindray", "mindray"),
]


def _describe(r, *, name, token, sample_name=None):
    entry = {
        "name": name,
        "token": token,
        "url": r.url,
        "method": r.method,
        "status": r.status,
        "ok": r.ok,
        "bytes": len(r.body),
        "elapsed_ms": r.elapsed_ms,
        "attempts": r.attempts,
        "error": r.error,
        "structure": None,
        "n_postings": None,
        "sample": None,
    }
    if r.ok:
        payload = None
        try:
            payload = r.json()
        except json.JSONDecodeError:
            entry["error"] = "response was not JSON"
        if isinstance(payload, list):
            entry["n_postings"] = len(payload)
            entry["structure"] = base.json_shape(payload)
            if payload:
                entry["first_posting_keys"] = sorted(payload[0].keys())
                entry["first_posting_fields"] = {
                    k: payload[0].get(k)
                    for k in ("id", "text", "createdAt", "categories", "hostedUrl")
                    if k in payload[0]
                }
        elif isinstance(payload, dict):
            entry["structure"] = base.json_shape(payload)
        if sample_name:
            entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    else:
        entry["body_head"] = r.text[:160]
    return entry


def probe(client, directory):
    probes = []
    for label, token in TOKENS:
        r = client.get(POSTINGS_URL.format(company=token), params={"mode": "json"})
        probes.append(
            _describe(r, name=label, token=token,
                      sample_name=(f"postings_{token}.json" if r.ok else None))
        )

    ok = [p for p in probes if p["ok"]]
    firm_hits = [p["token"] for p in probes if p["ok"] and not p["name"].startswith("control")]
    status = "VERIFIED_API" if ok else "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id="lever",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in ok][:6],
        notes=(
            "Lever postings API answers anonymously for a control token, so the endpoint "
            f"works; target-firm tokens that resolved: {firm_hits or 'none'}. Lever returns "
            "createdAt (source publication time) per posting, which is what the hiring "
            "evidence needs, but only for companies that actually use Lever."
        ),
    )


outcome = base.run_probe("lever", ROOT, probe, budget=8, min_interval=0.8)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['bytes']:>7}B n={p.get('n_postings')} {p['name']:<20} {p['error'][:50]}")
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
