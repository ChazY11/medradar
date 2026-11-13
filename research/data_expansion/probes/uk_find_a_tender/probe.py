#!/usr/bin/env python
"""Probe: UK Find a Tender service (OCDS 1.1), domain F, priority P1.

What is tested
--------------
1. ``GET /api/1.0/ocdsReleasePackages`` — the official OCDS release-package
   feed.  No key, no registration.
2. The ``stages`` filter (``award`` vs ``tender``): UK FTS stages releases, so
   the same procurement appears as a *tender* release first and an *award*
   release later.  Whether the API can filter on that decides whether notice
   and award are separable without parsing prose.
3. A date window via ``updatedFrom`` / ``updatedTo`` — the feed is time-paged,
   which is the only honest way to walk it.
4. The public HTML search page with a company keyword, to see whether a
   firm-targeted query is available at all (the OCDS feed has no keyword
   parameter).

Run:  python research/data_expansion/probes/uk_find_a_tender/probe.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

PACKAGES_URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
SAMPLE_DIR = ROOT / "samples" / "uk_find_a_tender"


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
        "structure": None,
        "sample": None,
    }
    if r.ok:
        try:
            payload = r.json()
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            entry["structure"] = base.json_shape(payload)
            if isinstance(payload, dict):
                entry["n_releases"] = len(payload.get("releases") or [])
                entry["package_version"] = payload.get("version")
                rel = (payload.get("releases") or [{}])[0]
                entry["first_release_keys"] = sorted(rel.keys()) if rel else []
                entry["first_release_tags"] = rel.get("tag") if rel else None
                entry["first_release_date"] = rel.get("date") if rel else None
                entry["has_awards"] = bool(rel.get("awards")) if rel else None
                entry["has_contracts"] = bool(rel.get("contracts")) if rel else None
        if sample_name:
            entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    else:
        entry["body_head"] = r.text[:200]
    if extra:
        entry.update(extra)
    return entry


def probe(client, directory):
    probes = []

    # 1. plain feed ---------------------------------------------------------
    r = client.get(PACKAGES_URL, params={"limit": 2})
    probes.append(_describe(r, name="release_packages_limit2",
                            sample_name="release_packages_limit2.json"))

    # 2. award-stage releases only -----------------------------------------
    r = client.get(PACKAGES_URL, params={"limit": 1, "stages": "award"})
    probes.append(_describe(r, name="release_packages_stage_award",
                            sample_name="release_packages_stage_award.json"))

    # 3. tender-stage releases only ----------------------------------------
    r = client.get(PACKAGES_URL, params={"limit": 1, "stages": "tender"})
    probes.append(_describe(r, name="release_packages_stage_tender",
                            sample_name="release_packages_stage_tender.json"))

    # 4. explicit date window ----------------------------------------------
    today = date.today()
    since = today - timedelta(days=7)
    r = client.get(
        PACKAGES_URL,
        params={
            "limit": 1,
            "updatedFrom": since.isoformat() + "T00:00:00",
            "updatedTo": today.isoformat() + "T00:00:00",
        },
    )
    probes.append(_describe(r, name="release_packages_date_window",
                            sample_name="release_packages_date_window.json",
                            extra={"window": [since.isoformat(), today.isoformat()]}))

    # 5. is there a keyword/company query? ---------------------------------
    r = client.get(PACKAGES_URL, params={"limit": 1, "keywords": "Medtronic"})
    probes.append(_describe(r, name="release_packages_keyword_param_rejected_or_ignored",
                            sample_name="release_packages_keyword_param.json"))

    # 6. public HTML search (the only firm-targeted path) -------------------
    r = client.get(
        "https://www.find-tender.service.gov.uk/Search/Results",
        params={"keywords": "Medtronic"},
        accept="text/html",
    )
    probes.append(_describe(r, name="html_keyword_search_medtronic",
                            extra={"target_url": "https://www.find-tender.service.gov.uk/Search/Results?keywords=Medtronic"}))

    ok = [p for p in probes if p["ok"]]
    status = "VERIFIED_API" if len(ok) >= 4 else ("VERIFIED_PUBLIC_QUERY" if ok else "UNAVAILABLE")
    return base.ProbeOutcome(
        source_id="uk_find_a_tender",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in ok][:6],
        notes=(
            "UK Find a Tender serves anonymous OCDS 1.1 release packages. Releases are "
            "tagged/staged, so a tender release and its award release are separate "
            "objects with separate publication dates — exactly the layering needed. "
            "The feed has no keyword parameter; a company-targeted query only exists as "
            "the HTML search page, so firm-level retrieval cannot use the OCDS API alone."
        ),
    )


outcome = base.run_probe("uk_find_a_tender", ROOT, probe, budget=10, min_interval=0.8)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['method']:4} {p['bytes']:>7}B tags={p.get('first_release_tags')} aw={p.get('has_awards')} {p['name']}  {p['error'][:40]}")
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
