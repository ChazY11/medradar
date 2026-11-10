#!/usr/bin/env python3
"""Offline smoke test for the independent verifier (used by CI).

Builds a tiny synthetic store from the public evidence API, derives a matching
report, then runs ``tools/verify_atlas.py`` against it.  This proves the
verifier's hash/relational/arithmetic checks work without any network or
committed database.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medradar.atlas.evidence import schema as ev  # noqa: E402
from medradar.atlas.evidence.timeq import build_time, utc_iso  # noqa: E402
from medradar.atlas.identity.resolver import (  # noqa: E402
    CONFIRMED,
    SAME_DEVICE_IDENTITY,
    MatchDecision,
)
from medradar.atlas.store import AtlasStore  # noqa: E402


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_atlas", ROOT / "tools" / "verify_atlas.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_store(db_path: Path) -> dict:
    with AtlasStore(db_path) as store:
        records = []
        for i, source in enumerate(("openfda_device_udi", "canada_mdall"), start=1):
            record = ev.make_evidence(
                source_id=source,
                source_record_id=f"rec-{i}",
                evidence_type="device_registration",
                source_url=f"https://example.test/{i}",
                raw_content_hash=ev.sha256_text(f"raw-{i}"),
                raw_bytes=8,
                normalized={"brand_name": f"DEVICE {i}", "country": "US" if i == 1 else "CA"},
                time=build_time(
                    event_at=None,
                    source_public_at="2020-01-01",
                    fetched_at="2026-11-10T00:00:00Z",
                    quality="day",
                ),
                identifiers=[{"scheme": "di", "value": "08717648200274", "is_primary": True}],
                entity_refs=[
                    {
                        "entity_type": "company",
                        "name_raw": "MEDTRONIC",
                        "firm_key": "medtronic",
                        "method": "exact_alias",
                        "confidence": 0.95,
                        "matched_alias": "MEDTRONIC",
                    }
                ],
                licence_status="public_domain",
                identity_resolution_status="confirmed",
            )
            store.append_evidence(record)
            records.append(record)
        store.upsert_company(
            company_id=ev.deterministic_id("co", "firm", "medtronic"),
            canonical_name="Medtronic plc",
            aliases=["MEDTRONIC"],
        )
        for i, record in enumerate(records, start=1):
            store.upsert_device(
                device_id=f"dev-{i}",
                canonical_name=f"DEVICE {i}",
                brand_name=f"DEVICE {i}",
                company_id=ev.deterministic_id("co", "firm", "medtronic"),
                identifiers=[{"scheme": "di", "value": "08717648200274", "is_primary": True}],
                evidence_id=record["evidence_id"],
            )
        decision = MatchDecision(
            left_ref="dev-1",
            right_ref="dev-2",
            relation_type=SAME_DEVICE_IDENTITY,
            status=CONFIRMED,
            method="official_identifier",
            authority="source_declared",
            confidence=0.99,
        )
        store.add_relation(
            decision, evidence_ids=[r["evidence_id"] for r in records]
        )
        stats = store.stats()
    report = {
        "schema": "medradar.atlas.identity_pilot.v1",
        "counts": {
            "evidence_ids": stats["evidence_ids"],
            "evidence_versions": stats["evidence_versions"],
            "unique_devices": stats["devices"],
            "device_identifiers": stats["device_identifiers"],
            "companies": stats["companies"],
            "bridge_confirmed_identity": stats["relations_confirmed"],
        },
        "relations": {
            "confirmed": stats["relations_confirmed"],
            "candidate": stats["relations_candidate"],
            "rejected": stats["relations_rejected"],
        },
        "baseline": {
            "metrics": {
                "identity": {
                    "tp": 1, "fp": 0, "fn": 0, "tn": 1,
                    "precision": 1.0, "recall": 1.0, "f1": 1.0, "labelled_pairs": 2,
                }
            }
        },
    }
    return report


def main() -> int:
    verifier_module = load_verifier()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "atlas.sqlite"
        report = build_store(db)
        report_path = Path(tmp) / "identity_pilot.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        result = verifier_module.Verifier(db, report_path).run()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
