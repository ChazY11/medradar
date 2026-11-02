"""Audit the crosswalk GO: pair distribution, duplicate later events, and the stricter count."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

payload = json.loads(Path("research/studies/early_signal_5firms/LEAD_LAG_PROBE_CROSSWALK.json")
                     .read_text(encoding="utf-8"))
print("verdict:", payload["verdict"], "| eligible pairs:", payload["eligible_pairs_total"],
      "| firms:", payload["firms_with_pairs"])
print("\nby cell:")
for key, block in payload["pairs_by_cell"].items():
    if block["eligible_pairs"]:
        print(f"  {key:34s} trials={block['trials_assigned']:>3} reg={block['regulatory_events']:>4} "
              f"pairs={block['eligible_pairs']:>2} below={block['below_threshold']:>2} "
              f"median_lead_q={block['leads']['median']}")

# duplicates: the same later event used by several earlier trials would inflate the count
pairs = payload.get("pairs") or []
print("\npair list present in artifact:", bool(pairs))
if pairs:
    later_counts = Counter(pair["later_id"] for pair in pairs)
    duplicates = {key: count for key, count in later_counts.items() if count > 1}
    print("distinct later events:", len(later_counts), "of", len(pairs))
    print("later events used more than once:", duplicates)
print("\nnot_claimed:")
for item in payload["not_claimed"]:
    print(" -", item)
