"""Live probe for ``fda_import_alerts`` (DATA-EXPANSION-001, postmarket).

Run from the repository root::

    python research/data_expansion/probes/fda_import_alerts/probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from medradar.external_sources import base  # noqa: E402
from medradar.external_sources.regulatory import postmarket_fda_import_alerts as connector  # noqa: E402

ROOT = REPO_ROOT / "research" / "data_expansion"
SAMPLES = ROOT / "samples" / connector.SOURCE_ID


def probe(client: base.HttpClient, directory: Path) -> base.ProbeOutcome:
    probes: list[dict] = []

    # The bare directory is a Forbidden directory-listing page, which is why the
    # documented entry point must be a concrete HTML file.
    bare = client.get("https://www.accessdata.fda.gov/cms_ia/", accept="text/html")
    probes.append(
        {
            "name": "bare_directory_not_usable",
            "url": bare.url,
            "status": bare.status,
            "ok": bare.status == 403,
            "bytes": len(bare.body),
            "elapsed_ms": bare.elapsed_ms,
            "error": bare.error,
            "note": "HTTP 403.14 directory listing forbidden; concrete .html pages are required",
        }
    )

    index = client.get(connector.INDEX_URL, accept="text/html")
    rows: list[dict] = []
    sample = None
    if index.ok:
        sample = base.write_sample(SAMPLES, "ialist.html", index.body)
        rows = connector.parse_alert_index(index.text)
    probes.append(
        {
            "name": "ialist_index_parsed",
            "url": index.url,
            "status": index.status,
            "ok": index.ok,
            "bytes": len(index.body),
            "elapsed_ms": index.elapsed_ms,
            "error": index.error,
            "sample": sample,
            "alerts": len(rows),
            "first_rows": rows[:3],
        }
    )

    device_group = client.get(connector.DEVICE_GROUP_URL, accept="text/html")
    industries: list[dict] = []
    if device_group.ok:
        base.write_sample(SAMPLES, "industrygroup_9_medical_devices.html", device_group.body)
        industries = connector.parse_industry_links(device_group.text)
    probes.append(
        {
            "name": "device_industry_group_parsed",
            "url": device_group.url,
            "status": device_group.status,
            "ok": device_group.ok and len(industries) >= 10,
            "bytes": len(device_group.body),
            "elapsed_ms": device_group.elapsed_ms,
            "error": device_group.error,
            "device_industries": len(industries),
            "first_industries": industries[:4],
        }
    )

    detail_url = "https://www.accessdata.fda.gov/cms_ia/importalert_1182.html"
    detail = client.get(detail_url, accept="text/html")
    if detail.ok:
        base.write_sample(SAMPLES, "importalert_1182.html", detail.body)
    probes.append(
        {
            "name": "one_alert_detail_page",
            "url": detail.url,
            "status": detail.status,
            "ok": detail.ok,
            "bytes": len(detail.body),
            "elapsed_ms": detail.elapsed_ms,
            "error": detail.error,
            "is_real_alert_page": "Import Alert" in detail.text[:4000] if detail.ok else False,
            "five_firm_alias_text_hits": connector.count_firm_tokens(detail.text) if detail.ok else None,
            "note": "detail pages carry the firm red list; counts are raw text hits, not identity links",
        }
    )

    records = connector.parse_to_evidence(index.body, fetched_at=base.utc_iso()) if index.ok else []
    probes.append(
        {
            "name": "schema_validation",
            "ok": bool(records),
            "status": index.status,
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
            "https://www.accessdata.fda.gov/cms_ia/ialist.html",
            "https://www.accessdata.fda.gov/cms_ia/industrygroup_9.html",
            "https://www.fda.gov/about-fda/about-website/website-policies",
        ],
        notes=(
            f"no openFDA endpoint; ialist.html parsed into {len(rows)} import alerts with number/type/"
            f"publish-date/name, {len(records)} schema-v1 evidence records; device industry group lists "
            f"{len(industries)} sub-industries. Index has no company column, so firm-level linkage is UNKNOWN."
        ),
    )


if __name__ == "__main__":
    outcome = base.run_probe(connector.SOURCE_ID, ROOT, probe, budget=8, min_interval=0.9)
    print(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2)[:3000])
