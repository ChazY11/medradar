#!/usr/bin/env python
"""Probe: EU TED (Tenders Electronic Daily), domain F, priority P0.

What is tested
--------------
1. ``POST https://api.ted.europa.eu/v3/notices/search`` — TED Search API v3,
   rich field list, **no API key**.  Real notices come back.
2. ``notice-type = cn-standard`` vs ``notice-type = can-standard`` — a contract
   notice and a contract award notice are distinct entries in one index, which
   is what lets us keep "tender published" and "award published" apart.
3. A recent, medical-device award-notice query
   (``can-standard AND FT~"stent" AND publication-date >= 20240101``) with the
   winner fields requested.  Result: the search index returns
   ``winner-name``/``winner-partname`` as **null**, so the *awarded supplier is
   not exposed by the search index* — it lives in the notice XML.
4. ``FT~"Medtronic" AND publication-date >= 20240101`` — a keyword hit count.
   Full text includes the winner name, so this finds notices that mention a
   firm; it is a keyword hit, not a structured award→supplier link.
5. ``classification-cpv = 33100000`` — CPV is a category, not a device ID.
6. The public web host ``ted.europa.eu``: a real XML notice link taken from an
   API response, and the bulk-downloads page.  Both answer with a JavaScript
   "Human Verification" challenge, so **no anonymous bulk XML package was
   verified**.  We did not try to defeat that challenge.

``ted_field_names.txt`` is the raw validation message that lists all 1830
supported search fields; it was produced by sending one deliberately invalid
field name and reading the server's own error text.

Run:  python research/data_expansion/probes/eu_ted/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from medradar.external_sources import base  # noqa: E402

SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
SAMPLE_DIR = ROOT / "samples" / "eu_ted"

RICH_FIELDS = [
    "publication-number",
    "notice-title",
    "publication-date",
    "notice-type",
    "buyer-name",
    "classification-cpv",
    "total-value",
]
AWARD_FIELDS = RICH_FIELDS + [
    "winner-name",
    "winner-partname",
    "winner-country",
    "winner-selection-status",
]
MINIMAL_FIELDS = ["publication-number", "publication-date", "notice-type"]


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
            entry["error"] = "response was not JSON"
        if payload is not None:
            entry["structure"] = base.json_shape(payload)
            if isinstance(payload, dict):
                entry["total_notice_count"] = payload.get("totalNoticeCount")
                notices = payload.get("notices") or []
                if notices:
                    entry["first_notice_keys"] = sorted(notices[0].keys())
        if sample_name:
            entry["sample"] = base.write_sample(SAMPLE_DIR, sample_name, r.body)
    else:
        entry["body_head"] = r.text[:240]
    if extra:
        entry.update(extra)
    return entry


def _search(client, query, fields, limit=5):
    return client.post_json(
        SEARCH_URL, {"query": query, "fields": fields, "page": 1, "limit": limit}
    )


def probe(client, directory):
    probes = []

    # 1. free-text expert query, rich field list ---------------------------
    r = _search(client, 'FT~"stent"', RICH_FIELDS)
    probes.append(_describe(r, name="search_rich_fields", sample_name="search_rich_fields.json"))

    # 2/3. tender notice vs award notice ----------------------------------
    r = _search(client, "notice-type = cn-standard", RICH_FIELDS)
    probes.append(
        _describe(r, name="search_notice_type_cn_standard",
                  sample_name="search_notice_type_cn_standard.json")
    )
    r = _search(client, "notice-type = can-standard", RICH_FIELDS)
    probes.append(
        _describe(r, name="search_notice_type_can_standard",
                  sample_name="search_notice_type_can_standard.json")
    )

    # 4. recent medical award notices: is the winner published? -----------
    r = _search(
        client,
        'notice-type = can-standard AND FT~"stent" AND publication-date >= 20240101',
        AWARD_FIELDS,
        limit=5,
    )
    probes.append(
        _describe(r, name="search_recent_award_stent_winner_fields",
                  sample_name="search_recent_award_stent.json")
    )

    # 5. keyword hit count for one target firm ----------------------------
    r = _search(
        client,
        'FT~"Medtronic" AND publication-date >= 20240101',
        AWARD_FIELDS,
        limit=5,
    )
    probes.append(
        _describe(r, name="search_fulltext_medtronic_since_2024",
                  sample_name="search_medtronic_since_2024.json")
    )
    r = _search(client, 'FT~"Mindray" AND publication-date >= 20240101', AWARD_FIELDS, limit=5)
    probes.append(
        _describe(r, name="search_fulltext_mindray_since_2024",
                  sample_name="search_mindray_since_2024.json")
    )

    # 6. CPV category filter (medical equipment) --------------------------
    r = _search(client, "classification-cpv = 33100000", MINIMAL_FIELDS)
    probes.append(
        _describe(r, name="search_cpv_33100000", sample_name="search_cpv_33100000.json")
    )

    # 7. public web host: a real XML notice link and the bulk page --------
    xml_url = ""
    try:
        first = json.loads((SAMPLE_DIR / "search_rich_fields.json").read_text(encoding="utf-8"))
        notice = (first.get("notices") or [{}])[0]
        xml_url = ((notice.get("links") or {}).get("xml") or {}).get("MUL", "")
    except Exception:
        xml_url = ""
    if xml_url:
        r = client.get(xml_url, accept="application/xml")
        probes.append(_describe(r, name="notice_xml_on_web_host", extra={"target_url": xml_url}))
    r = client.get("https://ted.europa.eu/en/bulk-downloads", accept="text/html")
    probes.append(
        _describe(r, name="bulk_downloads_page",
                  extra={"target_url": "https://ted.europa.eu/en/bulk-downloads"})
    )

    ok_api = [p for p in probes if p["ok"] and "api.ted.europa.eu" in p["url"]]
    status = "VERIFIED_API" if ok_api else "UNAVAILABLE"
    web_failed = [p["name"] for p in probes if not p["ok"] and "ted.europa.eu/" in p["url"]]
    return base.ProbeOutcome(
        source_id="eu_ted",
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[p["url"] for p in ok_api][:6],
        notes=(
            "TED Search API v3 answered anonymous POST queries with real notices (no key). "
            "notice-type separates contract notices (cn-standard, 2.95M) from contract award "
            "notices (can-standard, 2.86M), so tender publication and award publication are "
            "distinguishable. The award winner is NOT in the search index: winner-name / "
            "winner-partname come back null even for a 2024 medical award notice, so an "
            "award→supplier link cannot be built from the search API; a full-text FT~ query "
            "finds notices that merely mention a firm. CPV is a category, not a device ID. "
            "The ted.europa.eu web host serves a 'Human Verification' challenge "
            f"({', '.join(web_failed) or 'none'}), so anonymous bulk XML download is NOT verified."
        ),
    )


outcome = base.run_probe("eu_ted", ROOT, probe, budget=12, min_interval=1.0)
for p in outcome.to_dict()["probes"]:
    print(f"{str(p['status']):>5} {p['method']:4} {p['bytes']:>7}B total={p.get('total_notice_count')} {p['name']}  {p['error'][:40]}")
print("STATUS:", outcome.status, "REQUESTS:", outcome.requests)
