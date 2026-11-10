"""UK HMRC Trade Info — UK medical-device HS4 trade aggregates (OTS).

The interesting part is the *shape* of this API, because it is where a careless
analyst would quietly produce a wrong number:

* ``OTS`` is a **microcube**: commodity (CN8) x country x port x flow x month.
  There is **no** "world total" row, so a UK annual total has to be computed.
* imports and exports are split **EU vs non-EU** (FlowType 1/2/3/4), so an
  import total is flow 1 **plus** flow 3.
* the grain is CN8, so an HS4 total is the sum over the HS4's CN8 children —
  which are enumerated from HMRC's own ``Commodity`` table rather than assumed.

The API supports OData ``$apply=filter(...)/groupby(...)``, so server-side
aggregation returns exact totals in a few hundred bytes instead of ~10^5 rows.
That is a bounded-collection decision, and it is recorded in PROVENANCE.json.

Values are in GBP. No firm is identified.

Run
---
    python CONNECTORS/industry/uk_hmrc_trade.py
"""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlencode

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from _util import (  # noqa: E402
    make_client, save_fetch, write_provenance, write_json, write_records, utc_now,
)

from hz.schema import build_record  # noqa: E402

SOURCE_ID = "uk_hmrc_trade"
API = "https://api.uktradeinfo.com"

HS_CODES = ["9018", "9019", "9020", "9021", "9022"]
YEARS = list(range(2015, 2025))
MONTH_FROM = 201501
MONTH_TO = 202512

# FlowTypeId -> (label, direction). Verified from /FlowType.
FLOW_DIRECTION = {1: ("EU Imports", "imports"), 2: ("EU Exports", "exports"),
                  3: ("Non-EU Imports", "imports"), 4: ("Non-EU Exports", "exports")}

LICENCE_STATUS = "open_licence"
LICENCE_NOTE = (
    "uktradeinfo.com footer: 'All content is available under the Open Government "
    "Licence v3.0, except where otherwise stated' "
    "(https://www.uktradeinfo.com/, stored at "
    "DATASETS/industry/uk_hmrc_trade/raw/portal_home.html)."
)

HS_SCOPE_NOTE = {
    "9018": ("Medical/surgical/dental/veterinary instruments incl. scintigraphic "
             "and electro-medical apparatus; also dental chairs, veterinary and "
             "non-corrective ophthalmic instruments."),
    "9019": ("Oxygen therapy, artificial respiration and other breathing "
             "apparatus; also massage and psychological aptitude-testing "
             "apparatus."),
    "9020": ("Other breathing appliances and gas masks without mechanical parts "
             "or replaceable filters; excludes ventilators counted in 9019."),
    "9021": ("Orthopaedic appliances, splints, artificial body parts, hearing "
             "aids; prosthetics/orthotics/hearing aids are devices but a "
             "different commercial category."),
    "9022": ("X-ray and alpha/beta/gamma apparatus; also industrial/security "
             "radiography and non-destructive-testing equipment."),
}


def _hs4_children(client, hs4: str, prov: list) -> tuple[list[int], dict[int, dict]]:
    """Enumerate the CN8 children of one HS4 from HMRC's own Commodity table.

    The query string is baked into the URL rather than passed as ``params=``
    because ``hz.http.BoundedClient`` memoises on the URL alone — with
    ``params=`` every HS4 would replay the first HS4's response, which is
    exactly the silent-mislabel failure this project exists to avoid.
    """
    query = urlencode({"$filter": f"Hs4Code eq '{hs4}'"})
    res = client.get(f"{API}/Commodity?{query}")
    prov.append(save_fetch(SOURCE_ID, f"commodity_hs4_{hs4}.json", res,
                          note=f"CN8 children of HS4 {hs4}"))
    ids: list[int] = []
    meta: dict[int, dict] = {}
    if not res.ok:
        return ids, meta
    for row in res.json().get("value") or []:
        cid = row.get("CommodityId")
        if cid is None:
            continue
        # verify the server honoured the filter instead of assuming it did
        if str(row.get("Hs4Code")) != hs4:
            raise RuntimeError(
                f"{SOURCE_ID}: Commodity filter returned Hs4Code="
                f"{row.get('Hs4Code')!r} for a request for {hs4!r}"
            )
        ids.append(int(cid))
        meta[int(cid)] = row
    return ids, meta


def _ots_series(client, hs4: str, commodity_ids: list[int], prov: list):
    """One OData $apply call -> monthly totals per FlowTypeId."""
    ors = " or ".join(f"CommodityId eq {cid}" for cid in commodity_ids)
    apply_expr = (
        f"filter(({ors}) and MonthId ge {MONTH_FROM} and MonthId le {MONTH_TO})"
        "/groupby((MonthId,FlowTypeId),aggregate(Value with sum as TotalValue))"
    )
    query = urlencode({"$apply": apply_expr})
    res = client.get(f"{API}/OTS?{query}")
    prov.append(save_fetch(SOURCE_ID, f"ots_monthly_{hs4}.json", res,
                          note=f"OTS monthly totals for HS4 {hs4}"))
    if not res.ok:
        return []
    return res.json().get("value") or []


def collect() -> dict:
    prov: list[dict] = []
    records: list = []
    stats = {"requests": 0, "monthly_cells": 0, "hs4_children": {}}

    with make_client("industry_uk_hmrc_trade", max_requests=20,
                     max_total_bytes=12_000_000) as client:
        # flow names, quoted from source
        res = client.get(f"{API}/FlowType")
        stats["requests"] += 1
        prov.append(save_fetch(SOURCE_ID, "flowtype.json", res, note="flow code names"))
        flow_names = {}
        if res.ok:
            for row in res.json().get("value") or []:
                flow_names[int(row["FlowTypeId"])] = (row.get("FlowTypeDescription") or "").strip()

        for hs4 in HS_CODES:
            ids, meta = _hs4_children(client, hs4, prov)
            stats["requests"] += 1
            stats["hs4_children"][hs4] = {
                "cn8_ids": ids,
                "cn8_count": len(ids),
                "descriptions": {str(k): (v.get("Cn8LongDescription") or "").strip()
                                 for k, v in meta.items()},
                "hs4_description": next(
                    ((v.get("Hs4Description") or "").strip() for v in meta.values()
                     if v.get("Hs4Description")), None),
            }
            if not ids:
                continue
            rows = _ots_series(client, hs4, ids, prov)
            stats["requests"] += 1
            stats["monthly_cells"] += len(rows)

            # ---- roll months up to years, joining EU + non-EU flows ----------
            acc: dict[tuple[int, str], float] = {}
            months_seen: dict[tuple[int, str], set[int]] = {}
            for r in rows:
                month = int(r.get("MonthId") or 0)
                flow = int(r.get("FlowTypeId") or 0)
                value = r.get("TotalValue")
                if not month or value is None:
                    continue
                year, m = month // 100, month % 100
                direction = FLOW_DIRECTION.get(flow, (None, None))[1]
                if direction is None:
                    continue
                acc[(year, direction)] = acc.get((year, direction), 0.0) + float(value)
                months_seen.setdefault((year, direction), set()).add(m)

            for (year, direction), value in sorted(acc.items()):
                if year not in YEARS:
                    continue
                n_months = len(months_seen.get((year, direction), ()))
                flags = []
                if n_months < 12:
                    flags.append("PARTIAL_PAGE")
                rec = build_record(
                    source_id=SOURCE_ID,
                    source_record_id=f"hmrc_ots:{hs4}:{year}:{direction}",
                    entity_type="trade_flow",
                    original_name=(
                        f"United Kingdom {direction} of HS {hs4}, {year} "
                        f"(HMRC OTS, sum of CN8 children)"
                    ),
                    identifiers=[
                        {"scheme": "hs_code", "value": hs4,
                         "issuing_authority": "World Customs Organization",
                         "scope": "H6"},
                        {"scheme": "hmrc_ots_series",
                         "value": f"{hs4}:{year}:{direction}",
                         "issuing_authority": "HM Revenue & Customs"},
                    ],
                    manufacturer=None,
                    attributes={
                        "reporter_code": "GB",
                        "reporter_name": "United Kingdom",
                        "partner_code": "WORLD",
                        "partner_name": "World",
                        "hs_code": hs4,
                        "hs_description": stats["hs4_children"][hs4]["hs4_description"],
                        "hs_scope_note": HS_SCOPE_NOTE.get(hs4),
                        "direction": direction,
                        "flow_type_ids_summed": [
                            fid for fid, (_n, d) in FLOW_DIRECTION.items() if d == direction
                        ],
                        "period": str(year),
                        "precision": "annual (rolled up from monthly OTS cells)",
                        "value_gbp": round(value, 2),
                        "unit": "GBP",
                        "months_observed": n_months,
                        "months_in_period": 12,
                        "source_entity": "OTS",
                        "source_grain": "CN8 x country x port x flow x month",
                        "aggregation_semantics": (
                            "sum of HMRC Overseas Trade Statistics microcells; "
                            "not revenue, not R&D, not firm activity"
                        ),
                        "firm_attribution": "none",
                    },
                    event_at=f"{year}-12-31",
                    source_public_at=None,
                    first_observed_at=utc_now(),
                    fetched_at=utc_now(),
                    source_url=f"{API}/OTS",
                    licence_status=LICENCE_STATUS,
                    licence_note=LICENCE_NOTE,
                    identity_status="UNKNOWN",
                    evidence_status="CANDIDATE",
                    quality_flags=["MISSING_PUBLICATION_DATE"] + flags,
                    notes=(
                        "Value is computed by summing server-side aggregated OTS "
                        "cells; the API exposes no single 'UK total' row."
                    ),
                )
                records.append(rec)

        budget = client.budget_report()

    write_provenance(SOURCE_ID, prov, extra={
        "licence_status": LICENCE_STATUS,
        "licence_note": LICENCE_NOTE,
        "hs_codes": HS_CODES,
        "hs_scope_notes": HS_SCOPE_NOTE,
        "flow_type_direction_map": {str(k): {"label": v[0], "direction": v[1]}
                                    for k, v in FLOW_DIRECTION.items()},
        "hs4_children": stats["hs4_children"],
        "budget": {k: v for k, v in budget.items() if v != "errors"},
        "aggregation_method": (
            "Per HS4: one OData $apply=filter(...)/groupby((MonthId,FlowTypeId),"
            "aggregate(Value with sum as TotalValue)) call over all CN8 children of "
            "that HS4; then months are summed to years and EU + non-EU flows are "
            "added per direction. No row-level OTS dump was downloaded."
        ),
        "coverage_limits": [
            "OTS has no world-total row: the total is our sum, so it inherits any "
            "suppression in the underlying cells.",
            "Values are in GBP and are NOT deflated or converted.",
            "FlowType 1/2 are EU flows, 3/4 non-EU: an import total is 1+3 and an "
            "export total is 2+4. Reading flow 1 as 'imports' understates UK "
            "imports by the non-EU share.",
            "The UK left the EU customs union in 2021, so the EU/non-EU split is "
            "not stable across the 2015-2025 window.",
        ],
    })
    write_json(SOURCE_ID, "summary.json", {
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "records": len(records),
        "requests": stats["requests"],
        "monthly_cells_aggregated": stats["monthly_cells"],
        "hs4_cn8_child_counts": {k: v["cn8_count"] for k, v in stats["hs4_children"].items()},
    })
    path = write_records(SOURCE_ID, records)
    print(f"uk_hmrc_trade: {len(records)} records, {stats['requests']} requests -> {path}")
    return {"records": len(records), "requests": stats["requests"]}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
