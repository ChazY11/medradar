import json
from pathlib import Path

d = json.loads((Path(__file__).resolve().parent / "results" / "raea_results.json").read_text(encoding="utf-8"))
g = d["application_to_unmapped"]["gained_by_rule_and_kind"]
tot = {}
for r in g:
    tot[r["rule"]] = tot.get(r["rule"], 0) + r["n"]
print("gained by rule:", tot, "total", d["application_to_unmapped"]["total_gained"])
print("guard:", json.dumps(d["guard_tradeoff"], indent=2))
print("coverage:", json.dumps(d["coverage_change"], indent=2))
