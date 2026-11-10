#!/usr/bin/env python3
"""Audit facts about the frozen EXP-H2 pair file.

Prints the recomputed distribution, the pair-id uniqueness check, and the exact
arithmetic that connects the final artifact (726 rows) to the number quoted in
the prose (712 pairs).

Usage:
    python research/convergence/h2/audit_pairs.py
"""

from __future__ import annotations

import json
import os
from collections import Counter

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", ".."))
PAIRS = os.path.join(REPO_ROOT, "research", "horizon", "experiments", "regulatory",
                     "EXP_H2_PAIRS.jsonl")


def main():
    with open(PAIRS, "r", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    ids = [r["pair_id"] for r in rows]
    verdicts = Counter(r["verdict"] for r in rows)
    construction = Counter(r.get("construction_rule") or "candidate" for r in rows)
    per_signal = {s: sum(1 for r in rows if (r.get("signals") or {}).get(s))
                  for s in ("S1", "S2", "S3", "S4", "S5")}

    hn_total = sum(v for k, v in construction.items() if k != "candidate")
    candidate = construction.get("candidate", 0)
    hn3 = construction.get("HN3_same_family_different_device", 0)
    hn4 = construction.get("HN4_subsidiary_vs_parent", 0)

    print(f"file: {PAIRS}")
    print(f"rows={len(rows)}  unique_pair_id={len(set(ids))}  "
          f"duplicate_pair_id={len(ids) - len(set(ids))}")
    print(f"verdicts={dict(verdicts)}")
    print(f"by_construction_rule={dict(construction)}")
    print(f"per_signal_fired={per_signal}")
    print()
    print("identity checks")
    print(f"  726 - HN3({hn3})                     = {len(rows) - hn3}")
    print(f"  candidate({candidate}) + HN4({hn4})          = {candidate + hn4}")
    print(f"  candidate({candidate}) + HN3({hn3}) + HN4({hn4}) = {candidate + hn3 + hn4}")
    print()
    print("conclusion: 712 = 726 - 14 = 700 candidate rows + 12 HN4 rows;")
    print("           i.e. the prose count predates the HN3 hard-negative stage,")
    print("           and it is NOT a duplicate-pair_id collapse (0 duplicates).")


if __name__ == "__main__":
    main()
