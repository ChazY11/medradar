"""Inspect the third-source crosswalk result (read-only)."""
from __future__ import annotations

import json
from pathlib import Path

payload = json.loads(Path("research/studies/early_signal_5firms/THIRD_SOURCE_CROSSWALK.json")
                     .read_text(encoding="utf-8"))
print("status:", payload["status_counts"])
print("distance:", payload.get("distance_counts"))
for event in payload["events"]:
    print(f"  {event['event_id']} {event.get('company'):14s} {str(event.get('technology_track')):20s} "
          f"{event['status']:16s} {str(event.get('distance_class')):16s} "
          f"lead_years={event.get('lead_years')} hits={event.get('hits_total')}")
    record = event.get("earliest_record") or {}
    if record.get("title"):
        print(f"        earliest: {str(record.get('title'))[:90]} | {str(record.get('journal'))[:40]} "
              f"| pmid={record.get('pmid')}")
