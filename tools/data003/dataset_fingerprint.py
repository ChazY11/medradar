"""DATA-003 dataset fingerprint.

Produces a SHA-256 over everything the product derives from a snapshot, so a memory
optimisation can be proven behaviour-preserving rather than assumed:

* every event's public projection (``Event.to_public``),
* the global counts / aggregations,
* every organization's ``OrgStats`` (counts, window, per-source rows, status counts),
* the device index: every application, device, family, recall and relation public projection,
  plus the quality report the API serves.

Two trees (before/after) that produce the same digest expose the same product semantics.

Usage:
    python tools/data003/dataset_fingerprint.py --data-dir <snapshot-or-root> [--json-out FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCHEMA = "data003.dataset_fingerprint.v1"


class Hasher:
    def __init__(self) -> None:
        self._hash = hashlib.sha256()
        self.rows = 0

    def add(self, value: Any) -> None:
        self._hash.update(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
        self._hash.update(b"\n")
        self.rows += 1

    def digest(self) -> str:
        return self._hash.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--review-db", default=None)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--skip-index", action="store_true")
    args = parser.parse_args(argv)

    from medradar.product import dataset as dataset_module

    dataset = dataset_module.load_dataset(args.data_dir, review_db=args.review_db)

    events = Hasher()
    for event in dataset.events:
        events.add(event.to_public())

    aggregates = Hasher()
    aggregates.add(dataset.global_counts)
    aggregates.add(dataset.global_aggregations)
    aggregates.add(dataset.global_by_type)
    for key in sorted(dataset.org_stats):
        stats = dataset.org_stats[key]
        aggregates.add(
            {
                "key": key,
                "counts": stats.counts,
                "aggregations": stats.aggregations,
                "window": stats.window,
                "sources": stats.sources,
                "recent_events": stats.recent_events,
                "first_observed_at": stats.first_observed_at,
                "pending_review_records": stats.pending_review_records,
                "unattributed_in_scope": stats.unattributed_in_scope,
                "rejected_in_scope": stats.rejected_in_scope,
                "verified_records": stats.verified_records,
                "rule_verified_records": stats.rule_verified_records,
                "proposed_records": stats.proposed_records,
                "status_counts": stats.status_counts,
                "historical_verified_current_group": stats.historical_verified_current_group,
                "historical_verified_predecessor": stats.historical_verified_predecessor,
                "historical_unknown": stats.historical_unknown,
                "historical_by_reason": stats.historical_by_reason,
            }
        )

    index_digest = None
    index_counts: dict[str, int] = {}
    quality_digest = None
    if not args.skip_index:
        index = dataset.device_index()
        hasher = Hasher()
        for key in sorted(index.applications):
            hasher.add(index.applications[key].to_public())
        for key in sorted(index.devices):
            hasher.add(index.devices[key].to_public())
        for key in sorted(index.families):
            hasher.add(index.families[key].to_public())
        for key in sorted(index.recalls):
            hasher.add(index.recalls[key].to_public())
        for relation in sorted(index.relations, key=lambda item: item.relation_id):
            hasher.add(relation.to_public())
        index_digest = hasher.digest()
        index_counts = {
            "applications": len(index.applications),
            "devices": len(index.devices),
            "families": len(index.families),
            "recalls": len(index.recalls),
            "relations": len(index.relations),
        }
        from medradar.product.device import quality_report

        quality = quality_report(index)
        quality.pop("index_build_ms", None)
        quality_digest = hashlib.sha256(
            json.dumps(quality, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()

    payload = {
        "schema": SCHEMA,
        "snapshot_id": dataset.snapshot_id,
        "events": len(dataset.events),
        "organizations": len(dataset.registry.organizations),
        "events_sha256": events.digest(),
        "aggregates_sha256": aggregates.digest(),
        "index_sha256": index_digest,
        "quality_sha256": quality_digest,
        "index_counts": index_counts,
        "warnings": dataset.warnings,
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
