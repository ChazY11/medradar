"""Fast smoke test for the P2 panel build (no backtest)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.cycle2_coverage.run_cycle2 import build_p2  # noqa: E402

panel, detail = build_p2(Path("data/research.sqlite"), cohort_size=200,
                         min_material=3, min_active_years=2)
print("P2 panel size:", panel["n_examples"], "positives:", panel["n_positives"],
      "base rate:", round(panel["n_positives"] / panel["n_examples"], 5))
print("entities:", panel["entity_count"], "tracks:", panel["track_count"],
      "pairs:", panel["observed_pair_count"])
print("coverage:", panel["coverage_start"], "->", panel["coverage_end"],
      "origins:", len(panel["cutoffs"]))
print("candidates/origin:", {k: v for k, v in list(panel["candidates_by_origin"].items())[:5]}, "...")
print("positives/origin:", {k: v for k, v in list(panel["positives_by_origin"].items())[:5]}, "...")
print("pos/origin min/max:", min(panel["positives_by_origin"].values()),
      max(panel["positives_by_origin"].values()))
print("cohort:", detail["universe"]["cohort_size"], "of", detail["universe"]["entities_total"])
print("events in cohort:", detail["universe"]["events_in_cohort"], "/",
      detail["universe"]["events_total_material"])
print("\nfocus:")
for key, row in detail["universe"]["focus_companies"].items():
    ents = row["universe_entities"]
    print(f"  {key:16s} entities={len(ents)} in_cohort={sum(1 for e in ents if e['in_cohort'])} "
          f"top={ents[0]['display_name'][:40] if ents else None} n_material={ents[0]['n_material'] if ents else 0}")
print("\ntop cohort:")
for row in detail["universe"]["top_cohort"][:12]:
    print(f"  {row['display_name'][:42]:42s} mat={row['n_material']:5d} ev={row['n_events']:5d} "
          f"years={row['active_years']:2d} tracks={row['tracks']:2d}")
