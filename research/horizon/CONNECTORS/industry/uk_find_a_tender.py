"""UK Find a Tender — OCDS release packages, award stage.

Verified facts about this API (all measured, see PROVENANCE.json):

* keyless, JSON, OCDS 1.1 release packages;
* award-stage releases **do** carry ``awards[].suppliers[].name`` (and an OCDS
  party ``id`` such as ``GB-FTS-8557``), so the previous "no suppliers" concern
  does not apply here;
* the API accepts **exactly** ``stages, limit, cursor, updatedFrom, updatedTo``
  — there is no CPV or keyword filter (HTTP 400 "Request parameter 'keyword' is
  not recognised, allowed parameters are: ..."). Medical awards therefore have
  to be found by **scanning** award-stage releases, which is why this collection
  is explicitly a *sample*, with the sampled denominator reported.

There is no award date in ``awards[]``: ``release.date`` is the *publication*
date, so it is used as ``source_public_at``, and ``event_at`` comes only from a
contract ``dateSigned`` if the release exposes one.

Run
---
    python CONNECTORS/industry/uk_find_a_tender.py
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
    make_client, save_fetch, write_provenance, write_json, write_records, utc_now,
)

from hz.schema import build_record  # noqa: E402

SOURCE_ID = "uk_find_a_tender"
BASE = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"

#: Three pages of 100 award-stage releases = the bounded sample.
PAGES = 3
PAGE_SIZE = 100

#: CPV prefixes that identify medical devices/equipment in UK notices.
MEDICAL_CPV_PREFIXES = ("331", "336", "339", "337")

DEVICE_TERMS = [
    "ventilator", "mri", "magnetic resonance", "ultrasound", "sonograph",
    "infusion pump", "ct scanner", "computed tomography", "defibrillator",
    "patient monitor", "dialysis", "x-ray", "radiograph", "endoscope",
    "catheter", "stent", "pacemaker", "insulin pump", "syringe pump",
    "analyzer", "electrosurgical", "mammograph", "linear accelerator",
    "surgical robot", "ecg", "electrocardiograph", "prosthe", "implant",
    "wheelchair", "hospital bed", "sterilis", "centrifuge", "incubator",
]

#: The OCDS package itself declares its licence; the observed value is recorded
#: in PROVENANCE.json and quoted here after collection.
LICENCE_STATUS = "open_licence"
LICENCE_NOTE = (
    "The OCDS release package declares its own licence in its `license` field: "
    "`http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/` "
    "(read verbatim from the package fetched 2026-11-10 and stored in "
    "DATASETS/industry/uk_find_a_tender/raw/award_packages_p1.json). UK "
    "public-sector information is re-usable under the Open Government Licence v3.0."
)


def _cpv_from_release(rel: dict) -> list[str]:
    codes: list[str] = []
    tender = rel.get("tender") or {}
    for item in tender.get("items") or []:
        cls = item.get("classification") or {}
        for key in ("id", "description"):
            pass
        if cls.get("id"):
            codes.append(str(cls["id"]))
        for add in item.get("additionalClassifications") or []:
            if add.get("id"):
                codes.append(str(add["id"]))
    cls = tender.get("classification") or {}
    if cls.get("id"):
        codes.append(str(cls["id"]))
    for lot in tender.get("lots") or []:
        lc = lot.get("classification") or {}
        if lc.get("id"):
            codes.append(str(lc["id"]))
    return sorted(set(codes))


def _is_medical(codes: list[str]) -> bool:
    return any(c.startswith(MEDICAL_CPV_PREFIXES) for c in codes)


def _device_signals(text: str) -> dict:
    low = (text or "").lower()
    hits = sorted({t for t in DEVICE_TERMS if t in low})
    return {"device_terms_found": hits, "names_concrete_device": bool(hits)}


def _party_index(rel: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in rel.get("parties") or []:
        if p.get("id"):
            out[str(p["id"])] = p
    return out


def collect() -> dict:
    prov: list[dict] = []
    records: list = []
    stats = {"requests": 0, "releases_scanned": 0, "medical_releases": 0,
             "awards_total": 0, "medical_awards": 0, "awards_with_supplier": 0,
             "medical_awards_with_supplier": 0, "device_named": 0,
             "parties_with_legal_identifier": 0}
    licence_field = None
    cursor: str | None = None

    with make_client("industry_uk_find_a_tender", max_requests=8,
                     max_total_bytes=14_000_000) as client:
        for page in range(1, PAGES + 1):
            params = [f"stages=award", f"limit={PAGE_SIZE}"]
            if cursor:
                params.append(f"cursor={cursor}")
            url = BASE + "?" + "&".join(params)
            res = client.get(url)
            stats["requests"] += 1
            prov.append(save_fetch(SOURCE_ID, f"award_packages_p{page}.json", res,
                                  note=f"award-stage OCDS page {page}"))
            if not res.ok:
                break
            doc = res.json()
            if licence_field is None:
                licence_field = {
                    "license": doc.get("license"),
                    "publicationPolicy": doc.get("publicationPolicy"),
                    "publisher": doc.get("publisher"),
                    "uri": doc.get("uri"),
                }
            releases = doc.get("releases") or []
            for rel in releases:
                stats["releases_scanned"] += 1
                codes = _cpv_from_release(rel)
                medical = _is_medical(codes)
                if medical:
                    stats["medical_releases"] += 1
                parties = _party_index(rel)

                for award in rel.get("awards") or []:
                    stats["awards_total"] += 1
                    suppliers = award.get("suppliers") or []
                    if suppliers:
                        stats["awards_with_supplier"] += 1
                    if medical:
                        stats["medical_awards"] += 1
                        if suppliers:
                            stats["medical_awards_with_supplier"] += 1
                    if not medical or not suppliers:
                        continue

                    tender = rel.get("tender") or {}
                    value = (award.get("value") or {})
                    contracts = rel.get("contracts") or []
                    signed = None
                    for c in contracts:
                        if c.get("dateSigned"):
                            signed = str(c["dateSigned"])[:10]
                            break
                    release_date = str(rel.get("date") or "")
                    pub = release_date[:10] if release_date else None
                    desc_text = " ".join([
                        str(tender.get("title") or ""),
                        str(tender.get("description") or ""),
                        str(award.get("description") or ""),
                        str(award.get("title") or ""),
                    ])
                    sig = _device_signals(desc_text)
                    if sig["names_concrete_device"]:
                        stats["device_named"] += 1

                    for sidx, sup in enumerate(suppliers):
                        pid = str(sup.get("id") or "")
                        party = parties.get(pid) or {}
                        ident = party.get("identifier") or {}
                        legal_id = ident.get("id") or ident.get("scheme")
                        if legal_id:
                            stats["parties_with_legal_identifier"] += 1
                        name = str(sup.get("name") or party.get("name") or "").strip()
                        if not name:
                            continue
                        identifiers = [
                            {"scheme": "ocds_ocid", "value": str(rel.get("ocid")),
                             "issuing_authority": "UK Find a Tender (OCDS)"},
                        ]
                        if pid:
                            identifiers.append({
                                "scheme": "ocds_party_id", "value": pid,
                                "issuing_authority": "UK Find a Tender (OCDS)",
                            })
                        flags = []
                        if not pub:
                            flags.append("MISSING_PUBLICATION_DATE")
                        if not signed:
                            flags.append("MISSING_FILING_DATE")
                        rec = build_record(
                            source_id=SOURCE_ID,
                            source_record_id=(
                                f"fts:{rel.get('ocid')}:{award.get('id')}:{sidx}"
                            ),
                            entity_type="procurement_award",
                            original_name=(
                                f"{name} — supplier on UK FTS award "
                                f"{award.get('id')} ({tender.get('title') or rel.get('ocid')})"
                            ),
                            identifiers=identifiers,
                            manufacturer=None,
                            attributes={
                                "stage": "contract_award",
                                "stage_basis": (
                                    "OCDS release tag contains 'award'/'contract'; "
                                    "this is an award notice, not a tender, a "
                                    "delivery or revenue"
                                ),
                                "ocid": rel.get("ocid"),
                                "release_id": rel.get("id"),
                                "release_tags": rel.get("tag"),
                                "award_id": award.get("id"),
                                "award_status": award.get("status"),
                                "supplier_name": name,
                                "supplier_party_id": pid or None,
                                "supplier_all_suppliers_in_award": [
                                    s.get("name") for s in suppliers if s.get("name")
                                ],
                                "supplier_legal_identifier": legal_id,
                                "supplier_legal_identifier_scheme": ident.get("scheme"),
                                "supplier_country": (party.get("address") or {}).get(
                                    "countryName"),
                                "identity_basis": (
                                    "OCDS supplier name plus OCDS party id; a "
                                    "national company number is present only when "
                                    "the buyer published one"
                                ),
                                "buyer_name": (rel.get("buyer") or {}).get("name"),
                                "tender_title": tender.get("title"),
                                "tender_description": tender.get("description"),
                                "cpv_codes": codes,
                                "cpv_scope_note": (
                                    "CPV describes what was bought, not who made it"
                                ),
                                "award_value": value.get("amount"),
                                "award_currency": value.get("currency"),
                                "value_semantics": (
                                    "award/lot value as published, not a per-device price"
                                ),
                                "publication_date": pub,
                                "contract_date_signed": signed,
                                "event_at_semantics": (
                                    "contracts[].dateSigned when published; "
                                    "release.date is the publication date and is "
                                    "used only as source_public_at"
                                ),
                                "names_concrete_device": sig["names_concrete_device"],
                                "device_terms_found": sig["device_terms_found"],
                                "device_manufacturer_identified": False,
                                "device_relation_status": (
                                    "CANDIDATE" if sig["names_concrete_device"] else "NONE"
                                ),
                            },
                            event_at=signed,
                            source_public_at=pub,
                            first_observed_at=utc_now(),
                            fetched_at=utc_now(),
                            source_url=str(rel.get("id") and (
                                "https://www.find-tender.service.gov.uk/"
                                f"Notice/{rel.get('id')}") or BASE),
                            licence_status=LICENCE_STATUS,
                            licence_note=LICENCE_NOTE,
                            identity_status="CONFIRMED" if legal_id else "CANDIDATE",
                            evidence_status="CONFIRMED",
                            quality_flags=flags,
                            notes=(
                                "Sampled award release: UK FTS API has no CPV filter, "
                                "so medical awards were found by scanning."
                            ),
                        )
                        records.append(rec)

            cursor = (doc.get("links") or {}).get("next")
            if not cursor:
                break

        budget = client.budget_report()

    write_provenance(SOURCE_ID, prov, extra={
        "licence_status": LICENCE_STATUS,
        "licence_note": LICENCE_NOTE,
        "ocds_package_licence_field": licence_field,
        "api_parameter_allowlist": ["stages", "limit", "cursor", "updatedFrom",
                                    "updatedTo"],
        "medical_cpv_prefixes": list(MEDICAL_CPV_PREFIXES),
        "budget": {k: v for k, v in budget.items() if k != "errors"},
        "sampling": {
            "pages_fetched": stats["requests"],
            "releases_scanned": stats["releases_scanned"],
            "medical_releases": stats["medical_releases"],
            "awards_total_in_sample": stats["awards_total"],
            "medical_awards_in_sample": stats["medical_awards"],
        },
        "coverage_limits": [
            "This is a SCAN of award-stage releases, not a census: the API offers "
            "no CPV or keyword filter, so the medical share of the sampled window "
            "is the only statistic that generalises.",
            "The sample window is 'the most recent award-stage releases', not a "
            "fixed calendar period.",
            "CPV is a procurement vocabulary; it identifies what was bought, not "
            "the manufacturer.",
            "No award date exists in awards[]; contract dateSigned is used when "
            "present, otherwise event_at is null.",
        ],
    })
    write_json(SOURCE_ID, "summary.json", {
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "records": len(records),
        "requests": stats["requests"],
        "releases_scanned": stats["releases_scanned"],
        "medical_releases": stats["medical_releases"],
        "awards_scanned": stats["awards_total"],
        "medical_awards": stats["medical_awards"],
        "medical_awards_with_named_supplier": stats["medical_awards_with_supplier"],
        "awards_naming_a_device": stats["device_named"],
        "suppliers_with_legal_identifier": stats["parties_with_legal_identifier"],
        "ocds_licence": (licence_field or {}).get("license"),
    })
    path = write_records(SOURCE_ID, records)
    print(f"uk_find_a_tender: {len(records)} supplier rows; scanned "
          f"{stats['releases_scanned']} releases, {stats['medical_awards']} "
          f"medical awards -> {path}")
    return {"records": len(records), "releases_scanned": stats["releases_scanned"]}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
