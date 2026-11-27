"""AccessGUDID connector (source_id ``accessgudid``).

Two independent access paths, both official and keyless:

1. **Release files** — ``https://accessgudid.nlm.nih.gov/download`` publishes
   ``gudid_full_release_*.zip`` / ``gudid_monthly_update_*.zip`` /
   ``gudid_weekly_update_*.zip``. A monthly update is a ZIP of daily ZIPs, each
   holding one GUDID XML delta file. Among all the release artifacts this is the
   only one small enough to keep inside a bounded research budget: the October
   2026 monthly update is 7,002,352 bytes and contains 21 daily files covering
   roughly 40k device records.
2. **Device Lookup API** — ``/api/v3/devices/lookup.json?di=…`` returns one full
   GUDID record as JSON (the documented shape is in
   ``/resources/developers/v3/device_lookup_api``).

What GUDID gives us, and what it does not
-----------------------------------------
GUDID gives the device identifier (UDI-DI), brand name, version/model number,
catalogue number, company name, DUNS, device description, product codes, device
class, GMDN terms and — crucially for the four-clocks discipline — both
``devicePublishDate`` (when the record first became publicly visible) and
``publicVersionDate`` (when the current version became visible).

It does **not** give a clearance decision date, a 510(k)/PMA number, or a
regulation number. Those live in the openFDA endpoints. We therefore set
``event_at = None`` and flag ``MISSING_FILING_DATE`` rather than inventing a
date from the publish clock — that substitution is exactly the error this
project exists to avoid.

Run:  python CONNECTORS/regulatory/accessgudid.py
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lxml import etree  # noqa: E402

from hz.schema import build_record, write_jsonl  # noqa: E402
from hz.timeq import classify_record  # noqa: E402

from CONNECTORS.regulatory._util import (  # noqa: E402
    ROOT,
    make_client,
    save_raw,
    utc_now,
    write_json,
    write_provenance,
)

SOURCE_ID = "accessgudid"

MONTHLY_ZIPS = [
    "gudid_monthly_update_october_2026.zip",
]
ZIP_URL = "https://accessgudid.nlm.nih.gov/release_files/download/{name}"
LOOKUP_URL = "https://accessgudid.nlm.nih.gov/api/v3/devices/lookup.json?di={di}"

NS = "{http://www.fda.gov/cdrh/gudid}"

# The five target firms, matched case-insensitively against GUDID companyName.
# These are *display-name* matches for sampling only; they never enter a record's
# identifiers, and identity is never asserted from them.
FIRMS = {
    "Medtronic": (r"MEDTRONIC",),
    "GE HealthCare": (r"GE HEALTHCARE", r"GE MEDICAL", r"GE HFS", r"OHMEDA", r"GE DATEX"),
    "Philips": (r"PHILIPS",),
    "Draeger": (r"DR[AÄ]GER", r"DRAGER"),
    "Mindray": (r"MINDRAY",),
}

# Product-family keywords used for the product-code-driven slice.
FAMILIES = {
    "monitoring": (r"MONITOR", r"PULSE OXIMET", r"CAPNOGRAPH", r"ELECTROCARDIOGRAPH"),
    "respiratory_support": (r"VENTILATOR", r"RESPIRATOR", r"CPAP", r"BIPAP", r"OXYGEN", r"HUMIDIFI"),
    "imaging": (r"ULTRASOUND", r"\bMRI\b", r"MAGNETIC RESONANCE", r"TOMOGRAPH", r"X-RAY", r"MAMMOGRAPH", r"FLUOROSCOP"),
    "life_support": (r"DEFIBRILLAT", r"HEART-LUNG", r"ECMO", r"INFUSION PUMP", r"SYRINGE PUMP", r"ANESTHESIA"),
    "neonatal": (r"INCUBATOR", r"NEONAT", r"INFANT WARMER", r"RADIANT WARMER", r"BILIRUBIN"),
}

MAX_RECORDS = 320
MAX_PER_FIRM = 70
MAX_PER_FAMILY = 60


def _txt(el, path: str) -> str | None:
    found = el.find(path)
    if found is None:
        return None
    if found.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
        return None
    t = (found.text or "").strip()
    return t or None


def _find_text(el, localname: str) -> list[str]:
    out = []
    for node in el.iter(NS + localname):
        v = (node.text or "").strip()
        if v:
            out.append(v)
    return out


def parse_device(el) -> dict | None:
    """Extract one GUDID device element into a plain dict. Never guesses."""
    ids = []
    for ident in el.iter(NS + "identifier"):
        ids.append(
            {
                "deviceId": _txt(ident, NS + "deviceId"),
                "deviceIdType": _txt(ident, NS + "deviceIdType"),
                "deviceIdIssuingAgency": _txt(ident, NS + "deviceIdIssuingAgency"),
                "pkgStatus": _txt(ident, NS + "pkgStatus"),
                "containsDINumber": _txt(ident, NS + "containsDINumber"),
            }
        )
    primary = [i["deviceId"] for i in ids if i["deviceIdType"] == "Primary" and i["deviceId"]]
    company = _txt(el, NS + "companyName")
    desc = _txt(el, NS + "deviceDescription")
    if not primary or not company:
        return None
    return {
        "di": primary[0],
        "all_di": [i["deviceId"] for i in ids if i["deviceId"]],
        "identifiers": ids,
        "record_key": _txt(el, NS + "publicDeviceRecordKey"),
        "version_status": _txt(el, NS + "publicVersionStatus"),
        "record_status": _txt(el, NS + "deviceRecordStatus"),
        "version_number": _txt(el, NS + "publicVersionNumber"),
        "version_date": _txt(el, NS + "publicVersionDate"),
        "publish_date": _txt(el, NS + "devicePublishDate"),
        "comm_dist_end_date": _txt(el, NS + "deviceCommDistributionEndDate"),
        "comm_dist_status": _txt(el, NS + "deviceCommDistributionStatus"),
        "brand": _txt(el, NS + "brandName"),
        "model": _txt(el, NS + "versionModelNumber"),
        "catalog": _txt(el, NS + "catalogNumber"),
        "duns": _txt(el, NS + "dunsNumber"),
        "company": company,
        "description": desc,
        "device_count": _txt(el, NS + "deviceCount"),
        "mri_safety": _txt(el, NS + "MRISafetyStatus"),
        "rx": _txt(el, NS + "rx"),
        "otc": _txt(el, NS + "otc"),
        "product_codes": _find_text(el, "productCode"),
        "device_classes": _find_text(el, "deviceClass"),
        "gmdn_codes": _find_text(el, "gmdnCode"),
        "gmdn_names": _find_text(el, "gmdnPTName"),
    }


def firm_of(company: str) -> str | None:
    up = (company or "").upper()
    for firm, pats in FIRMS.items():
        for p in pats:
            if re.search(p, up):
                return firm
    return None


def families_of(text: str) -> list[str]:
    up = (text or "").upper()
    out = []
    for fam, pats in FAMILIES.items():
        if any(re.search(p, up) for p in pats):
            out.append(fam)
    return out


def iter_devices_from_zip(raw: bytes, dayname: str):
    """Yield parsed devices from one GUDID daily XML inside the monthly bundle."""
    outer = zipfile.ZipFile(io.BytesIO(raw))
    for inner_name in sorted(n for n in outer.namelist() if n.lower().endswith(".zip")):
        inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))
        for xml_name in sorted(n for n in inner.namelist() if n.lower().endswith(".xml")):
            payload = inner.read(xml_name)
            for _event, el in etree.iterparse(
                io.BytesIO(payload), events=("end",), tag=NS + "device", resolve_entities=False
            ):
                dev = parse_device(el)
                # free the tree as we go: the full monthly set is ~40k records
                el.clear()
                while el.getprevious() is not None:
                    del el.getparent()[0]
                if dev is not None:
                    yield dev, dayname, inner_name, xml_name


def to_record(dev: dict, dayname: str, fams: list[str], firm: str | None, raw_ref: str) -> dict:
    flags: list[str] = ["MISSING_FILING_DATE"]
    ids = [{"scheme": "udi_di", "value": dev["di"], "issuing_authority": _issuing_agency(dev),
            "scope": "US", "is_primary": True}]
    clock = classify_record(None, dev["publish_date"])
    rec = build_record(
        source_id=SOURCE_ID,
        source_record_id=dev["record_key"] or dev["di"],
        entity_type="product_identifier",
        original_name=dev["brand"] or dev["description"] or dev["di"],
        identifiers=ids,
        manufacturer=dev["company"],
        attributes={
            "device_description": dev["description"],
            "brand_name": dev["brand"],
            "version_model_number": dev["model"],
            "catalog_number": dev["catalog"],
            "company_name": dev["company"],
            "duns_number": dev["duns"],
            "product_codes": dev["product_codes"],
            "device_class": dev["device_classes"][0] if dev["device_classes"] else None,
            "gmdn_codes": dev["gmdn_codes"][:5],
            "gmdn_names": dev["gmdn_names"][:5],
            "all_device_ids": dev["all_di"],
            "identifier_details": dev["identifiers"],
            "public_version_status": dev["version_status"],
            "public_version_number": dev["version_number"],
            "public_version_date": dev["version_date"],
            "device_publish_date": dev["publish_date"],
            "device_comm_dist_end_date": dev["comm_dist_end_date"],
            "device_comm_dist_status": dev["comm_dist_status"],
            "mri_safety_status": dev["mri_safety"],
            "rx": dev["rx"],
            "otc": dev["otc"],
            "device_count": dev["device_count"],
            "release_file": dayname,
            "product_family_slice": fams,
            "target_firm_slice": firm,
            "clock_class": clock["class"],
        },
        event_at=None,
        source_public_at=dev["publish_date"],
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url="https://accessgudid.nlm.nih.gov/download",
        licence_status="public_domain",
        licence_note=(
            "US federal government work: GUDID is published by FDA/NLM; the AccessGUDID "
            "site states no reuse restriction and robots.txt disallows nothing."
        ),
        identity_status="CANDIDATE" if firm else "UNKNOWN",
        evidence_status="CANDIDATE",
        quality_flags=flags,
        raw_ref=raw_ref,
    )
    return rec


def _issuing_agency(dev: dict) -> str | None:
    for i in dev["identifiers"]:
        if i["deviceIdType"] == "Primary":
            return i["deviceIdIssuingAgency"]
    return None


def ensure_zips(client) -> tuple[list[dict], list[bytes]]:
    prov: list[dict] = []
    bodies: list[bytes] = []
    for name in MONTHLY_ZIPS:
        path = os.path.join(ROOT, "DATASETS", "regulatory", SOURCE_ID, "raw", name)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                bodies.append(fh.read())
            prov.append({"path": os.path.relpath(path, ROOT).replace(os.sep, "/"),
                         "note": "already on disk from this workstream's earlier fetch",
                         "bytes": os.path.getsize(path)})
            continue
        res = client.get(ZIP_URL.format(name=name))
        rec = save_raw(SOURCE_ID, name, res, url_note="GUDID monthly release ZIP")
        prov.append(rec)
        bodies.append(res.body)
    return prov, bodies


def lookup_sample(dis: list[str], max_lookups: int = 6) -> tuple[list[dict], list[dict], list[dict]]:
    """Fetch a few DI lookups as direct API evidence, and parse them."""
    prov: list[dict] = []
    records: list[dict] = []
    seen: list[dict] = []
    with make_client("regulatory-accessgudid-lookup", max_requests=max_lookups + 1,
                     max_bytes_per_response=1_000_000, max_total_bytes=8_000_000,
                     rps=1.0) as c:
        for di in dis[:max_lookups]:
            url = LOOKUP_URL.format(di=di)
            try:
                res = c.get(url)
            except Exception as exc:  # noqa: BLE001
                seen.append({"di": di, "outcome": type(exc).__name__, "error": str(exc)[:200]})
                continue
            rec = save_raw(SOURCE_ID, f"lookup_{di}.json", res, url_note="AccessGUDID v3 device lookup")
            prov.append(rec)
            seen.append({"di": di, "status": res.status, "bytes": len(res.body)})
            if not res.ok:
                continue
            try:
                doc = res.json()
            except ValueError:
                continue
            dev = (doc.get("gudid") or {}).get("device") or {}
            if not dev:
                continue
            records.append(_record_from_lookup(dev, di, rec["path"]))
        budget = c.budget_report()
    return prov, records, seen


def _record_from_lookup(dev: dict, di: str, raw_ref: str) -> dict:
    idents = []
    for i in (dev.get("identifiers") or {}).get("identifier") or []:
        idents.append(
            {
                "deviceId": i.get("deviceId"),
                "deviceIdType": i.get("deviceIdType"),
                "deviceIdIssuingAgency": i.get("deviceIdIssuingAgency"),
                "pkgStatus": i.get("pkgStatus"),
                "containsDINumber": i.get("containsDINumber"),
            }
        )
    primary = [i["deviceId"] for i in idents if i["deviceIdType"] == "Primary" and i["deviceId"]]
    company = dev.get("companyName")
    publish = (dev.get("devicePublishDate") or "")[:10] or None
    flags = ["MISSING_FILING_DATE", "PARSED_FROM_HTML"] if False else ["MISSING_FILING_DATE"]
    clock = classify_record(None, publish)
    firm = firm_of(company or "")
    return build_record(
        source_id=SOURCE_ID,
        source_record_id=dev.get("publicDeviceRecordKey") or di,
        entity_type="product_identifier",
        original_name=dev.get("brandName") or dev.get("deviceDescription") or di,
        identifiers=[{
            "scheme": "udi_di",
            "value": primary[0] if primary else di,
            "issuing_authority": next((i["deviceIdIssuingAgency"] for i in idents
                                    if i["deviceIdType"] == "Primary"), None),
            "scope": "US",
            "is_primary": True,
        }],
        manufacturer=company,
        attributes={
            "device_description": dev.get("deviceDescription"),
            "brand_name": dev.get("brandName"),
            "version_model_number": dev.get("versionModelNumber"),
            "catalog_number": dev.get("catalogNumber"),
            "company_name": company,
            "duns_number": dev.get("dunsNumber"),
            "device_class": None,
            "all_device_ids": [i["deviceId"] for i in idents if i["deviceId"]],
            "identifier_details": idents,
            "public_version_status": dev.get("publicVersionStatus"),
            "public_version_number": dev.get("publicVersionNumber"),
            "public_version_date": (dev.get("publicVersionDate") or "")[:10] or None,
            "device_publish_date": publish,
            "device_comm_dist_end_date": (dev.get("deviceCommDistributionEndDate") or "")[:10] or None,
            "device_comm_dist_status": dev.get("deviceCommDistributionStatus"),
            "mri_safety_status": dev.get("MRISafetyStatus"),
            "access_path": "lookup_api_v3",
            "target_firm_slice": firm,
            "clock_class": clock["class"],
        },
        event_at=None,
        source_public_at=publish,
        first_observed_at=None,
        fetched_at=utc_now(),
        source_url=LOOKUP_URL.format(di=di),
        licence_status="public_domain",
        licence_note="US federal government work, published by FDA/NLM via AccessGUDID.",
        identity_status="CANDIDATE" if firm else "UNKNOWN",
        evidence_status="CANDIDATE",
        quality_flags=flags,
        raw_ref=raw_ref,
    )


def main() -> int:
    out_dir = os.path.join(ROOT, "DATASETS", "regulatory", SOURCE_ID)
    os.makedirs(out_dir, exist_ok=True)

    with make_client("regulatory-accessgudid-fetch", max_requests=4,
                     max_bytes_per_response=12_000_000, max_total_bytes=24_000_000,
                     rps=1.0) as c:
        prov, bodies = ensure_zips(c)

    # Scan the whole archive into bounded buckets rather than stopping at the first
    # N matches: a global first-come cap lets one alphabetically-early firm crowd
    # out the others, which would silently bias the firm sample.
    scanned = 0
    daily_seen: list[str] = []
    seen_di: set[str] = set()
    firm_buckets: dict[str, list[dict]] = {f: [] for f in FIRMS}
    family_buckets: dict[str, list[dict]] = {f: [] for f in FAMILIES}
    for name, body in zip(MONTHLY_ZIPS, bodies):
        raw_ref = f"DATASETS/regulatory/{SOURCE_ID}/raw/{name}"
        for dev, _archive, inner_name, _xml in iter_devices_from_zip(body, name):
            scanned += 1
            if inner_name not in daily_seen:
                daily_seen.append(inner_name)
            if dev["di"] in seen_di:
                continue
            firm = firm_of(dev["company"])
            fams = families_of(" ".join(filter(None, [dev["brand"], dev["description"]])))
            if not firm and not fams:
                continue
            seen_di.add(dev["di"])
            item = {"dev": dev, "firm": firm, "fams": fams, "raw_ref": raw_ref,
                    "release_file": inner_name}
            if firm and len(firm_buckets[firm]) < MAX_PER_FIRM:
                firm_buckets[firm].append(item)
            for f in fams:
                if len(family_buckets[f]) < MAX_PER_FAMILY:
                    family_buckets[f].append(item)

    # Round-robin the firm buckets first (so every target firm is represented),
    # then top up from the product-family buckets.
    records: list[dict] = []
    emitted: set[str] = set()

    def _emit(item: dict) -> None:
        if len(records) >= MAX_RECORDS:
            return
        di = item["dev"]["di"]
        if di in emitted:
            return
        emitted.add(di)
        records.append(to_record(item["dev"], item["release_file"], item["fams"],
                                 item["firm"], item["raw_ref"]))

    idx = 0
    while len(records) < MAX_RECORDS:
        progressed = False
        for firm in FIRMS:
            bucket = firm_buckets[firm]
            if idx < len(bucket):
                _emit(bucket[idx])
                progressed = True
        if not progressed:
            break
        idx += 1
    idx = 0
    while len(records) < MAX_RECORDS:
        progressed = False
        for fam in FAMILIES:
            bucket = family_buckets[fam]
            if idx < len(bucket):
                _emit(bucket[idx])
                progressed = True
        if not progressed:
            break
        idx += 1

    per_firm = {f: sum(1 for r in records
                       if r.attributes.get("target_firm_slice") == f) for f in FIRMS}
    family_counts = {f: sum(1 for r in records
                            if f in (r.attributes.get("product_family_slice") or []))
                     for f in FAMILIES}

    # direct API lookups on a deterministic sample of the DIs we found
    dis = [r.identifiers[0].value for r in records[:6]]
    lookup_prov, lookup_records, lookup_seen = (lookup_sample(dis) if dis else ([], [], []))
    known = {(r.source_record_id) for r in records}
    added = [r for r in lookup_records if r.source_record_id not in known]
    records.extend(added)

    path = os.path.join(out_dir, "records.jsonl")
    n = write_jsonl(path, records)
    counts = {
        "source_id": SOURCE_ID,
        "generated_at": utc_now(),
        "records_emitted": n,
        "devices_scanned": scanned,
        "daily_release_files_scanned": len(daily_seen),
        "monthly_archives": MONTHLY_ZIPS,
        "per_target_firm": per_firm,
        "per_product_family_slice": family_counts,
        "lookup_api_calls": lookup_seen,
        "records_with_udi_di": sum(1 for r in records if r.identifiers),
        "records_with_source_public_at": sum(1 for r in records if r.source_public_at),
        "selection_rule": (
            "Within the October 2026 GUDID monthly release (21 daily deltas, ~40k device "
            "records), keep every record whose companyName matches one of the five target "
            "firms (cap 70 records/firm) and every record whose brand or description "
            "matches a product-family keyword (monitoring / respiratory support / imaging / "
            "life support / neonatal), total cap 320."
        ),
        "coverage_limit": (
            "This is a one-month delta of GUDID changes, not the full GUDID universe "
            "(which is published as a ~multi-hundred-MB full release, outside this budget). "
            "Row counts here are a sample, never a coverage statement."
        ),
    }
    write_json(SOURCE_ID, "COUNTS.json", counts)
    write_provenance(SOURCE_ID, prov + lookup_prov, extra={
        "generated_at": utc_now(),
        "counts_file": f"DATASETS/regulatory/{SOURCE_ID}/COUNTS.json",
        "note": "Release archives saved verbatim; unzipped only in memory for parsing.",
    })
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


