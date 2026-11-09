"""EU TED — award-level supplier names for medical-device tenders.

Headline finding (this overturns the previous round's verdict)
---------------------------------------------------------------
The earlier conclusion was "TED's search API returns notices without award
suppliers, so TED is BLOCKED". That is only true for **legacy** notices. On the
*current* API:

* ``POST https://api.ted.europa.eu/v3/notices/search`` is keyless and returns
  ``winner-name`` as a multilingual map **and** ``winner-identifier`` as a list
  of national registration numbers, for **eForms-era contract award notices**.
* For legacy 2016-era CANs both come back ``null`` and ``BT-768-Contract`` comes
  back as a boolean presence flag ``[true]/[false]``.
* ``GET /v3/notices/{publication-number}`` returns
  ``400 Missing Authorization header in request`` — an API key is required, so
  full-notice retrieval is REQUIRES_REGISTRATION.
* ``https://ted.europa.eu/en/notice/{pn}/xml`` returns an AWS WAF "Human
  Verification" interstitial to an automated client.

Identity discipline
-------------------
``winner-name`` and ``winner-identifier`` are **parallel lists of unequal
length**, one entry per contract/lot. Their index alignment is NOT established
by the API. Zipping them positionally would manufacture supplier identities, so
this connector emits one record per unique published supplier *name*, keeps the
identifiers as an unaligned list on the notice, and marks identity CANDIDATE.
Placeholder identifiers such as ``"00000000"`` are dropped.

Stage discipline
----------------
A CAN is a contract **award**. ``event_at`` is the contract conclusion date when
the notice exposes one; the publication date is used only as
``source_public_at``. When no conclusion date exists, ``event_at`` stays ``None``
with ``MISSING_FILING_DATE``.

Run
---
    python CONNECTORS/industry/eu_ted.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from _util import (  # noqa: E402
    post_json, write_provenance, write_json, write_records, utc_now,
)

from hz.schema import build_record  # noqa: E402

SOURCE_ID = "eu_ted"
SEARCH = "https://api.ted.europa.eu/v3/notices/search"

#: CPV codes used for the collection query. NB: 33100000 is the *division-level*
#: code ("Medical equipments, pharmaceuticals and personal care products"), so
#: on its own it does NOT mean "medical devices" — see ``cpv_diagnostics`` in
#: PROVENANCE.json.
CPV_PRIMARY = "33100000"
CPV_SUBFAMILY = "33140000"     # Medical consumable accessories
CPV_QUERY_CODES = ["33100000", "33110000", "33140000", "33150000",
                   "33170000", "33190000", "33192000", "33195000"]

WINDOW = "publication-date=today(-365)"
NOTICE_TYPE = "can-standard"

FIELDS = [
    "publication-number", "notice-type", "publication-date", "notice-title",
    "winner-name", "winner-identifier", "winner-country", "buyer-name",
    "total-value", "classification-cpv", "contract-conclusion-date",
]

LICENCE_STATUS = "open_no_explicit_licence"
LICENCE_NOTE = (
    "TED API documentation describes 'reusers of TED Data' as an intended "
    "audience and states the API lets developers 'Retrieve published procurement "
    "notices from the TED website for analysis or reuse', but no formal reuse "
    "licence statement was found on the pages fetched "
    "(https://docs.ted.europa.eu/api/latest/index.html). Recorded as publicly "
    "readable without an explicit reuse licence rather than assumed permissive."
)

DEVICE_TERMS = [
    "ventilator", "mri", "magnetic resonance", "ultrasound", "sonograph",
    "infusion pump", "ct scanner", "computed tomography", "defibrillator",
    "patient monitor", "dialysis", "x-ray", "radiograph", "endoscope",
    "catheter", "stent", "pacemaker", "insulin pump", "syringe pump",
    "analyzer", "electrosurgical", "mammograph", "linear accelerator",
    "surgical robot", "ecg", "electrocardiograph", "prosthe", "implant",
    "wheelchair", "hospital bed", "sterilis", "centrifuge", "incubator",
]

#: Non-medical CPV divisions that co-occur in the same notices; used to flag
#: "this award notice is not purely medical".
NON_MEDICAL_CPV_PREFIXES = ("33", "336", "337", "339", "983", "192", "50", "85")


def _first_str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        for x in v:
            if isinstance(x, str) and x:
                return x
        return None
    if isinstance(v, dict):
        for x in v.values():
            r = _first_str(x)
            if r:
                return r
    return None


def _date_only(v) -> str | None:
    """Normalise TED's '2025-11-06+02:00' / '2025-10-10Z' / list forms."""
    s = _first_str(v)
    if not s:
        return None
    s = s.strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def _earliest_date(v) -> str | None:
    if isinstance(v, list):
        cands = sorted(x for x in (_date_only(i) for i in v) if x)
        return cands[0] if cands else None
    return _date_only(v)


def _primary_name(ml) -> str | None:
    if not ml:
        return None
    if isinstance(ml, str):
        return ml
    for lang in ("eng", "en", "deu", "fra"):
        vals = ml.get(lang)
        if vals:
            return vals[0] if isinstance(vals, list) else str(vals)
    for vals in ml.values():
        if vals:
            return vals[0] if isinstance(vals, list) else str(vals)
    return None


def _unique_names(ml) -> list[str]:
    """Unique published supplier names, order preserved, multilingual map."""
    out: list[str] = []
    if not ml:
        return out
    if isinstance(ml, str):
        return [ml]
    for vals in ml.values():
        for x in vals if isinstance(vals, list) else [vals]:
            if isinstance(x, str) and x.strip() and x.strip() not in out:
                out.append(x.strip())
    return out


def _clean_identifiers(v) -> list[str]:
    """Drop placeholder identifiers; keep the rest verbatim."""
    if not v:
        return []
    items = v if isinstance(v, list) else [v]
    out: list[str] = []
    for x in items:
        if not isinstance(x, str):
            x = _first_str(x)
        if not x:
            continue
        x = x.strip()
        if not x or set(x) <= {"0", "-", " ", "X", "x"}:
            continue
        if x not in out:
            out.append(x)
    return out


def _cpv_list(v) -> list[str]:
    if not v:
        return []
    items = v if isinstance(v, list) else [v]
    return sorted({str(x) for x in items if x})


def _is_medical_cpv(code: str) -> bool:
    return code.startswith("331") or code.startswith("3319") or code.startswith("3314")


def _device_signals(text: str) -> dict:
    low = (text or "").lower()
    hits = sorted({t for t in DEVICE_TERMS if t in low})
    return {"device_terms_found": hits, "names_concrete_device": bool(hits)}


def collect() -> dict:
    prov: list[dict] = []
    records: list = []
    stats = {"posts": 0, "notices": 0, "notices_with_winner": 0,
             "notices_with_identifier": 0, "winner_rows": 0,
             "device_named_notices": 0, "mixed_cpv_notices": 0}
    diagnostics: dict[str, object] = {}

    # ------------------------------------------------------------------
    # 1. CPV predicate diagnostics: does the expert-search CPV predicate match
    #    descendants, and is 33100000 really "medical equipment"?
    # ------------------------------------------------------------------
    for tag, cpv in (("division_33100000", CPV_PRIMARY),
                     ("subfamily_33140000", CPV_SUBFAMILY)):
        q = f"classification-cpv={cpv} AND notice-type={NOTICE_TYPE} AND {WINDOW}"
        p, doc = post_json(SOURCE_ID, SEARCH,
                           {"query": q, "fields": FIELDS, "page": 1, "limit": 1,
                            "scope": "ALL"},
                           name=f"diag_{tag}.json",
                           note=f"CPV predicate diagnostic {cpv}")
        prov.append(p)
        stats["posts"] += 1
        diagnostics[tag] = {
            "query": q,
            "status": p["status"],
            "totalNoticeCount": (doc or {}).get("totalNoticeCount"),
            "sample_cpv_codes": _cpv_list(
                ((doc or {}).get("notices") or [{}])[0].get("classification-cpv")
            ) if (doc or {}).get("notices") else [],
        }

    # ------------------------------------------------------------------
    # 2. Collection: one bounded query, two pages of 100
    # ------------------------------------------------------------------
    cpv_expr = " OR ".join(f"classification-cpv={c}" for c in CPV_QUERY_CODES)
    query = f"({cpv_expr}) AND notice-type={NOTICE_TYPE} AND {WINDOW}"
    total = None
    for page in (1, 2):
        p, doc = post_json(SOURCE_ID, SEARCH,
                           {"query": query, "fields": FIELDS, "page": page,
                            "limit": 100, "scope": "ALL"},
                           name=f"search_can_medical_p{page}.json",
                           note=f"TED v3 expert search page {page}")
        prov.append(p)
        stats["posts"] += 1
        if not doc or not doc.get("notices"):
            continue
        total = doc.get("totalNoticeCount")
        for n in doc["notices"]:
            stats["notices"] += 1
            pub = n.get("publication-number")
            pub_date = _earliest_date(n.get("publication-date"))
            conclusion = _earliest_date(n.get("contract-conclusion-date"))
            winners = _unique_names(n.get("winner-name"))
            ids = _clean_identifiers(n.get("winner-identifier"))
            if winners:
                stats["notices_with_winner"] += 1
            if ids:
                stats["notices_with_identifier"] += 1
            buyer = _primary_name(n.get("buyer-name"))
            title = _primary_name(n.get("notice-title"))
            cpvs = _cpv_list(n.get("classification-cpv"))
            medical_cpvs = [c for c in cpvs if _is_medical_cpv(c)]
            mixed = any(c not in medical_cpvs for c in cpvs)
            if mixed:
                stats["mixed_cpv_notices"] += 1
            sig = _device_signals(f"{title or ''} {n.get('notice-title') or ''}")
            if sig["names_concrete_device"]:
                stats["device_named_notices"] += 1

            for idx, winner in enumerate(winners):
                flags = []
                if not pub_date:
                    flags.append("MISSING_PUBLICATION_DATE")
                if not conclusion:
                    flags.append("MISSING_FILING_DATE")
                rec = build_record(
                    source_id=SOURCE_ID,
                    source_record_id=f"ted:{pub}:supplier:{idx}",
                    entity_type="procurement_award",
                    original_name=f"{winner} — supplier on TED award notice {pub}",
                    identifiers=[
                        {"scheme": "ted_publication_number", "value": str(pub),
                         "issuing_authority": "TED (EU Publications Office)"},
                    ],
                    manufacturer=None,
                    attributes={
                        "stage": "contract_award",
                        "stage_basis": (
                            "notice-type=can-standard is the contract award "
                            "notice; it is not a tender, not a delivery, not "
                            "revenue"
                        ),
                        "notice_type": n.get("notice-type"),
                        "publication_number": pub,
                        "publication_date": pub_date,
                        "contract_conclusion_date": conclusion,
                        "event_at_semantics": (
                            "earliest contract conclusion date in the notice; "
                            "publication date is used only as source_public_at"
                        ),
                        "notice_title": title,
                        "buyer_name": buyer,
                        "buyer_names_by_language": n.get("buyer-name"),
                        "supplier_name": winner,
                        "all_supplier_names_in_notice": winners,
                        "winner_names_by_language": n.get("winner-name"),
                        # deliberately NOT zipped to supplier_name: see docstring
                        "winner_identifiers_in_notice_unaligned": ids,
                        "winner_identifier_count": len(ids),
                        "identity_basis": (
                            "supplier legal name as published. The notice also "
                            "carries national registration numbers, but names and "
                            "identifiers are parallel lists of unequal length and "
                            "the API does not state their alignment, so no "
                            "identifier is attached to this name."
                        ),
                        "cpv_codes": cpvs,
                        "medical_cpv_codes": medical_cpvs,
                        "cpv_notice_is_mixed": mixed,
                        "cpv_scope_note": (
                            "CPV describes what was bought, not who made it. A "
                            "notice containing a medical CPV may award mostly "
                            "non-medical lots."
                        ),
                        "total_value_eur": n.get("total-value"),
                        "value_semantics": (
                            "notice or lot total as published; covers all lots, "
                            "not a per-device price"
                        ),
                        "names_concrete_device": sig["names_concrete_device"],
                        "device_terms_found": sig["device_terms_found"],
                        "device_manufacturer_identified": False,
                        "device_relation_status": (
                            "CANDIDATE" if sig["names_concrete_device"] else "NONE"
                        ),
                    },
                    event_at=conclusion,
                    source_public_at=pub_date,
                    first_observed_at=utc_now(),
                    fetched_at=utc_now(),
                    source_url=f"https://ted.europa.eu/en/notice/{pub}",
                    licence_status=LICENCE_STATUS,
                    licence_note=LICENCE_NOTE,
                    identity_status="CANDIDATE",
                    evidence_status="CANDIDATE",
                    quality_flags=flags,
                    notes=(
                        "Supplier is a name published by the contracting "
                        "authority. No supplier identifier is attached because the "
                        "source does not align its identifier list to its name list."
                    ),
                )
                records.append(rec)
                stats["winner_rows"] += 1

    write_provenance(SOURCE_ID, prov, extra={
        "licence_status": LICENCE_STATUS,
        "licence_note": LICENCE_NOTE,
        "cpv_query_codes": CPV_QUERY_CODES,
        "window": WINDOW,
        "query_used": query,
        "cpv_diagnostics": diagnostics,
        "cpv_diagnostic_interpretation": (
            "If the division-level code 33100000 and the subfamily 33140000 return "
            "the same totalNoticeCount, the expert-search predicate matches "
            "descendants, so 'classification-cpv=33100000' is NOT a "
            "medical-device filter - it covers the whole medical / pharmaceutical "
            "/ personal-care division."
        ),
        "post_endpoints": [
            {"url": SEARCH, "method": "POST",
             "note": "logged manually in SOURCE_PROBES/industry/REQUEST_LOG.jsonl "
                     "with method=POST and request-body sha256"},
            {"url": "https://api.ted.europa.eu/v3/notices/{pn}", "method": "GET",
             "status_observed": 400,
             "error_body": "Missing Authorization header in request",
             "route": "REQUIRES_REGISTRATION for full-notice retrieval"},
            {"url": "https://ted.europa.eu/en/notice/{pn}/xml", "method": "GET",
             "status_observed": 405,
             "error_body": "AWS WAF 'Human Verification' interstitial",
             "route": "BLOCKED_TECHNICAL for automated per-notice retrieval"},
        ],
        "winner_availability": {
            "legacy_can_2016": ("winner-name = null; winner-identifier = null; "
                                "BT-768-Contract = [true]/[false] presence flag"),
            "eforms_can_2025_plus": ("winner-name = multilingual map; "
                                     "winner-identifier = national registration numbers"),
        },
        "coverage_limits": [
            "Two pages of one query (<=200 notices): a bounded sample, not a census.",
            "Only notice-type=can-standard; can-social/can-regional/can-desg and "
            "below-threshold national notices are out of scope.",
            "Only the trailing 12 months; legacy notices do not expose supplier "
            "names through the search API at all.",
            "Supplier names are legal names as published; no cross-language or "
            "corporate-group deduplication was performed.",
            "Award values are notice/lot totals and may cover many devices.",
        ],
    })
    write_json(SOURCE_ID, "summary.json", {
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "post_requests": stats["posts"],
        "total_notice_count_for_query": total,
        "notices_seen": stats["notices"],
        "notices_with_supplier_name": stats["notices_with_winner"],
        "notices_with_supplier_identifier": stats["notices_with_identifier"],
        "supplier_rows": stats["winner_rows"],
        "notices_naming_a_device": stats["device_named_notices"],
        "notices_with_mixed_cpv": stats["mixed_cpv_notices"],
        "cpv_diagnostics": diagnostics,
        "query": query,
    })
    path = write_records(SOURCE_ID, records)
    print(f"eu_ted: {stats['winner_rows']} supplier rows from {stats['notices']} "
          f"notices ({stats['notices_with_winner']} with names, "
          f"{stats['notices_with_identifier']} with ids) -> {path}")
    return {"records": stats["winner_rows"], "notices": stats["notices"],
            "notices_with_winner": stats["notices_with_winner"]}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
