"""Inspect the generated config/universe_v1.json and cross-check the cohort."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

path = Path("config/universe_v1.json")
payload = json.loads(path.read_text(encoding="utf-8"))
print("top-level keys:", list(payload.keys()))
for key, value in payload.items():
    if isinstance(value, dict):
        print(f"  {key}: dict keys={list(value.keys())[:14]}")
    elif isinstance(value, list):
        print(f"  {key}: list len={len(value)}")
    else:
        print(f"  {key}: {value!r}")

entities = payload.get("entities") or payload.get("universe") or []
if isinstance(entities, dict):
    entities = entities.get("entities", [])
print("\nentity records:", len(entities))
if entities:
    print("record keys:", list(entities[0].keys()))
    print("first record:", json.dumps(entities[0], ensure_ascii=False)[:600])

# Locate cohort info if recorded
for key in ("cohort", "selected_cohort", "selection"):
    if key in payload:
        value = payload[key]
        print(f"\n{key}:", json.dumps(value, ensure_ascii=False)[:500])

# coverage / summary blocks
for key in ("coverage", "summary", "counts", "meta", "schema", "schema_version",
            "normalisation_version", "db"):
    if key in payload:
        value = payload[key]
        text = json.dumps(value, ensure_ascii=False)
        print(f"\n{key}: {text[:700]}")

# focus section
if "focus" in payload:
    print("\nfocus:", json.dumps(payload["focus"], ensure_ascii=False)[:900])
