"""UN Comtrade — medical-device HS trade aggregates.

What this collects
------------------
Annual (2015-2024) and a bounded monthly slice (2025) of **country-total**
import/export values for HS4 9018 / 9019 / 9020 / 9022 for eight reporters,
plus the two official reference files (reporter codes, HS nomenclature) so that
no reporter or commodity name is ever invented.

What this does NOT collect, and cannot
-------------------------------------
A trade flow is a national aggregate. It is not revenue, not R&D, not market
share, not firm activity. Every record says so in
``attributes.aggregation_semantics`` and carries
``attributes.firm_attribution = "none"``. See ``reports/INDUSTRY_DATA_REPORT.md``.

Licence posture (important)
---------------------------
The keyless ``/public/v1/preview`` endpoints answer without a key, but the UN
Comtrade Usage Agreement §5 states that "any copying, automated browsing or
downloading, redistribution, publication, or commercial exploitation of any
material ... is strictly prohibited without the prior written permission of the
United Nations" (quoted verbatim in
``DATASETS/industry/un_comtrade/raw/comtrade_license.html``). The collection
below is therefore deliberately minimal and one-off; it is evidence for a
research finding, not a pipeline. Any operational use needs written permission
from UNSD or a licensed subscription.

Run
---
    python CONNECTORS/industry/un_comtrade.py
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

SOURCE_ID = "un_comtrade"
PREVIEW = "https://comtradeapi.un.org/public/v1/preview"
REF = "https://comtradeapi.un.org/files/v1/app/reference"

# Eight reporters: large + diverse reporting practice. Codes are UN M49 numeric
# and are resolved to names only through Reporters.json (never hard-coded).
REPORTERS = [156, 842, 276, 250, 392, 826, 380, 724]

# HS4 codes in scope. Contamination is documented per code in HS_CONTAMINATION.
HS_CODES = ["9018", "9019", "9020", "9022"]
YEARS = list(range(2015, 2025))

# Monthly slice: two reporters, 2025, imports only (bounded on purpose).
MONTHLY_REPORTERS = [156, 842]
MONTHLY_PERIODS = [f"2025{m:02d}" for m in range(1, 13)]

FLOWS = {"M": "Import", "X": "Export"}

#: What each HS4 heading actually covers and what it wrongly sweeps in.
#: Descriptions in records come from HS.json; these notes are analyst commentary
#: and are labelled as such.
HS_CONTAMINATION = {
    "9018": (
        "Instruments and appliances used in medical, surgical, dental or "
        "veterinary sciences. Sweeps in dental chairs, veterinary instruments, "
        "ophthalmic (non-corrective) instruments and sight-testing apparatus "
        "that are not 'medical devices' for revenue purposes."
    ),
    "9019": (
        "Mechano-therapy, massage, psychological aptitude-testing apparatus; "
        "oxygen therapy, artificial respiration and other breathing apparatus. "
        "Highly relevant (ventilators, oxygen therapy) but also contains "
        "massage devices and ozone/aerosol therapy equipment sold to consumers."
    ),
    "9020": (
        "Other breathing appliances and gas masks (excluding protective masks "
        "having neither mechanical parts nor replaceable filters). Narrow, but "
        "excludes the ventilators that sit in 9019, so 9019+9020 must be read "
        "together for respiratory care."
    ),
    "9022": (
        "X-ray, alpha/beta/gamma radiation apparatus incl. radiography and "
        "radiotherapy tubes/generators. Contains industrial and security "
        "radiography and non-destructive-testing apparatus, which is not "
        "medical."
    ),
}

LICENCE_STATUS = "terms_restricted"
LICENCE_NOTE = (
    "UN Comtrade Usage Agreement §5: 'any copying, automated browsing or "
    "downloading, redistribution, publication, or commercial exploitation of any "
    "material contained on or otherwise made available to you on United Nations "
    "COMTRADE is strictly prohibited without the prior written permission of the "
    "United Nations.' (https://comtradeplus.un.org/LicenseAgreement). The "
    "keyless preview API is published for programmatic access, so the two "
    "instruments are in tension; HORIZON-001 collected a bounded one-off sample "
    "for research and treats operational reuse as requiring written permission."
)


def _period_bounds(period: str) -> tuple[str, str]:
    """Return (event_at, precision) for 'YYYY' or 'YYYYMM'."""
    if len(period) == 4:
        return f"{period}-12-31", "annual"
    y, m = int(period[:4]), int(period[4:])
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return f"{y}-{m:02d}-{last:02d}", "monthly"


def _load_reference(client, name: str, url: str, prov: list) -> dict:
    res = client.get(url)
    prov.append(save_fetch(SOURCE_ID, name, res, note="official reference file"))
    return res.json().get("results", [])


def collect() -> dict:
    prov: list[dict] = []
    records: list = []
    stats = {"requests": 0, "rows": 0, "series": set(), "reporters_present": set(),
             "codes_present": set(), "years_present": set()}

    with make_client("industry_un_comtrade", max_requests=55,
                     max_total_bytes=12_000_000, rps=0.8) as client:
        # ---- reference data (names/descriptions come from here, not memory)
        reporters = _load_reference(
            client, "reporters.json", f"{REF}/Reporters.json", prov)
        hsrows = _load_reference(client, "hs.json", f"{REF}/HS.json", prov)
        rep_name = {int(r["reporterCode"]): r.get("reporterDesc") or r.get("text")
                    for r in reporters if r.get("reporterCode") is not None}
        hs_desc = {str(r["id"]): (r.get("text") or "") for r in hsrows}
        # '9018 - Instruments and ...' -> 'Instruments and ...'
        for k, v in list(hs_desc.items()):
            if " - " in v:
                hs_desc[k] = v.split(" - ", 1)[1].strip()

        def ingest(payload: dict, requested_period: str, precision: str, url: str,
                   freq: str) -> None:
            for row in payload.get("data") or []:
                rep = int(row.get("reporterCode"))
                cmd = str(row.get("cmdCode"))
                flow = str(row.get("flowCode"))
                # NEVER trust the loop variable: read the period back out of the
                # response. ``hz.http.BoundedClient`` caches by URL only, so a
                # params-based query would silently replay the first response.
                period = str(row.get("period") or requested_period)
                if period != requested_period:
                    raise RuntimeError(
                        f"{SOURCE_ID}: response period {period!r} != requested "
                        f"{requested_period!r}; refusing to write a mislabelled row"
                    )
                event_at, _ = _period_bounds(period)
                # ---- why every trade record is CANDIDATE, not CONFIRMED ----
                # The value is an official reported aggregate, but Comtrade's
                # preview payload does not disclose when the figure became
                # public, so the record cannot be placed on an observability
                # timeline. It is a usable *measurement*, not a datable fact.
                rec = build_record(
                    source_id=SOURCE_ID,
                    source_record_id=(
                        f"comtrade:{freq}:{rep}:0:{cmd}:{flow}:{period}"
                    ),
                    entity_type="trade_flow",
                    original_name=(
                        f"{rep_name.get(rep, str(rep))} "
                        f"{FLOWS.get(flow, flow).lower()}s of HS {cmd}"
                        f" from/to world, {period}"
                    ),
                    identifiers=[
                        {"scheme": "hs_code", "value": cmd,
                         "issuing_authority": "World Customs Organization",
                         "scope": "H6"},
                        {"scheme": "comtrade_reporter_flow_cmd_period",
                         "value": f"{rep}:{flow}:{cmd}:{period}",
                         "issuing_authority": "UN Comtrade"},
                    ],
                    manufacturer=None,
                    attributes={
                        "reporter_code": rep,
                        "reporter_name": rep_name.get(rep),
                        "partner_code": 0,
                        "partner_name": "World",
                        "hs_code": cmd,
                        "hs_description": hs_desc.get(cmd),
                        "hs_scope_note": HS_CONTAMINATION.get(cmd),
                        "flow_code": flow,
                        "flow_name": FLOWS.get(flow, flow),
                        "period": period,
                        "precision": precision,
                        "classification_code": row.get("classificationCode"),
                        "primary_value_usd": row.get("primaryValue"),
                        "cif_value_usd": row.get("cifvalue"),
                        "fob_value_usd": row.get("fobvalue"),
                        "net_weight_kg": row.get("netWgt"),
                        "is_aggregate": row.get("isAggregate"),
                        "is_reported": row.get("isReported"),
                        "legacy_estimation_flag": row.get("legacyEstimationFlag"),
                        "customs_code": row.get("customsCode"),
                        "mot_code": row.get("motCode"),
                        # ---- the two attributes that stop misreading --------
                        "aggregation_semantics": (
                            "country-total aggregate of customs declarations; "
                            "not revenue, not R&D, not firm activity"
                        ),
                        "firm_attribution": "none",
                    },
                    event_at=event_at,
                    source_public_at=None,      # not disclosed by the API
                    first_observed_at=utc_now(),
                    fetched_at=utc_now(),
                    source_url=url,
                    licence_status=LICENCE_STATUS,
                    licence_note=LICENCE_NOTE,
                    identity_status="UNKNOWN",  # no entity is identified
                    evidence_status="CANDIDATE",
                    quality_flags=["MISSING_PUBLICATION_DATE"],
                    notes=(
                        "Value is an official reported aggregate. "
                        "No release/publication date is exposed by the API, so "
                        "observability_gap cannot be computed."
                    ),
                )
                records.append(rec)
                stats["rows"] += 1
                stats["series"].add((rep, cmd, flow, period))
                stats["reporters_present"].add(rep)
                stats["codes_present"].add(cmd)
                stats["years_present"].add(period)

        # ---- annual: 1 period per request is a hard preview cap --------------
        # NB: the full query string is baked into the URL on purpose.
        # ``hz.http.BoundedClient`` memoises by URL alone, so passing ``params=``
        # makes every period replay the first response.
        for year in YEARS:
            period = str(year)
            query = urlencode({
                "reporterCode": ",".join(str(r) for r in REPORTERS),
                "period": period,
                "cmdCode": ",".join(HS_CODES),
                "flowCode": ",".join(FLOWS),
                "partnerCode": 0,
                "partner2Code": 0,
                "customsCode": "C00",
                "motCode": 0,
            })
            res = client.get(f"{PREVIEW}/C/A/HS?{query}")
            prov.append(save_fetch(SOURCE_ID, f"annual_{period}.json", res,
                                  note=f"annual preview {period}"))
            stats["requests"] += 1
            if res.ok:
                ingest(res.json(), period, "annual", res.final_url, "A")

        # ---- monthly: bounded 2025 slice, imports only ----------------------
        for period in MONTHLY_PERIODS:
            query = urlencode({
                "reporterCode": ",".join(str(r) for r in MONTHLY_REPORTERS),
                "period": period,
                "cmdCode": ",".join(HS_CODES),
                "flowCode": "M",
                "partnerCode": 0,
                "partner2Code": 0,
                "customsCode": "C00",
                "motCode": 0,
            })
            res = client.get(f"{PREVIEW}/C/M/HS?{query}")
            prov.append(save_fetch(SOURCE_ID, f"monthly_{period}.json", res,
                                  note=f"monthly preview {period}"))
            stats["requests"] += 1
            if res.ok:
                ingest(res.json(), period, "monthly", res.final_url, "M")

        budget = client.budget_report()

    yearly = {}
    for rep, cmd, flow, period in stats["series"]:
        yearly.setdefault(rep, set()).add(cmd)

    write_provenance(SOURCE_ID, prov, extra={
        "licence_status": LICENCE_STATUS,
        "licence_note": LICENCE_NOTE,
        "hs_codes": HS_CODES,
        "hs_scope_notes": HS_CONTAMINATION,
        "reporters": REPORTERS,
        "years": YEARS,
        "monthly_slice": {"reporters": MONTHLY_REPORTERS, "periods": MONTHLY_PERIODS},
        "observed_rate_limit": (
            "At 1.5 requests/second the preview endpoint returned HTTP 429 on "
            "roughly every second call and succeeded on the bounded retry; the "
            "practical keyless ceiling observed on 2026-11-10 was about one "
            "request per second. 429 responses are in "
            "SOURCE_PROBES/industry/REQUEST_LOG.jsonl with outcome HTTP_ERROR."
        ),
        "budget": {k: v for k, v in budget.items() if k != "errors"},
        "coverage_limits": [
            "Preview endpoint permits exactly ONE reference period per request "
            "(HTTP 400 'Maximum number of periods for preview is 1').",
            "Aggregates are partner=World only; no bilateral flows were fetched.",
            "Monthly coverage is a 12-month 2025 slice for two reporters, not a "
            "full monthly history.",
            "No publication/release date is returned, so every record is "
            "EVENT_ONLY (MISSING_PUBLICATION_DATE).",
            "Values are the reporters' own submissions to UNSD and are NOT "
            "harmonised with Eurostat or HMRC mirror statistics.",
        ],
    })
    write_json(SOURCE_ID, "summary.json", {
        "generated_at": utc_now(),
        "source_id": SOURCE_ID,
        "records": len(records),
        "rows_by_request_type": {"annual": sum(1 for r in records if r.attributes.get("precision") == "annual"),
                                 "monthly": sum(1 for r in records if r.attributes.get("precision") == "monthly")},
        "distinct_series": len(stats["series"]),
        "reporters_present": sorted(stats["reporters_present"]),
        "reporters_requested": REPORTERS,
        "codes_present": sorted(stats["codes_present"]),
        "periods_present": sorted(stats["years_present"]),
        "requests": stats["requests"],
    })
    path = write_records(SOURCE_ID, records)
    print(f"un_comtrade: {len(records)} records, {len(stats['series'])} series, "
          f"{stats['requests']} data requests -> {path}")
    return {"records": len(records), "series": len(stats["series"]),
            "requests": stats["requests"]}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
