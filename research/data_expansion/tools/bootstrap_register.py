#!/usr/bin/env python
"""Safety net: create *probe-only* register records for sources with no documentation record.

Agent-written records are the intended input.  This tool exists so that a probe
obtained under time pressure is not lost from the register just because nobody
wrote the documentary half.

It is deliberately conservative:

* it never claims documentation research that was not done — unverified
  documentary fields are left as ``UNKNOWN``;
* it sets ``record_origin = "lead_bootstrap_from_probe"`` so the report can say
  exactly which records came from this path;
* it refuses to overwrite an existing record.

    python research/data_expansion/tools/bootstrap_register.py --dry-run
    python research/data_expansion/tools/bootstrap_register.py --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

INDEX = ROOT / "registry" / "SOURCE_ID_INDEX.json"
SOURCES = ROOT / "registry" / "sources"
PROBES = ROOT / "probes"

#: Domain -> category label used when only a probe exists.
DOMAIN_CATEGORY = {
    "A": "regulatory_udi",
    "B": "patent",
    "C": "scholarly_literature",
    "D": "clinical_trial_registry",
    "E": "trade_and_customs",
    "F": "public_procurement",
    "G": "hiring",
    "H": "research_funding",
    "I": "postmarket_safety",
}


def load_index() -> dict[str, dict]:
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    return {item["source_id"]: item for item in payload["sources"]}


def probe_status(source_id: str) -> dict | None:
    path = PROBES / source_id / "PROBE_RESULT.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_record(source_id: str, meta: dict, probe: dict) -> dict:
    return {
        "source_id": source_id,
        "source_name": meta.get("source_name", source_id),
        "official_url": meta.get("official_url", "UNKNOWN"),
        "country_or_region": meta.get("country_or_region", "UNKNOWN"),
        "domain": meta.get("domain", "UNKNOWN"),
        "category": DOMAIN_CATEGORY.get(meta.get("domain", ""), "UNKNOWN"),
        "official_or_commercial": "UNKNOWN",
        "api_available": "YES" if str(probe.get("status", "")).startswith("VERIFIED_") else "UNKNOWN",
        "bulk_download_available": "UNKNOWN",
        "authentication": "UNKNOWN",
        "free_tier": "UNKNOWN",
        "rate_limits": "UNKNOWN",
        "licence": "UNKNOWN",
        "redistribution_allowed": "UNKNOWN",
        "update_frequency": "UNKNOWN",
        "historical_coverage": "UNKNOWN",
        "entity_identifiers": [],
        "timestamp_fields": [],
        "known_limitations": [
            "documentation not reviewed for this record; fields marked UNKNOWN are genuinely unknown",
            f"probe note: {str(probe.get('notes', ''))[:300]}",
        ],
        "connection_status": "NOT_TESTED",
        "research_value": f"probe-only record. {str(probe.get('notes', ''))[:400]}",
        "evidence_urls": list(probe.get("evidence_urls", []) or []),
        "verified_at": str(probe.get("verified_at", "")),
        "cost_notes": "UNKNOWN",
        "probe_priority": meta.get("priority", "UNKNOWN"),
        "record_origin": "lead_bootstrap_from_probe",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    index = load_index()
    SOURCES.mkdir(parents=True, exist_ok=True)
    created, skipped, no_probe = [], [], []
    for source_id, meta in sorted(index.items()):
        target = SOURCES / f"{source_id}.json"
        if target.exists():
            skipped.append(source_id)
            continue
        probe = probe_status(source_id)
        if probe is None:
            no_probe.append(source_id)
            continue
        record = build_record(source_id, meta, probe)
        created.append(source_id)
        if args.write:
            target.write_text(
                json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    print(f"existing records : {len(skipped)}")
    print(f"{'would create' if args.dry_run else 'created'}     : {len(created)}")
    for source_id in created:
        print(f"  + {source_id}")
    print(f"no probe, no record: {len(no_probe)}")
    for source_id in no_probe:
        print(f"  - {source_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
