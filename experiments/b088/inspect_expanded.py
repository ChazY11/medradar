"""Inspect the expanded run: where do onsets live (if anywhere)? Read-only summary."""
from __future__ import annotations

import json
from pathlib import Path

payload = json.loads(Path("research/studies/early_signal_5firms/CONCURRENT_DETECTION_EXPANDED.json")
                     .read_text(encoding="utf-8"))

print("primary cells:", len(payload["primary"]), "secondary:", len(payload["secondary"]))
for label in ("primary", "secondary"):
    onsets_all = sum(len(cell["onsets_all"]) for cell in payload[label])
    onsets_eval = sum(len(cell["onsets_evaluation"]) for cell in payload[label])
    censored = sum(len(cell["censored"]) for cell in payload[label])
    print(f"{label:10s} onsets_all={onsets_all:>3} onsets_evaluation={onsets_eval:>3} censored={censored:>3}")
    for cell in payload[label]:
        if cell["onsets_all"] or cell["censored"]:
            print(f"    {cell['company']:14s} {cell['track']:22s} onsets={cell['onsets_all']} "
                  f"eval={cell['onsets_evaluation']} censored={len(cell['censored'])}")

print("\npooled primary:")
for name, block in payload["pooled_primary"].items():
    if block.get("status") == "OK":
        print(f"  {name:18s} alerts={block['alerts']:>3} hits={block['hits']} false={block['false_alerts']:>3} "
              f"recall={block['recall']}")
print("\npooled secondary:")
for name, block in payload["pooled_secondary"].items():
    if block.get("status") == "OK":
        print(f"  {name:18s} alerts={block['alerts']:>3} hits={block['hits']} false={block['false_alerts']:>3} "
              f"recall={block['recall']}")
print("\nverdict:", payload["verdict"])
