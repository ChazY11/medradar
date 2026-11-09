"""Health Canada MDALL connector (source_id ``canada_mdall``).

The working interface today is **not** the old ``/api/medical-device/…`` path.
Health Canada publishes the current contract at

    https://health-products.canada.ca/api/documentation/mdall-documentation-en.html

and it names the base URI

    https://health-products.canada.ca/api/medical-devices/       (note: "medical-devices")

Everything else in this module follows that document plus the Open Government
Portal record for the same dataset (``open.canada.ca`` dataset
``c801a084-210b-4cd2-8513-26a00b66eb6f``), which also states the licence as the
**Open Government Licence – Canada**.

The data is three levels deep:

    licence           original_licence_no, licence_name, licence_status,
                      first_licence_status_dt, last_refresh_dt, end_date,
                      appl_risk_class, company_id, licence_type_*
    device            device_id, trade_name, first_licence_dt, end_date
    deviceidentifier  device_id, device_identifier (= the model/catalogue token),
                      first_licence_dt (= date the identifier joined the licence),
                      end_date (= date removed)

Temporal finding that matters
-----------------------------
MDALL exposes **no per-record publication date**. ``last_refresh_dt`` is
documented as "the refresh date of the mdall database" — a snapshot stamp for
the whole extract, not the date any individual licence became visible. We
therefore never use it as ``source_public_at``; every MDALL record is
``MISSING_PUBLICATION_DATE``. ``first_licence_status_dt`` is the first-issued
licence date, which is an event date, not a status-change date: MDALL exposes no
"current licence status date" at all.

Run:  python CONNECTORS/regulatory/canada_mdall.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from hz.schema import build_record, write_jsonl  # noqa: E402
from hz.timeq import classify_record  # noqa: E402

from CONNECTORS.regulatory._util import (  # noqa: E402
    ROOT,
    fetch_or_load,
    make_client,
    utc_now,
    write_json,
    write_provenance,
)

SOURCE_ID = "canada_mdall"
BASE = "https://health-products.canada.ca/api/medical-devices"
DOC_URL = "https://health-products.canada.ca/api/documentation/mdall-documentation-en.html"

LICENCE_STATUS = "open_licence"
LICENCE_NOTE = (
    "Open Government Licence - Canada, as stated for the MDALL dataset on the Open "
    "Government Portal record (open.canada.ca dataset c801a084-210b-4cd2-8513-26a00b66eb6f)."
)

FIRMS = {
    "Medtronic": "MEDTRONIC",
    "GE HealthCare": "GE HEALTHCARE",
    "Philips": "PHILIPS",
    "Draeger": "DRAEGER",
    "Mindray": "MINDRAY",
}

MAX_COMPANY_IDS_PER_FIRM = 12
MAX_LICENCES_PER_FIRM = 2
MAX_IDENTIFIER_LOOKUPS = 2

# `device/?licence_number=` is documented but returns an unscoped payload over
# 2.5 MB per call (measured; see COUNTS.pulls). These name-filtered calls do
# scope and stay ~50-100 KB, so devices are collected by name and attributed to
# a firm through the official original_licence_no field.
DEVICE_NAME_PROBES = ("monitor", "ventilator", "infusion")

# MDALL has no "list licences for this company" call that stays bounded for a
# large firm: `licence/?company_id=` returns every licence the company ever held
# and times out for the biggest ones (observed: read timeout on Medtronic's
# company_id 114663). Instead we discover licences through the documented
# `licence_name` search and *filter* the response by the company_ids we already
# resolved from `company/?company_name=`. That keeps every request bounded and
# still attributes licences to a firm through an official field (company_id).
LICENCE_NAME_PROBES = ("monitor", "ventilator", "infusion", "ultrasound")


def q(**params) -> str:
    params.setdefault("lang", "en")
    params.setdefault("type", "json")
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def _licence_rec(d: dict, firm: str, raw_ref: str) -> dict:
    lic = d.get("original_licence_no")
    event = d.get("first_licence_status_dt")
    return build_record(
        source_id=SOURCE_ID,
        source_record_id=f"licence:{lic}",
        entity_type="regulatory_clearance",
        original_name=d.get("licence_name") or f"licence {lic}",
        identifiers=[{
            "scheme": "hc_device_licence",
            "value": str(lic),
            "issuing_authority": "Health Canada",
            "scope": "CA",
            "is_primary": True,
        }],
        manufacturer=None,  # MDALL links company by id, not by name, on this object
        attributes={
            "licence_number": lic,
            "licence_name": d.get("licence_name"),
            "licence_status_code": d.get("licence_status"),
            "licence_status_meaning": _LICENCE_STATUS_MAP.get(d.get("licence_status")),
            "appl_risk_class": d.get("appl_risk_class"),
            "application_id": d.get("application_id"),
            "first_licence_status_dt": event,
            "last_refresh_dt": d.get("last_refresh_dt"),
            "end_date": d.get("end_date"),
            "licence_type_cd": d.get("licence_type_cd"),
            "licence_type_desc": d.get("licence_type_desc"),
            "company_id": d.get("company_id"),
            "target_firm_slice": firm,
            "clock_class": classify_record(event, None)["class"],
            "temporal_note": (
                "first_licence_status_dt is the first-issued licence date (an event date). "
                "last_refresh_dt is a database refresh stamp, not a publication date. "
                "MDALL has no current-status-change date field."
            ),
        },
        event_at=event,
        source_public_at=None,
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url=f"{BASE}/licence/?id={lic}",
        licence_status=LICENCE_STATUS,
        licence_note=LICENCE_NOTE,
        identity_status="CONFIRMED",
        evidence_status="CONFIRMED",
        quality_flags=["MISSING_PUBLICATION_DATE"],
        raw_ref=raw_ref,
    )


def _device_rec(d: dict, firm: str, raw_ref: str) -> dict:
    dev = d.get("device_id")
    lic = d.get("original_licence_no")
    event = d.get("first_licence_dt")
    return build_record(
        source_id=SOURCE_ID,
        source_record_id=f"device:{dev}",
        entity_type="regulatory_listing",
        original_name=d.get("trade_name") or f"device {dev}",
        identifiers=[
            {"scheme": "hc_mdall_device_id", "value": str(dev), "issuing_authority": "Health Canada",
             "scope": "CA", "is_primary": True},
            {"scheme": "hc_device_licence", "value": str(lic), "issuing_authority": "Health Canada",
             "scope": "CA"},
        ],
        manufacturer=None,
        attributes={
            "device_id": dev,
            "trade_name": d.get("trade_name"),
            "original_licence_no": lic,
            "first_licence_dt": event,
            "end_date": d.get("end_date"),
            "target_firm_slice": firm,
            "clock_class": classify_record(event, None)["class"],
        },
        event_at=event,
        source_public_at=None,
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url=f"{BASE}/device/?licence_number={lic}",
        licence_status=LICENCE_STATUS,
        licence_note=LICENCE_NOTE,
        identity_status="CONFIRMED",
        evidence_status="CONFIRMED",
        quality_flags=["MISSING_PUBLICATION_DATE"],
        raw_ref=raw_ref,
    )


def _identifier_rec(d: dict, firm: str, raw_ref: str) -> dict:
    dev = d.get("device_id")
    lic = d.get("original_licence_no")
    ident = d.get("device_identifier")
    event = d.get("first_licence_dt")
    return build_record(
        source_id=SOURCE_ID,
        source_record_id=f"identifier:{dev}:{ident}",
        entity_type="product_identifier",
        original_name=str(ident),
        identifiers=[
            {"scheme": "hc_mdall_device_identifier", "value": str(ident),
             "issuing_authority": "Health Canada", "scope": "CA", "is_primary": True},
            {"scheme": "hc_mdall_device_id", "value": str(dev), "issuing_authority": "Health Canada",
             "scope": "CA"},
            {"scheme": "hc_device_licence", "value": str(lic), "issuing_authority": "Health Canada",
             "scope": "CA"},
        ],
        manufacturer=None,
        attributes={
            "device_identifier": ident,
            "device_id": dev,
            "original_licence_no": lic,
            "first_licence_dt": event,
            "end_date": d.get("end_date"),
            "target_firm_slice": firm,
            "identifier_semantics": (
                "MDALL device_identifier is Health Canada's own model/catalogue token for the "
                "licensed device line (e.g. 'P02-14030'). It is NOT a UDI-DI and shares no "
                "namespace with FDA GUDID."
            ),
            "clock_class": classify_record(event, None)["class"],
        },
        event_at=event,
        source_public_at=None,
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url=f"{BASE}/deviceidentifier/?id={dev}",
        licence_status=LICENCE_STATUS,
        licence_note=LICENCE_NOTE,
        identity_status="CONFIRMED",
        evidence_status="CONFIRMED",
        quality_flags=["MISSING_PUBLICATION_DATE"],
        raw_ref=raw_ref,
    )


_LICENCE_STATUS_MAP = {
    "C": "Cancelled",
    "D": "Issued/Conditional",
    "I": "Issued/Active",
    "M": "Merge",
    "O": "Discontinued at Renewal",
    "P": "Pending signature",
    "R": "Cancelled Renewal No Response",
    "S": "Suspended",
    "W": "Withdrawn",
    "Q": "Suspended/Invalid QS Certification",
    "X": "Cancelled QS/2003",
}


def main() -> int:
    prov: list[dict] = []
    records: list[dict] = []
    log: list[dict] = []

    def pull(name: str, url: str, note: str):
        try:
            rec, body = fetch_or_load(client, SOURCE_ID, name, url, note)
        except Exception as exc:  # noqa: BLE001
            log.append({"name": name, "url": url, "outcome": type(exc).__name__,
                        "error": str(exc)[:220]})
            return None, None
        prov.append(rec)
        try:
            doc = json.loads(body.decode("utf-8"))
        except ValueError:
            doc = None
        log.append({"name": name, "url": url, "status": rec["status"], "bytes": rec["bytes"],
                    "sha256": rec["sha256"][:16], "from_disk": rec.get("from_disk", False),
                    "items": (len(doc) if isinstance(doc, list) else None),
                    "raw": rec["path"]})
        return doc, rec["path"]

    live = make_client("regulatory-mdall", max_requests=24,
                       max_bytes_per_response=2_500_000, max_total_bytes=16_000_000,
                       rps=1.2)
    with live as client:
        # step 1 — resolve each firm to its official company_id(s)
        firm_company_ids: dict[str, set[int]] = {}
        company_names: dict[str, list[str]] = {}
        for firm, needle in FIRMS.items():
            doc, _raw = pull(
                f"company__{firm.replace(' ', '_').lower()}.json",
                f"{BASE}/company/?{q(company_name=needle)}",
                f"MDALL company search for {firm}",
            )
            companies = doc if isinstance(doc, list) else []
            ids = {int(c["company_id"]) for c in companies if c.get("company_id")}
            firm_company_ids[firm] = ids
            company_names[firm] = [c.get("company_name") for c in companies][:12]
            log[-1]["company_ids_found"] = len(ids)
            log[-1]["company_names_sample"] = company_names[firm][:4]

        # step 2 — bounded licence discovery, attributed by company_id
        licences_by_firm: dict[str, list[dict]] = {f: [] for f in FIRMS}
        for word in LICENCE_NAME_PROBES:
            doc, lraw = pull(
                f"licence_name__{word}.json",
                f"{BASE}/licence/?{q(licence_name=word)}",
                f"MDALL licence search for licence_name={word}",
            )
            licences = doc if isinstance(doc, list) else []
            attributed = 0
            for d in licences:
                cid = d.get("company_id")
                try:
                    cid = int(cid) if cid is not None else None
                except (TypeError, ValueError):
                    cid = None
                for firm, ids in firm_company_ids.items():
                    if cid is not None and cid in ids:
                        if len(licences_by_firm[firm]) < MAX_LICENCES_PER_FIRM * 6:
                            licences_by_firm[firm].append(d)
                            attributed += 1
                        break
            log[-1]["licences_returned"] = len(licences)
            log[-1]["licences_attributed_to_target_firms"] = attributed

        # step 3 — licences
        licence_to_firm: dict[int, str] = {}
        for firm, lics in licences_by_firm.items():
            for d in lics[:MAX_LICENCES_PER_FIRM * 6]:
                records.append(_licence_rec(d, firm, "see pulls: licence_name__*"))
                lic_no = d.get("original_licence_no")
                if lic_no is not None:
                    licence_to_firm[lic_no] = firm

        # step 4 — devices.
        # `device/?licence_number=N` is the documented filter but does NOT behave:
        # every attempt returned a payload larger than 2.5 MB (see COUNTS.pulls),
        # i.e. it does not scope to one licence. `device/?device_name=…&state=active`
        # does scope and stays small, so devices are pulled by name and then
        # attributed to a firm through the official `original_licence_no` field.
        for word in DEVICE_NAME_PROBES:
            ddoc, draw = pull(
                f"device_name__{word}.json",
                f"{BASE}/device/?{q(device_name=word, state='active')}",
                f"MDALL active devices whose trade name contains {word}",
            )
            devs = ddoc if isinstance(ddoc, list) else []
            attributed = 0
            for dv in devs:
                lic_no = dv.get("original_licence_no")
                firm = licence_to_firm.get(lic_no)
                if firm is None:
                    continue
                records.append(_device_rec(dv, firm, draw))
                attributed += 1
            log[-1]["devices_returned"] = len(devs)
            log[-1]["devices_attributed_to_target_firms"] = attributed

        # step 5 — device identifiers (the only place MDALL publishes model tokens)
        dev_ids: list[tuple[int, str]] = []
        for r in records:
            if r.entity_type == "regulatory_listing" and r.attributes.get("device_id"):
                dev_ids.append((r.attributes["device_id"],
                                r.attributes.get("target_firm_slice") or "Medtronic"))
        for dev_id, firm in dev_ids[:MAX_IDENTIFIER_LOOKUPS]:
            idoc, iraw = pull(
                f"deviceidentifier__{dev_id}.json",
                f"{BASE}/deviceidentifier/?{q(id=dev_id)}",
                f"MDALL device identifiers for device_id {dev_id}",
            )
            idents = idoc if isinstance(idoc, list) else ([idoc] if isinstance(idoc, dict) else [])
            for it in idents:
                if isinstance(it, dict) and it.get("device_identifier"):
                    records.append(_identifier_rec(it, firm, iraw))

        budget = client.budget_report()

    # dedupe (the same licence can be reached from several company_ids)
    seen = set()
    uniq = []
    for r in records:
        if r.source_record_id in seen:
            continue
        seen.add(r.source_record_id)
        uniq.append(r)

    out_dir = os.path.join(ROOT, "DATASETS", "regulatory", SOURCE_ID)
    os.makedirs(out_dir, exist_ok=True)
    n = write_jsonl(os.path.join(out_dir, "records.jsonl"), uniq)

    by_entity: dict[str, int] = {}
    for r in uniq:
        by_entity[r.entity_type] = by_entity.get(r.entity_type, 0) + 1
    counts = {
        "source_id": SOURCE_ID,
        "generated_at": utc_now(),
        "documentation_url": DOC_URL,
        "base_uri": BASE,
        "records_emitted": n,
        "by_entity_type": by_entity,
        "records_with_official_identifier": sum(1 for r in uniq if r.identifiers),
        "records_with_event_at": sum(1 for r in uniq if r.event_at),
        "records_with_source_public_at": sum(1 for r in uniq if r.source_public_at),
        "per_target_firm": {f: sum(1 for r in uniq if r.attributes.get("target_firm_slice") == f)
                            for f in FIRMS},
        "pulls": log,
        "budget": budget,
        "temporal_answer": {
            "first_licence_date_field": "first_licence_status_dt (documented: 'The date of the "
                                        "first issued licence')",
            "current_licence_status_date_field": None,
            "what_exists_instead": [
                "licence_status (a code, not a dated event)",
                "last_refresh_dt (documented: 'The refresh date of the mdall database' — a "
                "snapshot stamp for the whole extract)",
                "end_date (cancellation date, null while active)",
                "per-device/identifier first_licence_dt and end_date",
            ],
            "consequence": (
                "MDALL cannot date a status change. It supports 'first licensed' and 'removed' "
                "reasoning only, and it has no publication clock, so no MDALL record may be used "
                "to claim a record became observable at a known time."
            ),
        },
        "archive_probe": {
            "archived_state_documented": True,
            "note": ("The documented state=archived parameter returns licences that carry a "
                     "cancellation date, so past licences are retained with the same object "
                     "shape. It was NOT pulled here: the parameter has no result limit and the "
                     "full archived list is outside this workstream's byte/time budget."),
        },
    }
    write_json(SOURCE_ID, "COUNTS.json", counts)
    write_provenance(SOURCE_ID, prov, extra={
        "generated_at": utc_now(),
        "documentation_url": DOC_URL,
        "counts_file": f"DATASETS/regulatory/{SOURCE_ID}/COUNTS.json",
    })
    print(json.dumps({k: v for k, v in counts.items() if k not in ("pulls", "budget")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
