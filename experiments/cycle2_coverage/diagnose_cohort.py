"""Isolate why the computed cohort differs from the committed artifact cohort."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.universe import (  # noqa: E402
    build_universe, select_cohort,
)
from experiments.cycle2_coverage.run_cycle2 import (  # noqa: E402
    build_cohort, load_regulatory_events,
)

artifact = json.loads(Path("config/universe_v1.json").read_text(encoding="utf-8"))
artifact_entities = artifact["entities"]
artifact_cohort = set(artifact["cohort"]["entity_keys"])
print("artifact entities:", len(artifact_entities), "cohort:", len(artifact_cohort))

# 1) select_cohort over the artifact's own records
cohort_from_artifact = set(select_cohort(artifact_entities, max_entities=200))
print("select_cohort(artifact records):", len(cohort_from_artifact),
      "equals artifact cohort:", cohort_from_artifact == artifact_cohort)
print("  only in artifact cohort:", sorted(artifact_cohort - cohort_from_artifact)[:8])
print("  only in select_cohort:", sorted(cohort_from_artifact - artifact_cohort)[:8])

# 2) my universe
events = load_regulatory_events(Path("data/research.sqlite"))
mine = build_universe(events, min_events=2)
print("\nmy universe entities:", len(mine))
mine_by_key = {r["entity_key"]: r for r in mine}
art_by_key = {r["entity_key"]: r for r in artifact_entities}
print("  keys only in mine:", len(set(mine_by_key) - set(art_by_key)))
print("  keys only in artifact:", len(set(art_by_key) - set(mine_by_key)))

# 3) compare n_material / active_years for the boundary entities
diffs = []
for key in sorted(artifact_cohort & set(mine_by_key)):
    a, m = art_by_key[key], mine_by_key[key]
    if a["n_material"] != m["n_material"] or a["active_years"] != m["active_years"]:
        diffs.append((key, a["n_material"], m["n_material"], a["active_years"], m["active_years"]))
print("  records in both cohorts with differing n_material/active_years:", len(diffs))
for row in diffs[:10]:
    print("   ", row)

# 4) my computed cohort vs artifact
cohort_mine, required, detail = build_cohort(mine, cohort_size=200, min_material=3,
                                             min_active_years=2)
print("\nmy build_cohort:", len(cohort_mine), "required focus:", sorted(required.values()))
print("  symmetric difference:", len(artifact_cohort ^ set(cohort_mine)))
print("  only mine:", sorted(set(cohort_mine) - artifact_cohort))
print("  only artifact:", sorted(artifact_cohort - set(cohort_mine)))
print("  min n_material in mine:", min(mine_by_key[k]["n_material"] for k in cohort_mine))
print("  min n_material in artifact:", min(art_by_key[k]["n_material"] for k in artifact_cohort))
