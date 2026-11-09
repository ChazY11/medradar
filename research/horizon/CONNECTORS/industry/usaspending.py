"""USAspending — US federal contract awards for medical equipment.

This is the only source in the INDUSTRY workstream that gets to **IDENTITY**:
every award carries the recipient's official **SAM UEI**, so the supplier is
pinned by an identifier issued by GSA rather than by a name match. What it does
*not* pin is the manufacturer of the device the award bought — the award text
names the supplier, not the OEM.

Stage discipline
----------------
``attributes["stage"] = "contract_award"`` always. An award is **not** a tender,
**not** a delivery and **not** revenue. The field set available on
``/search/spending_by_award/`` does not expose an award *action date*, so
``event_at`` is the period-of-performance start and the record says so
(``attributes["event_at_semantics"]``) and carries ``MISSING_FILING_DATE``.

Contamination
-------------
Filtering by medical PSC codes does **not** yield only devices. PSC 6515 mixes
surgical instruments with COVID-19 antigen tests and vaccines; PSC 6550 is
"in vitro diagnostic substances, reagents, test kits". Verified PSC labels are
quoted from the official filter tree (see PROVENANCE.json), not from memory —
and the task brief's assumed mapping was wrong for 6540 and 6545.

Run
---
    python CONNECTORS/industry/usaspending.py
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from _util import (  # noqa: E402
    make_client, post_json, save_fetch, write_provenance, write_json,
    write_records, utc_now,
)

from hz.schema import build_record  # noqa: E402

SOURCE_ID = "usaspending"
SEARCH = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
PSC_TREE = "https://api.usaspending.gov/api/v2/references/filter_tree/psc/?depth=3"

TIME_PERIOD = [{"start_date": "2020-10-01", "end_date": "2024-09-30"}]

#: Medical PSC codes in scope. Labels are filled in from the official tree.
PSC_CODES = ["6510", "6515", "6520", "6525", "6530", "6540", "6545", "6550"]

#: NAICS codes for medical equipment manufacture (6-digit, as the API requires).
NAICS_CODES = ["339112", "339113", "339114", "339115", "334510", "334517"]

#: Keywords used to find awards whose *text* names a concrete device.
DEVICE_KEYWORDS = [
    "ventilator", "MRI", "ultrasound", "infusion pump", "CT scanner",
    "defibrillator", "patient monitor", "dialysis", "endoscope", "pacemaker",
    "insulin pump", "syringe pump", "analyzer", "electrosurgical",
    "mammography", "linear accelerator", "surgical robot", "ECG",
]

FIELDS = [
    "Award ID", "Recipient Name", "Recipient UEI", "Award Amount", "Description",
    "Start Date", "End Date", "Awarding Agency", "Awarding Sub Agency",
    "NAICS", "PSC", "generated_internal_id",
]

#: Device-type vocabulary for detecting a concrete device named in the award
#: text. Deliberately conservative: a match means "text names a device class",
#: which is CANDIDATE evidence for a device<->award relation, never CONFIRMED.
DEVICE_TERMS = [
    "ventilator", "mri", "magnetic resonance", "ultrasound", "sonograph",
    "infusion pump", "ct scanner", "computed tomography", "defibrillator",
    "patient monitor", "dialysis", "x-ray", "radiograph", "endoscope",
    "catheter", "stent", "pacemaker", "insulin pump", "syringe pump",
    "analyzer", "sequencer", "spectrometer", "electrosurgical", "centrifuge",
    "incubator", "electrocardiograph", "ecg", "mammograph",
    "linear accelerator", "prosthe", "implant", "surgical robot", "endotracheal",
    "laryngoscope", "otoscope", "ophthalmoscope", "spirometer", "catheter",
    "oxygen concentrator", "suction pump", "warming blanket", "autoclave",
]
MODEL_RE = re.compile(r"\b[A-Z]{2,6}[-/]?\d{2,5}[A-Z0-9-]{0,4}\b")

LICENCE_STATUS = "open_no_explicit_licence"
LICENCE_NOTE = (
    "USAspending.gov is a U.S. federal government service publishing agency "
    "contract data; no explicit reuse licence statement was found on the pages "
    "fetched (https://www.usaspending.gov/about returned no licence sentence), so "
    "this is recorded as publicly readable without an explicit reuse licence "
    "rather than assumed permissive. Underlying award data are the awarding "
    "agencies' own public contract records."
)


def _psc_labels(client) -> tuple[dict[str, str], list[dict]]:
    res = client.get(PSC_TREE)
    prov = [save_fetch(SOURCE_ID, "psc_filter_tree_depth3.json", res,
                       note="official PSC code labels")]
    labels: dict[str, str] = {}
    if not res.ok:
        return labels, prov
    doc = res.json()

    def walk(node):
        for ch in node.get("children") or []:
            labels[str(ch.get("id"))] = ch.get("description") or ""
            walk(ch)

    for root in doc.get("results") or []:
        walk(root)
    return labels, prov


def _device_signals(desc: str) -> dict:
    low = (desc or "").lower()
    hits = sorted({t for t in DEVICE_TERMS if t in low})
    models = sorted(set(MODEL_RE.findall(desc or "")))[:6]
    return {
        "device_terms_found": hits,
        "model_like_tokens": models,
        "names_concrete_device": bool(hits),
        "names_concrete_model": bool(models and hits),
    }


def collect() -> dict:
    prov: list[dict] = []
    records: list = []
    seen: dict[str, dict] = {}
    stats = {"posts": 0, "results": 0, "with_uei": 0, "device_named": 0,
             "model_named": 0, "psc_labels": 0}

    with make_client("industry_usaspending", max_requests=6,
                     max_total_bytes=6_000_000) as client:
        psc_labels, pprov = _psc_labels(client)
        prov.extend(pprov)
        stats["psc_labels"] = len(psc_labels)

    searches = [
        ("psc", {
            "award_type_codes": ["A", "B", "C", "D"],
            "psc_codes": PSC_CODES,
            "time_period": TIME_PERIOD,
        }),
        ("naics", {
            "award_type_codes": ["A", "B", "C", "D"],
            "naics_codes": NAICS_CODES,
            "time_period": TIME_PERIOD,
        }),
        ("device_keywords", {
            "award_type_codes": ["A", "B", "C", "D"],
            "keywords": DEVICE_KEYWORDS,
            "time_period": TIME_PERIOD,
        }),
    ]

    for tag, filters in searches:
        body = {
            "filters": filters,
            "fields": FIELDS,
            "page": 1,
            "limit": 100,
            "sort": "Award Amount",
            "order": "desc",
            "subawards": False,
        }
        p, doc = post_json(SOURCE_ID, SEARCH, body, name=f"search_{tag}.json",
                           note=f"spending_by_award POST filter={tag}")
        prov.append(p)
        stats["posts"] += 1
        if not doc:
            continue
        for row in doc.get("results") or []:
            stats["results"] += 1
            gid = row.get("generated_internal_id") or row.get("Award ID") or ""
            if gid in seen:
                seen[gid].setdefault("_found_by", []).append(tag)
                continue
            row["_found_by"] = [tag]
            seen[gid] = row

    for gid, row in seen.items():
        desc = row.get("Description") or ""
        sig = _device_signals(desc)
        uei = row.get("Recipient UEI")
        psc = (row.get("PSC") or {}).get("code")
        naics = (row.get("NAICS") or {}).get("code")
        start = row.get("Start Date")
        if uei:
            stats["with_uei"] += 1
        if sig["names_concrete_device"]:
            stats["device_named"] += 1
        if sig["names_concrete_model"]:
            stats["model_named"] += 1

        identifiers = []
        if uei:
            identifiers.append({
                "scheme": "sam_uei", "value": str(uei),
                "issuing_authority": "GSA / SAM.gov", "is_primary": True,
            })
        if row.get("Award ID"):
            identifiers.append({
                "scheme": "federal_award_id", "value": str(row["Award ID"]),
                "issuing_authority": "USAspending.gov",
            })
        if row.get("generated_internal_id"):
            identifiers.append({
                "scheme": "usaspending_generated_internal_id",
                "value": str(row["generated_internal_id"]),
                "issuing_authority": "USAspending.gov",
            })
        flags = ["MISSING_PUBLICATION_DATE", "MISSING_FILING_DATE"]
        if not identifiers:
            flags.append("MISSING_IDENTIFIER")

        rec = build_record(
            source_id=SOURCE_ID,
            source_record_id=str(gid),
            entity_type="procurement_award",
            original_name=(
                f"{row.get('Recipient Name') or 'unknown recipient'}: "
                f"{(desc or '(no description)')[:180]}"
            ),
            identifiers=identifiers,
            manufacturer=None,
            attributes={
                # ---- the stage field, closed vocabulary -------------------
                "stage": "contract_award",
                "stage_basis": (
                    "USAspending /search/spending_by_award/ returns awarded "
                    "(definitive) contracts, not tenders, deliveries or revenue"
                ),
                "award_id": row.get("Award ID"),
                "recipient_name": row.get("Recipient Name"),
                "recipient_uei": uei,
                "award_amount_usd": row.get("Award Amount"),
                "description": desc,
                "period_of_performance_start": start,
                "period_of_performance_end": row.get("End Date"),
                "event_at_semantics": (
                    "period-of-performance start. The award *action date* is not "
                    "returned by this endpoint's field set (requesting 'Action "
                    "Date' yields null), so it is not used as event_at."
                ),
                "awarding_agency": row.get("Awarding Agency"),
                "awarding_sub_agency": row.get("Awarding Sub Agency"),
                "naics_code": naics,
                "naics_description": (row.get("NAICS") or {}).get("description"),
                "psc_code": psc,
                "psc_description": (row.get("PSC") or {}).get("description")
                                   or psc_labels.get(str(psc)),
                "found_by_queries": row.get("_found_by"),
                "device_terms_found": sig["device_terms_found"],
                "model_like_tokens": sig["model_like_tokens"],
                "names_concrete_device": sig["names_concrete_device"],
                "names_concrete_model": sig["names_concrete_model"],
                # A device<->award relation is CANDIDATE at best: the text names
                # a device class, and the OEM is not identified by the source.
                "device_relation_status": (
                    "CANDIDATE" if sig["names_concrete_device"] else "NONE"
                ),
                "device_manufacturer_identified": False,
                "supplier_identified_by_identifier": bool(uei),
            },
            event_at=start if start else None,
            source_public_at=None,
            first_observed_at=utc_now(),
            fetched_at=utc_now(),
            source_url=SEARCH,
            licence_status=LICENCE_STATUS,
            licence_note=LICENCE_NOTE,
            identity_status="CONFIRMED" if uei else "CANDIDATE",
            evidence_status="CONFIRMED",
            quality_flags=flags,
            notes=(
                "Award record is an official federal contract record. The "
                "recipient is identified by SAM UEI. The manufacturer of the "
                "device (if any) is NOT identified by this source."
            ),
        )
        records.append(rec)

    write_provenance(SOURCE_ID, prov, extra={
        "licence_status": LICENCE_STATUS,
        "licence_note": LICENCE_NOTE,
        "psc_codes_scope": PSC_CODES,
        "psc_labels_observed": {c: psc_labels.get(c) for c in PSC_CODES},
        "naics_codes_scope": NAICS_CODES,
        "device_keywords": DEVICE_KEYWORDS,
        "time_period": TIME_PERIOD,
        "post_endpoints": [
            {"url": SEARCH, "method": "POST",
             "note": "logged manually in SOURCE_PROBES/industry/REQUEST_LOG.jsonl "
                     "with method=POST and a request-body sha256, because "
                     "hz.http.BoundedClient is GET-only by contract"},
        ],
        "coverage_limits": [
            "Award amounts are obligations, NOT revenue, and are not the price of "
            "any device.",
            "Only page 1 (100 rows) per query: this is a bounded sample of the "
            "largest awards, not a census.",
            "Medical PSC codes are contaminated: 6515 mixes instruments with "
            "COVID-19 tests and vaccines; 6550 is reagents/test kits.",
            "PSC 6540 is OPHTHALMIC instruments and 6545 is REPLENISHABLE FIELD "
            "MEDICAL SETS — not 'medical/dental instruments' and 'reagents' as "
            "commonly assumed.",
            "No award in this sample identifies a device manufacturer; OEM "
            "attribution would require a separate source.",
        ],
    })
    write_json(SOURCE_ID, "summary.json", {
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "records": len(records),
        "post_requests": stats["posts"],
        "raw_results": stats["results"],
        "unique_awards": len(seen),
        "awards_with_uei": stats["with_uei"],
        "awards_naming_concrete_device": stats["device_named"],
        "awards_naming_model_like_token": stats["model_named"],
        "psc_labels_available": stats["psc_labels"],
    })
    path = write_records(SOURCE_ID, records)
    print(f"usaspending: {len(records)} records ({stats['with_uei']} with UEI, "
          f"{stats['device_named']} naming a device) -> {path}")
    return {"records": len(records), "with_uei": stats["with_uei"],
            "device_named": stats["device_named"]}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
