"""Inspect the matched_far lead-time payload shape from analysis.json."""
import json
from pathlib import Path

data = json.loads(Path("experiments/cycle2_coverage/analysis.json").read_text(encoding="utf-8"))
for panel in ("p1", "p2"):
    lead = data["panels"][panel].get("lead_time", {})
    for window in lead.get("windows", [])[:1]:
        print(f"== {panel} {window['origin']} matched_far ==")
        print(json.dumps(window.get("matched_far"), indent=2, default=str)[:3000])
        print("\nnaive model:", json.dumps(window.get("model"), indent=2)[:500])
