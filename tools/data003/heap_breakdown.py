"""DATA-003 heap breakdown.

Answers "where are the bytes?" for one loaded Dataset by attributing retained memory to
the structures the product actually keeps:

    Event instance overhead        (object + instance dict)
    Event scalar fields            (strings, deduplicated by identity)
    Event.raw payload              (the evidence dict, keys + values)
    events list / events_by_id
    _org_events / org_stats
    applicants / registry / manifest
    device index                   (when --index)

Sizes use sys.getsizeof (shallow) with an identity-based "already counted" set, so a
string shared by two events is counted once and reported under the first owner. This is
a lower bound for the true retained size and is labelled as such in the output.

Usage:
    python tools/data003/heap_breakdown.py --data-dir .data/active [--index]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCALAR_FIELDS = (
    "event_id",
    "official_id",
    "source_id",
    "event_type",
    "event_date",
    "published_at",
    "published_at_status",
    "first_observed_at",
    "available_at",
    "record_updated_at",
    "time_quality",
    "organization_key",
    "organization_name",
    "applicant_name",
    "attribution_status",
    "attribution_basis",
    "attribution_review",
    "product_code",
    "device_class",
    "device_name",
    "title",
    "summary",
    "official_url",
    "attribution_verification",
    "attribution_rule",
    "attribution_reviewer",
    "attribution_reviewer_kind",
    "attribution_provenance",
    "historical_owner_state",
    "historical_owner_reason",
    "historical_owner_display",
    "historical_owner_organization_key",
    "historical_owner_relation_id",
    "historical_owner_effective_from",
    "record_state",
)


class Sizer:
    def __init__(self) -> None:
        self.seen: set[int] = set()
        self.bytes = 0
        self.counts: Counter[str] = Counter()

    def add(self, value: Any, label: str) -> None:
        key = id(value)
        if key in self.seen:
            return
        self.seen.add(key)
        size = sys.getsizeof(value, 0)
        self.bytes += size
        self.counts[label] += size

    def add_deep(self, value: Any, label: str, depth: int = 3) -> None:
        """Count a value, its container, keys and immediate children once each."""
        self.add(value, label)
        if depth <= 0:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                self.add_deep(key, label + ".key", depth - 1)
                self.add_deep(item, label + ".value", depth - 1)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                self.add_deep(item, label + ".item", depth - 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--review-db", default=None)
    parser.add_argument("--index", action="store_true")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    from medradar.product.dataset import Dataset, load_dataset

    dataset = load_dataset(args.data_dir, review_db=args.review_db)
    sizer = Sizer()

    # ---- events
    event_overhead = 0
    scalar_bytes: Counter[str] = Counter()
    raw_total = 0
    raw_keys_bytes = 0
    for event in dataset.events:
        event_overhead += sys.getsizeof(event)
        instance_dict = getattr(event, "__dict__", None)
        if instance_dict is not None:
            event_overhead += sys.getsizeof(instance_dict)
        for field in SCALAR_FIELDS:
            value = getattr(event, field, None)
            if isinstance(value, str):
                before = sizer.counts["event." + field]
                # count the string exactly once, but attribute per field for the first owner
                key = id(value)
                if key not in sizer.seen:
                    sizer.seen.add(key)
                    size = sys.getsizeof(value)
                    scalar_bytes["event." + field] += size
                    sizer.bytes += size
                del before
            # non-str scalars are stored inside the instance dict already
        category = event.category
        if category is not None:
            sizer.add_deep(category, "event.category", depth=1)
        raw = event.raw or {}
        raw_total += sys.getsizeof(raw)
        for key, value in raw.items():
            sizer.add(key, "raw.key")
            sizer.add(value, "raw.value")
        sizer.seen.add(id(raw))
    scalar_bytes["__event_object_and_dict__"] = event_overhead
    scalar_bytes["__raw_dict_containers__"] = raw_total
    for key, value in sizer.counts.items():
        if key.startswith("raw."):
            scalar_bytes[key] = value
    raw_keys_bytes = scalar_bytes.get("raw.key", 0)

    # ---- dataset-level containers
    containers = {
        "events_list": sys.getsizeof(dataset.events),
        "events_by_id_dict": sys.getsizeof(dataset.events_by_id),
        "org_events_dict": sys.getsizeof(dataset._org_events),
        "applicants_list": sys.getsizeof(dataset.applicants),
        "manifest": sys.getsizeof(dataset.manifest),
        "registry": sys.getsizeof(dataset.registry),
        "global_counts": sys.getsizeof(dataset.global_counts),
        "global_aggregations": sys.getsizeof(dataset.global_aggregations),
        "org_stats": sys.getsizeof(dataset.org_stats),
    }
    # applicant rows are dicts retained by the dataset
    applicant_bytes = 0
    for row in dataset.applicants:
        applicant_bytes += sys.getsizeof(row)
        for key, value in row.items():
            sizer.add(key, "applicant.key")
            sizer.add_deep(value, "applicant.value", depth=2)
    containers["applicant_rows_and_values"] = applicant_bytes

    # ---- org stats payloads (recent events, sources)
    org_stats_bytes = 0
    for stats in dataset.org_stats.values():
        org_stats_bytes += sys.getsizeof(stats)
        for field_name in ("counts", "aggregations", "window", "sources", "recent_events", "status_counts", "historical_by_reason"):
            sizer.add_deep(getattr(stats, field_name, None), "org_stats." + field_name, depth=2)
    containers["org_stats_payloads"] = org_stats_bytes

    # ---- device index
    index_info: dict[str, Any] = {}
    if args.index:
        index_start = sizer.bytes
        index = dataset.device_index()
        sizes = {
            "applications": sys.getsizeof(index.applications),
            "devices": sys.getsizeof(index.devices),
            "families": sys.getsizeof(index.families),
            "recalls": sys.getsizeof(index.recalls),
            "relations_list": sys.getsizeof(index.relations),
        }
        for app in index.applications.values():
            sizer.add(app, "index.application")
            sizer.add_deep(getattr(app, "__dict__", None), "index.application.__dict__", depth=1)
            for field_name in getattr(app, "__dataclass_fields__", {}):
                sizer.add(getattr(app, field_name, None), "index.application.value")
        for device in index.devices.values():
            sizer.add(device, "index.device")
            sizer.add_deep(getattr(device, "__dict__", None), "index.device.__dict__", depth=1)
            for field_name in getattr(device, "__dataclass_fields__", {}):
                sizer.add(getattr(device, field_name, None), "index.device.value")
        for relation in index.relations:
            sizer.add(relation, "index.relation")
            sizer.add_deep(getattr(relation, "__dict__", None), "index.relation.__dict__", depth=1)
            sizer.add_deep(relation.evidence, "index.relation.evidence", depth=2)
        for family in index.families.values():
            sizer.add(family, "index.family")
            sizer.add_deep(getattr(family, "__dict__", None), "index.family.__dict__", depth=1)
        for recall in index.recalls.values():
            sizer.add(recall, "index.recall")
            sizer.add_deep(getattr(recall, "__dict__", None), "index.recall.__dict__", depth=1)
        for name in (
            "_relations_by_source",
            "_relations_by_target",
            "_devices_by_org",
            "_devices_by_category",
            "_devices_by_product_code",
            "_by_official",
            "recall_k_references",
            "external_k_references",
            "device_stats",
            "stats",
        ):
            value = getattr(index, name, None)
            sizer.add(value, "index." + name + ".container")
            if isinstance(value, dict):
                for key, item in value.items():
                    sizer.add(key, "index." + name + ".key")
                    sizer.add_deep(item, "index." + name + ".value", depth=1)
            elif isinstance(value, list):
                for item in value:
                    sizer.add(item, "index." + name + ".item")
        index_info = {
            "applications": len(index.applications),
            "devices": len(index.devices),
            "families": len(index.families),
            "recalls": len(index.recalls),
            "relations": len(index.relations),
            "attributed_bytes": sizer.bytes - index_start,
        }

    by_label = dict(sorted(sizer.counts.items(), key=lambda item: -item[1]))
    total = sizer.bytes + sum(containers.values())
    payload = {
        "probe": "data003.heap_breakdown.v1",
        "snapshot_id": dataset.snapshot_id,
        "events": len(dataset.events),
        "lower_bound_total_bytes": total,
        "lower_bound_event_bytes": sum(scalar_bytes.values()),
        "event_field_bytes": dict(sorted(scalar_bytes.items(), key=lambda item: -item[1])),
        "raw_keys_bytes": raw_keys_bytes,
        "containers": containers,
        "index": index_info,
        "by_label": by_label,
        "note": (
            "Lower bound: sys.getsizeof with identity deduplication. Shared strings are counted "
            "once, under the first structure that references them, so per-field rows are "
            "attribution rather than independent totals."
        ),
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
