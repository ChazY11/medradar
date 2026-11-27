"""Eurostat Comext — EU medical-device HS trade aggregates (DS-045409).

Why Comext and not only Comtrade
--------------------------------
Comtrade's keyless preview returned nothing at all for France (reporter code
250) across 2015-2024, and EU reporters are inconsistent about how they submit
HS detail. Comext is the *EU's own* compilation of the same customs
declarations, so it is both a second measurement and a coverage repair.

Dataset: DS-045409 "EU trade since 1988 by HS2-4-6 and CN8", annual, partner =
All countries of the world, indicators VALUE_IN_EUROS / QUANTITY_IN_100KG.

One request per reporter covers 5 HS4 codes x 2 flows x 10 years via repeated
``product=``/``flow=`` parameters plus ``sinceTimePeriod``/``untilTimePeriod``
(verified: comma lists are rejected with HTTP 400 "Invalid value for 'time'").

A value here is again a country aggregate. No firm is identified.

Run
---
    python CONNECTORS/industry/eurostat_comext.py
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

SOURCE_ID = "eurostat_comext"
BASE = ("https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/"
        "DS-045409")

# Seven EU reporters incl. the four largest traders, plus the EU aggregate so the
# sum can be cross-checked against the parts.
REPORTERS = ["DE", "FR", "IT", "ES", "NL", "PL", "SE", "EU"]
HS_CODES = ["9018", "9019", "9020", "9021", "9022"]
FLOWS = ["1", "2"]           # 1=IMPORT, 2=EXPORT (Comext codes)
YEARS = list(range(2015, 2025))
INDICATORS = ["VALUE_IN_EUROS", "QUANTITY_IN_100KG"]

LICENCE_STATUS = "open_licence"
LICENCE_NOTE = (
    "Eurostat copyright notice: 'Reuse of statistical data, metadata, "
    "publications, and other dissemination tools published on this website for "
    "commercial or non-commercial purposes is authorised provided the source is "
    "acknowledged.' (https://ec.europa.eu/eurostat/help/copyright-notice, "
    "Commission Decision of 12 December 2011 on the reuse of Commission "
    "documents)."
)

HS_SCOPE_NOTE = {
    "9018": ("Medical/surgical/dental/veterinary instruments incl. scintigraphic "
             "and electro-medical apparatus; also sweeps in dental chairs, "
             "veterinary and non-corrective ophthalmic instruments."),
    "9019": ("Oxygen therapy, artificial respiration and other breathing "
             "apparatus; also massage and psychological aptitude-testing "
             "apparatus, plus consumer ozone/aerosol therapy devices."),
    "9020": ("Other breathing appliances and gas masks without mechanical parts "
             "or replaceable filters; narrow, and excludes the ventilators in 9019."),
    "9021": ("Orthopaedic appliances, splints, artificial parts of the body, "
             "hearing aids; includes prosthetics, orthotics and hearing aids, "
             "which are devices but a different commercial category."),
    "9022": ("X-ray and alpha/beta/gamma apparatus incl. radiography and "
             "radiotherapy; also industrial/security radiography and "
             "non-destructive-testing equipment."),
}


def _jsonstat_values(doc: dict) -> list[dict]:
    """Decode a JSON-stat 2.0 dataset into flat row dicts.

    JSON-stat flattens with the *last* dimension varying fastest; the ``value``
    object is keyed by that flat index as a decimal string.
    """
    ids = doc.get("id") or []
    size = doc.get("size") or []
    if not ids or not size:
        return []
    cats: dict[str, list[str]] = {}
    labels: dict[str, dict[str, str]] = {}
    for d in ids:
        block = (doc.get("dimension") or {}).get(d) or {}
        index = (block.get("category") or {}).get("index") or {}
        if isinstance(index, dict):
            ordered = sorted(index.items(), key=lambda kv: kv[1])
            cats[d] = [k for k, _ in ordered]
        else:                      # list form
            cats[d] = list(index)
        labels[d] = (block.get("category") or {}).get("label") or {}

    strides = [1] * len(ids)
    for i in range(len(ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * size[i + 1]

    out: list[dict] = []
    for k, v in (doc.get("value") or {}).items():
        try:
            flat = int(k)
        except ValueError:
            continue
        if v is None:
            continue
        row: dict[str, object] = {"value": v}
        rem = flat
        for i, d in enumerate(ids):
            pos = rem // strides[i]
            rem = rem % strides[i]
            if pos < len(cats[d]):
                row[d] = cats[d][pos]
                row[d + "_label"] = labels[d].get(cats[d][pos])
        out.append(row)
    return out


def collect() -> dict:
    prov: list[dict] = []
    records: list = []
    stats = {"requests": 0, "raw_values": 0, "rejected": 0,
             "reporters_with_data": set(), "codes_with_data": set()}

    with make_client("industry_eurostat_comext", max_requests=16,
                     max_total_bytes=10_000_000) as client:
        for reporter in REPORTERS:
            params: list[tuple[str, object]] = [
                ("format", "JSON"), ("lang", "EN"), ("freq", "A"),
                ("reporter", reporter), ("partner", "WORLD"),
            ]
            for p in HS_CODES:
                params.append(("product", p))
            for f in FLOWS:
                params.append(("flow", f))
            params.append(("sinceTimePeriod", YEARS[0]))
            params.append(("untilTimePeriod", YEARS[-1]))

            url = BASE + "?" + "&".join(f"{k}={v}" for k, v in params)
            res = client.get(url)
            stats["requests"] += 1
            prov.append(save_fetch(SOURCE_ID, f"ds045409_{reporter}.json", res,
                                  note=f"DS-045409 annual, reporter={reporter}"))
            if not res.ok:
                stats["rejected"] += 1
                continue
            doc = res.json()
            dataset_updated = doc.get("updated")
            for row in _jsonstat_values(doc):
                ind = row.get("indicators")
                if ind not in INDICATORS:
                    continue
                product = str(row.get("product") or "")
                if product not in HS_CODES:
                    continue
                flow = str(row.get("flow") or "")
                period = str(row.get("time") or "")
                if not period.isdigit():
                    continue
                if ind == "QUANTITY_IN_100KG":
                    # attach to the value already emitted for this cell later
                    pass
                stats["raw_values"] += 1
                stats["reporters_with_data"].add(reporter)
                stats["codes_with_data"].add(product)

                key_attrs = {
                    "reporter_code": reporter,
                    "reporter_name": row.get("reporter_label"),
                    "partner_code": "WORLD",
                    "partner_name": row.get("partner_label"),
                    "hs_code": product,
                    "hs_description": row.get("product_label"),
                    "hs_scope_note": HS_SCOPE_NOTE.get(product),
                    "flow_code": flow,
                    "flow_name": row.get("flow_label"),
                    "period": period,
                    "precision": "annual",
                    "indicator": ind,
                    "value": row.get("value"),
                    "unit": "EUR" if ind == "VALUE_IN_EUROS" else "100 kg",
                    "dataset_code": "DS-045409",
                    "dataset_label": doc.get("label"),
                    "dataset_updated": dataset_updated,
                    "aggregation_semantics": (
                        "national aggregate of EU customs declarations; not "
                        "revenue, not R&D, not firm activity"
                    ),
                    "firm_attribution": "none",
                }
                rec = build_record(
                    source_id=SOURCE_ID,
                    source_record_id=(
                        f"comext:DS-045409:{reporter}:WORLD:{product}:{flow}:"
                        f"{period}:{ind}"
                    ),
                    entity_type="trade_flow",
                    original_name=(
                        f"{row.get('reporter_label') or reporter} "
                        f"{str(row.get('flow_label') or flow).lower()} of HS "
                        f"{product}, {period} ({ind})"
                    ),
                    identifiers=[
                        {"scheme": "hs_code", "value": product,
                         "issuing_authority": "World Customs Organization",
                         "scope": "H6"},
                        {"scheme": "eurostat_comext_cell",
                         "value": f"DS-045409:{reporter}:WORLD:{product}:{flow}:{period}:{ind}",
                         "issuing_authority": "Eurostat"},
                    ],
                    manufacturer=None,
                    attributes=key_attrs,
                    event_at=f"{period}-12-31",
                    source_public_at=None,
                    first_observed_at=utc_now(),
                    fetched_at=utc_now(),
                    source_url=res.final_url,
                    licence_status=LICENCE_STATUS,
                    licence_note=LICENCE_NOTE,
                    identity_status="UNKNOWN",
                    evidence_status="CANDIDATE",
                    quality_flags=["MISSING_PUBLICATION_DATE"],
                    notes=(
                        "Comext discloses only a dataset-level 'updated' "
                        "timestamp, not a per-observation release date; the "
                        "observation therefore cannot be placed on the "
                        "observability timeline."
                    ),
                )
                records.append(rec)

        budget = client.budget_report()

    write_provenance(SOURCE_ID, prov, extra={
        "licence_status": LICENCE_STATUS,
        "licence_note": LICENCE_NOTE,
        "dataset_code": "DS-045409",
        "dataset_label": "EU trade since 1988 by HS2-4-6 and CN8",
        "hs_codes": HS_CODES,
        "hs_scope_notes": HS_SCOPE_NOTE,
        "reporters": REPORTERS,
        "indicator_notes": {
            "VALUE_IN_EUROS": "statistical value in euro",
            "QUANTITY_IN_100KG": "net mass in 100 kg (not comparable across codes)",
        },
        "budget": {k: v for k, v in budget.items() if k != "errors"},
        "coverage_limits": [
            "Only partner=WORLD; no bilateral Comext flows were fetched.",
            "Only five HS4 headings; CN8 detail exists but was deliberately not "
            "downloaded (budget + aggregation would be finer than the study needs).",
            "Comext and Comtrade are separate compilations of the same customs "
            "declarations and will not agree exactly (different revision policy, "
            "different EU/non-EU treatment after Brexit).",
            "Values are NOT deflated; no exchange-rate conversion was applied.",
        ],
    })
    write_json(SOURCE_ID, "summary.json", {
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "records": len(records),
        "value_rows": sum(1 for r in records if r.attributes.get("indicator") == "VALUE_IN_EUROS"),
        "mass_rows": sum(1 for r in records if r.attributes.get("indicator") == "QUANTITY_IN_100KG"),
        "requests": stats["requests"],
        "reporters_with_data": sorted(stats["reporters_with_data"]),
        "reporters_requested": REPORTERS,
        "codes_with_data": sorted(stats["codes_with_data"]),
    })
    path = write_records(SOURCE_ID, records)
    print(f"eurostat_comext: {len(records)} records, {stats['requests']} requests -> {path}")
    return {"records": len(records), "requests": stats["requests"]}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
