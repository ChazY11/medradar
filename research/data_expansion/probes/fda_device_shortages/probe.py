"""Live probe for ``fda_device_shortages`` (DATA-EXPANSION-001, postmarket).

Run from the repository root::

    python research/data_expansion/probes/fda_device_shortages/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from medradar.external_sources import base  # noqa: E402
from medradar.external_sources.regulatory import postmarket_fda_device_shortages as connector  # noqa: E402

ROOT = REPO_ROOT / "research" / "data_expansion"
SAMPLES = ROOT / "samples" / connector.SOURCE_ID


def probe(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    probes: list[dict] = []

    # Negative check: confirm there is no openFDA device-shortage endpoint.  A 404
    # from the *documented gateway host* is the evidence, not an assumption.
    missing = client.get("https://api.fda.gov/device/shortage.json", params={"limit": 1})
    probes.append(
        {
            "name": "openfda_shortage_endpoint_absent",
            "url": missing.url,
            "status": missing.status,
            "ok": missing.status == 404,
            "bytes": len(missing.body),
            "elapsed_ms": missing.elapsed_ms,
            "error": missing.error,
            "note": "404 = no such openFDA endpoint; the public data is the HTML list page",
        }
    )

    page = client.get(connector.PAGE_URL, accept="text/html")
    sample = None
    parsed: dict = {}
    if page.ok:
        sample = base.write_sample(SAMPLES, "medical-device-shortages-list.html", page.body)
        parsed = connector.parse_shortages_page(page.text)
    probes.append(
        {
            "name": "shortages_list_page",
            "url": page.url,
            "status": page.status,
            "ok": page.ok,
            "bytes": len(page.body),
            "elapsed_ms": page.elapsed_ms,
            "error": page.error,
            "sample": sample,
            "tables": parsed.get("table_count"),
            "table_headers": parsed.get("table_headers"),
        }
    )

    shortages = parsed.get("shortages") or []
    discontinuances = parsed.get("discontinuances") or []
    probes.append(
        {
            "name": "parsed_real_records",
            "ok": len(shortages) >= 1 and len(discontinuances) >= 1,
            "status": page.status,
            "shortage_rows": len(shortages),
            "discontinuance_rows": len(discontinuances),
            "first_shortage": shortages[0] if shortages else None,
            "first_discontinuance": discontinuances[0] if discontinuances else None,
            "note": "rows are server-rendered in the page source; both tables have real entries",
        }
    )

    # Real evidence records must validate against schema v1.
    records = connector.parse_to_evidence(page.body, fetched_at=base.utc_iso()) if page.ok else []
    probes.append(
        {
            "name": "schema_validation",
            "ok": bool(records),
            "status": page.status,
            "records": len(records),
            "distinct_record_ids": len({record["source_record_id"] for record in records}),
            "kinds": sorted({record["kind"] for record in records}),
        }
    )

    ok_count = sum(1 for item in probes if item.get("ok"))
    status = "VERIFIED_PUBLIC_QUERY" if ok_count >= 3 and records else "UNAVAILABLE"
    return base.ProbeOutcome(
        source_id=connector.SOURCE_ID,
        status=status,
        probes=probes,
        requests=client.requests_made(),
        evidence_urls=[
            "https://www.fda.gov/medical-devices/medical-device-supply-chain-and-shortages/medical-device-shortages-list",
            "https://www.fda.gov/about-fda/about-website/website-policies",
        ],
        notes=(
            f"no openFDA shortage endpoint (404 confirmed); HTML list parsed into "
            f"{len(shortages)} shortage rows + {len(discontinuances)} discontinuance rows, "
            f"{len(records)} schema-v1 evidence records. Listing date is the only published clock."
        ),
    )


if __name__ == "__main__":
    outcome = base.run_probe(connector.SOURCE_ID, ROOT, probe, budget=4, min_interval=0.9)
    print(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2)[:3000])
