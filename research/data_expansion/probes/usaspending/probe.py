#!/usr/bin/env python
"""Probe: USAspending (US federal award / contract data), domain F, priority P0.

What is tested
--------------
1. ``POST /api/v2/search/spending_by_award/`` with a keyword filter — the
   documented award-search endpoint.  No API key is sent.
2. ``GET /api/v2/awards/<generated_internal_id>/`` — award detail, to check
   which dates are actually published (``Date Signed`` vs
   ``Period of Performance Start``) because that distinction decides
   ``event_at`` vs ``source_public_at``.
3. ``GET /api/v2/references/agency/1/`` — a reference endpoint, sanity check.
4. Per target firm: ``GET /api/v2/autocomplete/recipient/`` (what recipient
   names actually exist), ``POST .../spending_by_award/`` with
   ``recipient_search_text`` (10 rows) and
   ``POST .../spending_by_award_count/`` (population count).

The point of (4) is a *negative* control: ``recipient_search_text`` is a token
search, not an exact recipient match.  The probe must show whether the returned
``Recipient Name`` really is the target firm, which is why the five-firm
assembly step resolves every name through ``identity.CompanyIndex``.

Run:  python research/data_expansion/probes/usaspending/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
COUNT_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award_count/"
AGENCY_URL = "https://api.usaspending.gov/api/v2/references/agency/1/"
AUTOCOMPLETE_URL = "https://api.usaspending.gov/api/v2/autocomplete/recipient/"
AWARD_URL = "https://api.usaspending.gov/api/v2/awards/{award_id}/"

AWARD_TYPES = ["A", "B", "C", "D"]  # BPA calls, purchase orders, delivery orders, definitive contracts

#: Field list deliberately includes CONTRACT DESCRIPTION: whether USAspending
#: publishes a usable device description is exactly what we need to know before
#: claiming any product-level link.
RICH_FIELDS = [
    "Award ID",
    "Recipient Name",
    "Award Amount",
    "Start Date",
    "End Date",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Contract Award Type",
    "Description",
    "generated_internal_id",
]

FIRMS = ["Medtronic", "GE HealthCare", "Philips", "Draeger", "Mindray"]

SAMPLE_DIR = ROOT / "samples" / "usaspending"


def _post_search(client, *, keywords=None, recipient=None, limit=10, page=1):
    filters = {"award_type_codes": AWARD_TYPES}
    if keywords:
        filters["keywords"] = list(keywords)
    if recipient:
        filters["recipient_search_text"] = [recipient]
    payload = {
        "filters": filters,
        "fields": RICH_FIELDS,
        "limit": limit,
        "page": page,
        "sort": "Award Amount",
        "order": "desc",
    }
    return client.post_json(SEARCH_URL, payload)


def _post_count(client, *, keywords=None, recipient=None):
    filters = {"award_type_codes": AWARD_TYPES}
    if keywords:
        filters["keywords"] = list(keywords)
    if recipient:
        filters["recipient_search_text"] = [recipient]
    return client.post_json(COUNT_URL, {"filters": filters})


def _describe(r, *, name, sample_name, extra=None):
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
            entry["error"] = "response was not JSON"
        if payload is not None:
            entry["structure"] = base.json_shape(payload)
        entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    if extra:
        entry.update(extra)
    return entry


def probe(client, directory):
    probes = []

    # 1. keyword award search -------------------------------------------------
    r = _post_search(client, keywords=["stent"], limit=5)
    first_ids = []
    if r.ok:
        try:
            first_ids = [
                item.get("generated_internal_id", "")
                for item in (r.json() or {}).get("results", [])
            ]
        except Exception:
            first_ids = []
    probes.append(
        _describe(r, name="spending_by_award_keyword_stent",
                  sample_name="spending_by_award_stent.json")
    )

    # 2. award detail: which dates does the API publish? -----------------------
    award_id = next((i for i in first_ids if i), "")
    if award_id:
        r = client.get(AWARD_URL.format(award_id=award_id))
        probes.append(
            _describe(r, name="award_detail_dates", sample_name="award_detail.json",
                      extra={"award_id": award_id})
        )

    # 3. reference endpoint ---------------------------------------------------
    r = client.get(AGENCY_URL)
    probes.append(
        _describe(r, name="references_agency_1", sample_name="references_agency.json")
    )

    # 4. per-firm recipient autocomplete + search + population count ----------
    firm_rows = {}
    for firm in FIRMS:
        slug = firm.lower().replace(" ", "_")
        # autocomplete is POST-only (a GET returns 405); discovered in the first run
        auto = client.post_json(AUTOCOMPLETE_URL, {"search_text": firm, "limit": 10})
        probes.append(
            _describe(auto, name=f"recipient_autocomplete_{slug}",
                      sample_name=f"recipient_autocomplete_{slug}.json", extra={"firm": firm})
        )
        search = _post_search(client, recipient=firm, limit=10)
        probes.append(
            _describe(search, name=f"recipient_search_{slug}",
                      sample_name=f"recipient_{slug}.json", extra={"firm": firm})
        )
        count = _post_count(client, recipient=firm)
        probes.append(
            _describe(count, name=f"recipient_count_{slug}",
                      sample_name=f"recipient_count_{slug}.json", extra={"firm": firm})
        )
        auto_names, rows, total = [], [], None
        if auto.ok:
            try:
                auto_names = [c.get("recipient_name", "") for c in (auto.json() or {}).get("results", [])]
            except Exception:
                auto_names = []
        if search.ok:
            try:
                rows = (search.json() or {}).get("results", []) or []
            except Exception:
                rows = []
        if count.ok:
            try:
                total = ((count.json() or {}).get("results") or {}).get("contracts")
            except Exception:
                total = None
        firm_rows[firm] = {
            "autocomplete_recipients": auto_names,
            "rows": rows,
            "population_count_contracts": total,
        }

    # keep the firm rows for the five-firm probe assembly step
    (directory / "FIRM_ROWS.json").write_text(
        json.dumps(firm_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok_count = sum(1 for p in probes if p["ok"])
    status = "VERIFIED_API" if ok_count else "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id="usaspending",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in probes if p["ok"]][:6],
        notes=(
            "USAspending v2 is anonymously readable: award search is POST-only and "
            "returned real award rows without an API key; award detail exposes "
            "Date Signed and Period of Performance separately, so the publication "
            "date and the performance date are not the same field. "
            "recipient_search_text is a token search (it returns CHANGE HEALTHCARE "
            "for 'GE HealthCare'), so recipient hits are candidates until identity "
            "resolution confirms them."
        ),
    )


outcome = base.run_probe("usaspending", ROOT, probe, budget=20, min_interval=0.9)
for p in outcome.to_dict()["probes"]:
    print(f"{p['status']!s:>4} {p['method']:4} {p['bytes']:>7}B {p['name']}  {p['error'][:60]}")
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
