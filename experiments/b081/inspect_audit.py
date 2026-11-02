"""Inspect the entity/domain audit result (read-only helper for Phase 0)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

payload = json.loads(Path("research/studies/early_signal_5firms/ENTITY_AND_DOMAIN_AUDIT.json")
                     .read_text(encoding="utf-8"))
domains = payload["domain_sharing"]
print("floors:", domains["floors"])
print("tracks touched in window by any of the five firms:", len(domains["all_tracks_touched"]))
print()
print("shared tracks that support RQ4 (>= 3 firms meeting floors):")
for track, block in domains["shared_tracks"].items():
    print(f"  {track}  ({block['count']} firms)")
    for firm, row in sorted(block["detail"].items()):
        print(f"    {firm:14s} observations={row['observations']:>5}  quarters={row['quarters']:>3}  "
              f"meets_floor={row['meets_floor']}")
print()
print("GE HealthCare corporate-era continuity:")
for name, years in payload["ge_continuity"]["per_year_by_alias_group"].items():
    if not years:
        continue
    span = f"{min(years)}..{max(years)}"
    print(f"  {name:20s} span={span}  observations={sum(years.values())}")
print("  roster rows:", payload["ge_continuity"]["roster_rows"])
print()
print("alias strings flagged for human review:")
for firm, block in payload["entity_resolution"].items():
    for item in block["strings"]:
        if item["verdict"] == "REVIEW":
            print(f"  {firm:14s} | {item['applicant_raw']} | n={item['observations']} | "
                  f"tokens={item['suspicion_tokens']}")
