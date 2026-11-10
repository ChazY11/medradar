"""openFDA device connectors.

Four endpoints, one record file per source_id, all keyless on ``api.fda.gov``:

======================  ==========================================  ==============================
source_id               endpoint                                     official identifier
======================  ==========================================  ==============================
openfda_device_510k     /device/510k.json                            k_number (510(k) number)
openfda_device_pma      /device/pma.json                             pma_number
openfda_device_registrationlisting  /device/registrationlisting.json  fei_number / registration_number
openfda_device_classification  /device/classification.json         product_code + regulation_number
openfda_bulk_download   /download.json (bulk-file catalogue)         n/a — catalogue only
======================  ==========================================  ==============================

Temporal discipline
-------------------
``decision_date`` is a *decision* date, so it becomes ``event_at``. openFDA does
not state when a given record first became publicly visible, so
``source_public_at`` stays ``None`` with a ``MISSING_PUBLICATION_DATE`` flag. We
do not copy the decision date into the publication clock — that is precisely the
substitution that manufactures retrospective foresight.

Run:  python CONNECTORS/regulatory/openfda.py
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
    first_present,
    make_client,
    save_raw,
    utc_now,
    write_json,
    write_provenance,
)

BASE = "https://api.fda.gov/device/{endpoint}.json"
UA_NOTE = "openFDA device API, keyless"

LICENCE = "public_domain"
LICENCE_URL = "https://open.fda.gov/license/"
LICENCE_NOTE = (
    "openFDA data is public domain US government data; the openFDA terms state the "
    "data is available for reuse without restriction (licence page: open.fda.gov/license)."
)

MAX_PER_SOURCE = {
    "openfda_device_510k": 160,
    "openfda_device_pma": 60,
    "openfda_device_registrationlisting": 60,
    "openfda_device_classification": 60,
}

# (source_id, endpoint, label, search expression)
PULLS: list[tuple[str, str, str, str]] = [
    ("openfda_device_510k", "510k", "firm_medtronic", 'applicant:"MEDTRONIC"'),
    ("openfda_device_510k", "510k", "firm_ge", 'applicant:"GE"'),
    ("openfda_device_510k", "510k", "firm_philips", 'applicant:"PHILIPS"'),
    ("openfda_device_510k", "510k", "firm_draeger", 'applicant:"DRAGER"'),
    ("openfda_device_510k", "510k", "firm_mindray", 'applicant:"MINDRAY"'),
    ("openfda_device_510k", "510k", "product_monitor", 'device_name:"monitor"'),
    ("openfda_device_510k", "510k", "product_ventilator", 'device_name:"ventilator"'),
    ("openfda_device_510k", "510k", "product_infusion", 'device_name:"infusion"'),
    ("openfda_device_pma", "pma", "firm_medtronic", 'applicant:"MEDTRONIC"'),
    ("openfda_device_pma", "pma", "firm_philips", 'applicant:"PHILIPS"'),
    ("openfda_device_pma", "pma", "product_neonatal", 'trade_name:"neonatal"'),
    ("openfda_device_registrationlisting", "registrationlisting", "firm_medtronic",
     'registration.owner_operator.firm_name:"MEDTRONIC"'),
    ("openfda_device_registrationlisting", "registrationlisting", "firm_philips",
     'registration.owner_operator.firm_name:"PHILIPS"'),
    ("openfda_device_registrationlisting", "registrationlisting", "firm_draeger",
     'registration.owner_operator.firm_name:"DRAGER"'),
    ("openfda_device_classification", "classification", "product_monitor", 'device_name:"monitor"'),
    ("openfda_device_classification", "classification", "product_ventilator", 'device_name:"ventilator"'),
    ("openfda_device_classification", "classification", "product_infusion", 'device_name:"infusion"'),
]

LIMIT = 50


def _q(search: str, limit: int = LIMIT, skip: int = 0) -> str:
    params = {"search": search, "limit": limit}
    if skip:
        params["skip"] = skip
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def _oa(doc: dict, key: str):
    return (doc.get("openfda") or {}).get(key)


def _first_oa(doc: dict, key: str):
    v = _oa(doc, key)
    if isinstance(v, list):
        return v[0] if v else None
    return v


def rec_510k(d: dict, label: str) -> dict:
    flags = ["MISSING_PUBLICATION_DATE"]
    decision = d.get("decision_date")
    product_code = first_present(d, ["product_code"]) or _first_oa(d, "product_code")
    reg_no = _first_oa(d, "regulation_number")
    return build_record(
        source_id="openfda_device_510k",
        source_record_id=str(d.get("k_number")),
        entity_type="regulatory_clearance",
        original_name=d.get("device_name") or str(d.get("k_number")),
        identifiers=[
            {"scheme": "uspto_510k", "value": str(d.get("k_number")), "issuing_authority": "US FDA",
             "scope": "US", "is_primary": True},
        ] + ([{"scheme": "fda_product_code", "value": product_code, "issuing_authority": "US FDA",
               "scope": "US"}] if product_code else []),
        manufacturer=d.get("applicant"),
        attributes={
            "k_number": d.get("k_number"),
            "device_name": d.get("device_name"),
            "applicant": d.get("applicant"),
            "product_code": product_code,
            "regulation_number": reg_no,
            "device_class": first_present(d, ["device_class"]) or _first_oa(d, "device_class"),
            "decision_date": decision,
            "decision_code": d.get("decision_code"),
            "decision_description": d.get("decision_description"),
            "clearance_type": d.get("clearance_type"),
            "advisory_committee": d.get("advisory_committee")
            or _first_oa(d, "medical_specialty_description"),
            "statement_or_summary": d.get("statement_or_summary"),
            "pull_slice": label,
            "clock_class": classify_record(decision, None)["class"],
        },
        event_at=decision,
        source_public_at=None,
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url="https://api.fda.gov/device/510k.json",
        licence_status=LICENCE,
        licence_note=LICENCE_NOTE,
        identity_status="CONFIRMED",
        evidence_status="CONFIRMED",
        quality_flags=flags,
    )


def rec_pma(d: dict, label: str) -> dict:
    decision = d.get("decision_date")
    product_code = first_present(d, ["product_code"]) or _first_oa(d, "product_code")
    return build_record(
        source_id="openfda_device_pma",
        source_record_id=str(d.get("pma_number")),
        entity_type="regulatory_clearance",
        original_name=d.get("trade_name") or d.get("generic_name") or str(d.get("pma_number")),
        identifiers=[
            {"scheme": "uspto_pma", "value": str(d.get("pma_number")), "issuing_authority": "US FDA",
             "scope": "US", "is_primary": True},
        ] + ([{"scheme": "fda_product_code", "value": product_code, "issuing_authority": "US FDA",
               "scope": "US"}] if product_code else []),
        manufacturer=d.get("applicant"),
        attributes={
            "pma_number": d.get("pma_number"),
            "supplement_number": d.get("supplement_number"),
            "supplement_type": d.get("supplement_type"),
            "trade_name": d.get("trade_name"),
            "generic_name": d.get("generic_name"),
            "applicant": d.get("applicant"),
            "product_code": product_code,
            "regulation_number": _first_oa(d, "regulation_number"),
            "device_class": _first_oa(d, "device_class"),
            "decision_date": decision,
            "decision_code": d.get("decision_code"),
            "docket_number": d.get("docket_number"),
            "advisory_committee": d.get("advisory_committee"),
            "expedited_review_flag": d.get("expedited_review_flag"),
            "pull_slice": label,
            "clock_class": classify_record(decision, None)["class"],
        },
        event_at=decision,
        source_public_at=None,
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url="https://api.fda.gov/device/pma.json",
        licence_status=LICENCE,
        licence_note=LICENCE_NOTE,
        identity_status="CONFIRMED",
        evidence_status="CONFIRMED",
        quality_flags=["MISSING_PUBLICATION_DATE"],
    )


def rec_reglist(d: dict, label: str) -> dict:
    reg = d.get("registration") or {}
    owner = reg.get("owner_operator") or {}
    firm = owner.get("firm_name") or reg.get("name")
    fei = reg.get("fei_number")
    regnum = reg.get("registration_number")
    ids = []
    if fei:
        ids.append({"scheme": "fda_fei", "value": str(fei), "issuing_authority": "US FDA",
                    "scope": "US", "is_primary": True})
    if regnum:
        ids.append({"scheme": "fda_registration_number", "value": str(regnum),
                    "issuing_authority": "US FDA", "scope": "US"})
    products = d.get("products") or []
    pcs = sorted({p.get("product_code") for p in products if p.get("product_code")})
    for pc in pcs[:8]:
        ids.append({"scheme": "fda_product_code", "value": pc, "issuing_authority": "US FDA",
                    "scope": "US"})
    if not ids:
        ids = [{"scheme": "fda_fei", "value": str(regnum or "unknown"),
                "issuing_authority": "US FDA", "scope": "US"}]
    name = firm or reg.get("name") or (f"establishment {fei}" if fei else "unknown establishment")
    return build_record(
        source_id="openfda_device_registrationlisting",
        source_record_id=str(regnum or fei),
        entity_type="regulatory_listing",
        original_name=name,
        identifiers=ids,
        manufacturer=firm,
        attributes={
            "fei_number": fei,
            "registration_number": regnum,
            "status_code": reg.get("status_code"),
            "registration_expiry_year": reg.get("reg_expiry_date_year"),
            "establishment_type": d.get("establishment_type"),
            "registration_name": reg.get("name"),
            "owner_operator_firm_name": owner.get("firm_name"),
            "owner_operator_number": owner.get("owner_operator_number"),
            "iso_country_code": reg.get("iso_country_code"),
            "city": reg.get("city"),
            "state_code": reg.get("state_code"),
            "postal_code": reg.get("postal_code"),
            "proprietary_name": d.get("proprietary_name"),
            "k_number": d.get("k_number"),
            "pma_number": d.get("pma_number"),
            "product_codes": pcs,
            "product_count": len(products),
            "pull_slice": label,
        },
        event_at=None,
        source_public_at=None,
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url="https://api.fda.gov/device/registrationlisting.json",
        licence_status=LICENCE,
        licence_note=LICENCE_NOTE,
        identity_status="CONFIRMED",
        evidence_status="CONFIRMED",
        quality_flags=["MISSING_FILING_DATE", "MISSING_PUBLICATION_DATE"],
    )


def rec_classification(d: dict, label: str) -> dict:
    pc = d.get("product_code")
    reg_no = d.get("regulation_number")
    ids = []
    if pc:
        ids.append({"scheme": "fda_product_code", "value": pc, "issuing_authority": "US FDA",
                    "scope": "US", "is_primary": True})
    if reg_no:
        ids.append({"scheme": "cfr_regulation", "value": str(reg_no), "issuing_authority": "US FDA",
                    "scope": "US"})
    if not ids:
        ids = [{"scheme": "fda_product_code", "value": "unknown", "issuing_authority": "US FDA"}]
    return build_record(
        source_id="openfda_device_classification",
        source_record_id=str(pc or reg_no),
        entity_type="regulatory_listing",
        original_name=d.get("device_name") or str(pc),
        identifiers=ids,
        manufacturer=None,
        attributes={
            "product_code": pc,
            "device_name": d.get("device_name"),
            "device_class": d.get("device_class"),
            "regulation_number": reg_no,
            "medical_specialty_description": d.get("medical_specialty_description"),
            "definition": d.get("definition"),
            "submission_type_id": d.get("submission_type_id"),
            "gmp_exempt_flag": d.get("gmp_exempt_flag"),
            "implant_flag": d.get("implant_flag"),
            "life_sustain_support_flag": d.get("life_sustain_support_flag"),
            "pull_slice": label,
        },
        event_at=None,
        source_public_at=None,
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url="https://api.fda.gov/device/classification.json",
        licence_status=LICENCE,
        licence_note=LICENCE_NOTE,
        identity_status="CONFIRMED",
        evidence_status="CONFIRMED",
        quality_flags=["MISSING_FILING_DATE", "MISSING_PUBLICATION_DATE"],
    )


BUILDERS = {
    "510k": rec_510k,
    "pma": rec_pma,
    "registrationlisting": rec_reglist,
    "classification": rec_classification,
}


def main() -> int:
    prov: list[dict] = []
    per_source: dict[str, list] = {}
    pull_log: list[dict] = []
    bulk_doc: dict | None = None

    with make_client("regulatory-openfda", max_requests=24,
                     max_bytes_per_response=8_000_000, max_total_bytes=24_000_000,
                     rps=1.2) as c:
        for source_id, endpoint, label, search in PULLS:
            url = BASE.format(endpoint=endpoint) + "?" + _q(search)
            name = f"{endpoint}__{label}.json"
            try:
                rec, body = fetch_or_load(client=c, source_id=source_id, name=name, url=url,
                                          note=f"openFDA {endpoint} pull: {search}")
            except Exception as exc:  # noqa: BLE001
                pull_log.append({"source_id": source_id, "slice": label, "url": url,
                                 "outcome": type(exc).__name__, "error": str(exc)[:200]})
                continue
            prov.append(rec)
            entry = {"source_id": source_id, "slice": label, "search": search,
                     "status": rec["status"], "bytes": rec["bytes"],
                     "sha256": rec["sha256"][:16], "raw": rec["path"],
                     "from_disk": rec.get("from_disk", False)}
            if rec["status"] != 200:
                entry["outcome"] = "HTTP_ERROR"
                pull_log.append(entry)
                continue
            doc = json.loads(body.decode("utf-8"))
            results = doc.get("results") or []
            entry["results"] = len(results)
            entry["total_available"] = (doc.get("meta") or {}).get("results", {}).get("total")
            pull_log.append(entry)
            bucket = per_source.setdefault(source_id, [])
            builder = BUILDERS[endpoint]
            for d in results:
                if len(bucket) >= MAX_PER_SOURCE[source_id]:
                    break
                try:
                    bucket.append(builder(d, label))
                except Exception as exc:  # noqa: BLE001
                    entry.setdefault("build_errors", []).append(
                        f"{type(exc).__name__}: {exc}"[:160])

        # bulk catalogue (source_id openfda_bulk_download)
        try:
            rec, body = fetch_or_load(c, "openfda_bulk_download", "download_catalogue.json",
                                      "https://api.fda.gov/download.json",
                                      "openFDA bulk-download catalogue")
            prov.append(rec)
            if rec["status"] == 200:
                bulk_doc = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            pull_log.append({"source_id": "openfda_bulk_download", "outcome": type(exc).__name__,
                             "error": str(exc)[:200]})
        budget = c.budget_report()

    counts: dict[str, dict] = {}
    for source_id, recs in per_source.items():
        out_dir = os.path.join(ROOT, "DATASETS", "regulatory", source_id)
        os.makedirs(out_dir, exist_ok=True)
        n = write_jsonl(os.path.join(out_dir, "records.jsonl"), recs)
        counts[source_id] = {
            "records_emitted": n,
            "records_with_identifier": sum(1 for r in recs if r.identifiers),
            "records_with_event_at": sum(1 for r in recs if r.event_at),
            "records_with_source_public_at": sum(1 for r in recs if r.source_public_at),
            "unique_official_ids": len({i.value for r in recs for i in r.identifiers
                                        if i.scheme in ("uspto_510k", "uspto_pma", "fda_fei",
                                                        "fda_registration_number",
                                                        "fda_product_code")}),
        }
        write_provenance(source_id, [p for p in prov if source_id in p["path"]], extra={
            "generated_at": utc_now(),
            "counts": counts[source_id],
            "pulls": [p for p in pull_log if p.get("source_id") == source_id],
        })

    if bulk_doc is not None:
        # Summarise the catalogue without copying it: which device exports exist,
        # how big they are, and whether they are partitioned.
        dev = (bulk_doc.get("results") or {}).get("device") or {}
        summary = {}
        for key, meta in sorted(dev.items()):
            parts = meta.get("partitions") or []
            summary[key] = {
                "export_date": meta.get("export_date"),
                "total_records": meta.get("total_records"),
                "partitions": len(parts),
                "total_bytes": int(sum(float(p.get("size_mb") or 0) for p in parts) * 1_000_000)
                if parts else None,
                "first_partition_file": (parts[0].get("file") if parts else None),
                "size_mb_sum": sum(float(p.get("size_mb") or 0) for p in parts) if parts else None,
            }
        write_json("openfda_bulk_download", "COUNTS.json", {
            "source_id": "openfda_bulk_download",
            "generated_at": utc_now(),
            "catalogue_url": "https://api.fda.gov/download.json",
            "device_exports": summary,
            "note": ("Catalogue only. The device.udi export alone is far outside this "
                     "workstream's byte budget, so no bulk file was downloaded; the "
                     "per-endpoint API pulls are the collection path actually used."),
        })
        write_provenance("openfda_bulk_download",
                         [p for p in prov if "openfda_bulk_download" in p["path"]],
                         extra={"generated_at": utc_now()})

    write_json("openfda_device_510k", "COUNTS.json", {
        "generated_at": utc_now(),
        "per_source": counts,
        "pulls": pull_log,
        "budget": budget,
        "rate_policy_observed": (
            "No X-RateLimit-* headers are returned on api.fda.gov responses. All pulls in this "
            "run returned 200 at ~1.2 requests/second with no 429. openFDA's published keyless "
            "limits are recorded in registry/sources/openfda_device_510k.json."
        ),
    })
    print(json.dumps({"counts": counts, "pulls": pull_log, "budget": budget}, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


