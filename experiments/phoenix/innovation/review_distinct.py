"""Manual-precision review support: list the distinct newly-attributed names by frequency."""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments" / "phoenix" / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import phoenix_common as pc  # noqa: E402
import raea  # noqa: E402

con = pc.connect_ro()
registry = raea.load_registry(con)
events = raea.load_events(con)
con.close()
idx = raea.AliasIndex.build(registry)

rows = []
for eid, kind, gold, raw in events:
    if gold:
        continue
    pred, rule, detail = raea.attribute(raw, idx)
    if pred:
        rows.append((rule, raw, pred, kind))

by_rule = {}
for rule, raw, pred, kind in rows:
    by_rule.setdefault(rule, Counter())[(raw, pred)] += 1

for rule in ("R1_exact", "R2_suffix", "R3_family"):
    print(f"\n===== {rule}: {sum(by_rule.get(rule, {}).values())} events, "
          f"{len(by_rule.get(rule, {}))} distinct names =====")
    for (raw, pred), n in by_rule.get(rule, Counter()).most_common(45):
        print(f"{n:6d}  {str(raw)[:58]:60s} -> {pred}")
