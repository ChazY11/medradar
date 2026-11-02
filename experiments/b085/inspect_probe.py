"""Inspect the lead/lag probe result (read-only)."""
from __future__ import annotations

import json
from pathlib import Path

payload = json.loads(Path("research/studies/early_signal_5firms/LEAD_LAG_PROBE.json")
                     .read_text(encoding="utf-8"))

print("== S1 primary ==")
for key, block in payload["scope_s1_primary"].items():
    zero = block["by_lag"]["0"]
    print(f"  {key:30s} trials={block['trials']:>4} reg={block['regulatory_events']:>5} "
          f"pairs={zero['n_pairs']} below_threshold={zero['n_below_threshold']} "
          f"multiplicity_skipped={zero['multiplicity_skipped']}")

print("\n== S2 assumed crosswalk ==")
for key, block in payload["scope_s2_assumed_crosswalk"].items():
    zero = block["by_lag"]["0"]
    print(f"  {key:40s} trials={block['trials']:>3} reg={block['regulatory_events']:>3} "
          f"pairs={zero['n_pairs']} below={zero['n_below_threshold']} "
          f"median_lead={zero['median_lead_quarters']}")

print("\n== S3 descriptive ==")
for firm, block in payload["scope_s3_descriptive"].items():
    zero = block["by_lag"]["0"]
    print(f"  {firm:14s} trials={block['trials']:>4} reg={block['regulatory_events']:>5} "
          f"pairs={zero['n_pairs']} below={zero['n_below_threshold']} "
          f"multiplicity_skipped={zero['multiplicity_skipped']}")

print("\n== 8-K ==")
for firm, block in payload["eightk_scope_s3"].items():
    print(f"  {firm:14s} records={block['records']:>3} pairs_by_lag={block['eligible_pairs_by_lag']}")

print("\nG1:", payload["g1"]["verdict"])
