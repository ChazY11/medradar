#!/usr/bin/env python
"""Probe: OCDS (Open Contracting Data Standard) source layer, domain F, P2.

What is tested — and what is deliberately *not* claimed
-------------------------------------------------------
OCDS is a **data standard**, not a publisher.  ``standard.open-contracting.org``
documents the schema and a registry of publishers; it does not itself serve
contract records.  The probe therefore verifies the documentation/schema layer
and records that no homogeneous record API exists here, instead of dressing a
docs site up as a "verified API".

Evidence value of the run: it pins down *why* the OCDS layer is useful
(publisher-agnostic record model, so a connector written against it generalises)
and *why* it cannot be used as a source by itself (per-publisher endpoints).

Run:  python research/data_expansion/probes/ocds_registry/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

SAMPLE_DIR = ROOT / "samples" / "ocds_registry"

DOC_URLS = [
    ("standard_overview", "https://standard.open-contracting.org/latest/en/"),
    ("release_package_schema", "https://standard.open-contracting.org/latest/en/schema/release_package/"),
    ("record_model", "https://standard.open-contracting.org/latest/en/101/"),
]


def _describe(r, *, name):
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
        "sample": None,
    }
    if r.ok:
        text = r.text
        low = text.lower()
        start = low.find("<title")
        if start >= 0:
            end = low.find("</title>", start)
            entry["html_title"] = text[start:end][:150]
        entry["sample"] = base.write_sample(SAMPLE_DIR, f"{name}.html", r.body)
    return entry


def probe(client, directory):
    probes = []
    for name, url in DOC_URLS:
        r = client.get(url, accept="text/html")
        probes.append(_describe(r, name=name))

    ok = [p for p in probes if p["ok"]]
    return base.ProbeOutcome(
        source_id="ocds_registry",
        status="NOT_TESTED" if ok else "UNAVAILABLE",
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in ok][:3],
        notes=(
            "OCDS is a data standard plus a publisher registry, not a record "
            "publisher: the official site documents the release/record model and "
            "lists publishers, and has no homogeneous record API of its own. "
            "Status is NOT_TESTED on purpose - calling a documentation site "
            "'verified' would be a category error. Actual OCDS records were "
            "verified through a real publisher instead (uk_find_a_tender, OCDS 1.1)."
        ),
    )


outcome = base.run_probe("ocds_registry", ROOT, probe, budget=5, min_interval=0.8)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['bytes']:>7}B {p['name']:<26} {p['html_title'][:50]} {p['error'][:30]}")
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
