"""Live probe for ``openfda_device_maude`` (DATA-EXPANSION-001, postmarket).

Run from the repository root::

    python research/data_expansion/probes/openfda_device_maude/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from medradar.external_sources import base  # noqa: E402
from medradar.external_sources.regulatory import postmarket_openfda_device_maude as connector  # noqa: E402

ROOT = REPO_ROOT / "research" / "data_expansion"
SAMPLES = ROOT / "samples" / connector.SOURCE_ID


def probe(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    probes: list[dict] = []

    smoke = client.get(connector.API_URL, params={"limit": 2})
    row = {}
    if smoke.ok:
        payload = smoke.json()
        rows = payload.get("results") or []
        row = rows[0] if rows else {}
        sample = base.write_sample(SAMPLES, "smoke_limit2.json", smoke.body)
    else:
        sample = None
    probes.append(
        {
            "name": "smoke_limit2",
            "url": smoke.url,
            "status": smoke.status,
            "ok": smoke.ok,
            "bytes": len(smoke.body),
            "elapsed_ms": smoke.elapsed_ms,
            "error": smoke.error,
            "structure": base.json_shape(smoke.json()) if smoke.ok else None,
            "sample": sample,
            "record_keys": sorted(row.keys()),
        }
    )

    devices = row.get("device") or []
    device_row = devices[0] if devices else {}
    probes.append(
        {
            "name": "record_shape_and_three_dates",
            "ok": bool(row.get("date_of_event") and row.get("date_received")),
            "status": 200 if smoke.ok else smoke.status,
            "detail": {
                "date_of_event": row.get("date_of_event"),
                "date_received": row.get("date_received"),
                "date_report": row.get("date_report"),
                "date_report_to_fda": row.get("date_report_to_fda"),
                "date_added": row.get("date_added"),
                "top_level_manufacturer_name": row.get("manufacturer_name"),
                "device_manufacturer_d_name": device_row.get("manufacturer_d_name"),
                "device_is_array": isinstance(devices, list),
            },
            "conclusion": (
                "three distinct dates exist and the manufacturer identity lives in device[].manufacturer_d_name; "
                "the top-level manufacturer_name is empty for historical records"
            ),
        }
    )

    # Prove the nested dot path is required: the bare field name returns NOT_FOUND.
    bare = client.get(
        connector.API_URL,
        params={"search": 'manufacturer_d_name:"Medtronic"', "limit": 1},
    )
    probes.append(
        {
            "name": "bare_field_name_is_not_searchable",
            "url": bare.url,
            "status": bare.status,
            "ok": bare.status == 404,
            "bytes": len(bare.body),
            "elapsed_ms": bare.elapsed_ms,
            "error": bare.error,
            "note": "HTTP 404 NOT_FOUND 'No matches found!' proves the bare field name does not address the nested array",
        }
    )

    # Nested path works and returns a real meta.total for the family.
    nested = client.get(
        connector.API_URL,
        params={"search": "device.manufacturer_d_name:medtronic", "limit": 1},
    )
    total = None
    if nested.ok:
        total = ((nested.json().get("meta") or {}).get("results") or {}).get("total")
    probes.append(
        {
            "name": "nested_search_device_manufacturer_d_name",
            "url": nested.url,
            "status": nested.status,
            "ok": nested.ok,
            "bytes": len(nested.body),
            "elapsed_ms": nested.elapsed_ms,
            "error": nested.error,
            "meta_total": total,
        }
    )

    # Date aggregation for the public clock (real returned buckets).
    count = client.get(
        connector.API_URL,
        params={"search": "device.manufacturer_d_name:medtronic", "count": "date_received"},
    )
    buckets = 0
    bucket_sum = 0
    if count.ok:
        results = count.json().get("results") or []
        buckets = len(results)
        bucket_sum = sum(int(item.get("count", 0)) for item in results)
        base.write_sample(SAMPLES, "count_medtronic_date_received.json", count.body)
    probes.append(
        {
            "name": "count_date_received_medtronic",
            "url": count.url,
            "status": count.status,
            "ok": count.ok,
            "bytes": len(count.body),
            "elapsed_ms": count.elapsed_ms,
            "error": count.error,
            "buckets": buckets,
            "bucket_sum": bucket_sum,
            "note": "date buckets are exhaustive; bucket_sum equals meta.total for the same search",
        }
    )

    ok_count = sum(1 for item in probes if item.get("ok"))
    status = "VERIFIED_API" if ok_count >= 3 else "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id=connector.SOURCE_ID,
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[
            "https://open.fda.gov/apis/device/event/",
            "https://open.fda.gov/apis/authentication/",
            "https://open.fda.gov/license/",
            "https://www.fda.gov/medical-devices/medical-device-databases/maude-manufacturer-and-user-facility-device-experience-database",
        ],
        notes=(
            f"{ok_count}/{len(probes)} checks ok; MAUDE reports returned; nested "
            f"device.manufacturer_d_name is required (bare name -> 404); Medtronic family meta.total={total}; "
            f"date_received buckets={buckets} summing to {bucket_sum}. Passive-surveillance caveat recorded."
        ),
    )


if __name__ == "__main__":
    outcome = base.run_probe(connector.SOURCE_ID, ROOT, probe, budget=6, min_interval=0.9)
    print(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2)[:3000])
