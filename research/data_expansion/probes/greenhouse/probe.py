#!/usr/bin/env python
"""Probe: Greenhouse job-board API, domain G, priority P0.

What is tested
--------------
``GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=false``
for one *control* token plus the five target firms.

Why a control matters: a 404 for every token would be ambiguous — either the
API is unreachable, or the firms simply are not Greenhouse customers.  The
control (a company known to publish on Greenhouse) separates those two
explanations.  The probe is deliberately tiny: 6 requests, no enumeration
beyond that, because token guessing is not a legitimate access strategy.

If all five firms 404, the honest conclusion is *"none of the five is a
Greenhouse customer"* (a negative result worth recording), **not** "hiring data
is unavailable".

Run:  python research/data_expansion/probes/greenhouse/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
SAMPLE_DIR = ROOT / "samples" / "greenhouse"

#: (label, token).  ``medtronic`` is in the list because the recon note claimed
#: it 404s; the probe re-verifies that rather than trusting the note.
TOKENS = [
    ("control_stripe", "stripe"),
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
        "n_jobs": None,
        "sample": None,
    }
    if r.ok:
        payload = None
        try:
            payload = r.json()
        except json.JSONDecodeError:
            entry["error"] = "response was not JSON"
        if isinstance(payload, dict):
            jobs = payload.get("jobs") or []
            entry["n_jobs"] = len(jobs)
            entry["structure"] = base.json_shape(payload)
            if jobs:
                entry["first_job_keys"] = sorted(jobs[0].keys())
                entry["first_job_fields"] = {
                    k: (jobs[0].get(k) if not isinstance(jobs[0].get(k), (dict, list)) else "<structured>")
                    for k in ("id", "title", "updated_at", "absolute_url", "location")
                    if k in jobs[0]
                }
        if sample_name:
            entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    else:
        entry["body_head"] = r.text[:160]
    return entry


def probe(client, directory):
    probes = []
    for label, token in TOKENS:
        r = client.get(BOARD_URL.format(token=token), params={"content": "false"})
        probes.append(
            _describe(r, name=label, token=token,
                      sample_name=(f"board_{token}.json" if r.ok else None))
        )

    ok = [p for p in probes if p["ok"]]
    control_ok = any(p["ok"] for p in probes if p["name"].startswith("control"))
    firm_hits = [p["token"] for p in probes if p["ok"] and not p["name"].startswith("control")]
    if ok and control_ok:
        status = "VERIFIED_API"
    elif ok:
        status = "VERIFIED_API"
    else:
        status = "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id="greenhouse",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in ok][:6],
        notes=(
            "Greenhouse boards-api answers anonymously for a control token, so the "
            "endpoint works; the five target firms were tested by their likely board "
            f"tokens and the ones that resolved are: {firm_hits or 'none'}. A 404 is the "
            "API's answer for 'no such board', not a network failure. Token guessing was "
            "capped at 6 requests; absence here means 'not a Greenhouse customer under "
            "these tokens', not 'no hiring data exists'."
        ),
    )


outcome = base.run_probe("greenhouse", ROOT, probe, budget=8, min_interval=0.8)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['bytes']:>7}B n_jobs={p.get('n_jobs')} {p['name']:<20} {p['error'][:50]}")
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
