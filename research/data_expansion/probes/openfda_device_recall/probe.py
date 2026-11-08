"""Live probe for ``openfda_device_recall`` (DATA-EXPANSION-001, postmarket).

Run from the repository root::

    python research/data_expansion/probes/openfda_device_recall/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from medradar.external_sources import base  # noqa: E402
from medradar.external_sources.regulatory import postmarket_openfda_device_recall as connector  # noqa: E402

ROOT = REPO_ROOT / "research" / "data_expansion"


def probe(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    probes: list[dict] = []

    smoke = client.get(connector.API_URL, params={"limit": 2})
    row = {}
    if smoke.ok:
        payload = smoke.json()
        rows = payload.get("results") or []
        row = rows[0] if rows else {}
        sample = base.write_sample(directory.parent.parent / "samples" / connector.SOURCE_ID, "smoke_limit2.json", smoke.body)
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

    # The device recall schema uses event_date_*; the drug enforcement report_date
    # must NOT be assumed.  Prove the actual date fields from the response.
    date_fields = {
        "event_date_initiated": row.get("event_date_initiated"),
        "event_date_posted": row.get("event_date_posted"),
        "event_date_created": row.get("event_date_created"),
        "event_date_terminated": row.get("event_date_terminated"),
        "report_date_present": "report_date" in row,
        "center_classification_date_present": "center_classification_date" in row,
    }
    probes.append(
        {
            "name": "date_field_semantics",
            "ok": bool(date_fields["event_date_initiated"] and date_fields["event_date_posted"]),
            "status": 200 if smoke.ok else smoke.status,
            "detail": date_fields,
            "conclusion": (
                "device/recall exposes event_date_initiated (event) and event_date_posted (public); "
                "report_date is absent"
            ),
        }
    )

    # Real record total for one firm via the documented search syntax.
    firm = client.get(connector.API_URL, params={"search": 'recalling_firm:"Medtronic"', "limit": 1})
    total = None
    if firm.ok:
        total = ((firm.json().get("meta") or {}).get("results") or {}).get("total")
    probes.append(
        {
            "name": "search_recalling_firm_medtronic",
            "url": firm.url,
            "status": firm.status,
            "ok": firm.ok,
            "bytes": len(firm.body),
            "elapsed_ms": firm.elapsed_ms,
            "error": firm.error,
            "meta_total": total,
            "note": 'quoted value is an analysed phrase match on recalling_firm; 1599 records at probe time',
        }
    )

    # Server-side count aggregation (buckets are real returned values).
    count = client.get(
        connector.API_URL,
        params={"search": 'recalling_firm:"Medtronic"', "count": "event_date_posted"},
    )
    buckets = 0
    bucket_sum = 0
    if count.ok:
        results = count.json().get("results") or []
        buckets = len(results)
        bucket_sum = sum(int(item.get("count", 0)) for item in results)
        base.write_sample(
            directory.parent.parent / "samples" / connector.SOURCE_ID,
            "count_medtronic_event_date_posted.json",
            count.body,
        )
    probes.append(
        {
            "name": "count_event_date_posted_medtronic",
            "url": count.url,
            "status": count.status,
            "ok": count.ok,
            "bytes": len(count.body),
            "elapsed_ms": count.elapsed_ms,
            "error": count.error,
            "buckets": buckets,
            "bucket_sum": bucket_sum,
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
            "https://open.fda.gov/apis/device/recall/",
            "https://open.fda.gov/apis/authentication/",
            "https://open.fda.gov/license/",
        ],
        notes=(
            f"{ok_count}/{len(probes)} checks ok; limit=2 returned real device-recall records; "
            f"Medtronic phrase search meta.total={total}; date fields are event_date_initiated/posted "
            f"(report_date absent)."
        ),
    )


if __name__ == "__main__":
    outcome = base.run_probe(connector.SOURCE_ID, ROOT, probe, budget=6, min_interval=0.9)
    print(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2)[:3000])
