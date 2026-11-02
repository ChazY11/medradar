"""Repair claim P2: point it at a committed artifact instead of an uncommitted 5.6 MB prediction dump.

The claim map asserted an entity-panel ΔAP against `experiments/cycle2_coverage/pred_p2.json`, which is produced by
`dump_predictions.py` but was never committed (the file exists only in old worktrees). A claim whose source is not in
git cannot be verified by anyone who clones the repository. The committed `analysis.log` carries the entity-clustered
ΔAP (0.09732061085035523), which supports the same three-decimal claim (0.097), so the claim is re-anchored there and
the uncommitted dump is no longer required.
"""
from __future__ import annotations

import json
from pathlib import Path

CLAIMS = Path("papers/CLAIMS.json")
BUILD = Path("papers/build_claims.py")

NEW_SOURCE = "experiments/cycle2_coverage/analysis.log"
NEW_NEEDLE = "0.09732061085035523"

payload = json.loads(CLAIMS.read_text(encoding="utf-8"))
changed = 0
for claim in payload["claims"]:
    if claim["id"] == "P2":
        claim["source"] = NEW_SOURCE
        claim["source_needle"] = NEW_NEEDLE
        changed += 1
CLAIMS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

text = BUILD.read_text(encoding="utf-8")
old = '"experiments/cycle2_coverage/pred_p2.json", "0.09738123148139934"'
new = f'"{NEW_SOURCE}", "{NEW_NEEDLE}"'
if old in text:
    BUILD.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    changed += 1

log = Path(NEW_SOURCE).read_text(encoding="utf-8", errors="replace")
print(f"claims updated: {changed}; needle present in committed log: {NEW_NEEDLE in log}")
