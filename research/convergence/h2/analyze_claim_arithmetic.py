#!/usr/bin/env python3
"""Check the internal arithmetic of the *superseded* EXP-H2 prose table.

The stale prose in ``EXPERIMENT_RESULTS.md`` and
``REGULATORY_FRONTIER_REPORT.md`` quotes 712 pairs / 387 REJECTED / 325 UNKNOWN
and a per-signal table (S2 fired 445, S3 fired 365).  This script parses that
table and tests whether those numbers are mutually consistent under the verdict
rule that the frozen code implements:

    REJECTED  ==  S2 and not S3                 (firm/model contradiction)
                  or (S2 and an MDALL end_date before the GUDID publish date)
    UNKNOWN   ==  everything else
    CONFIRMED ==  S4

If the table is internally consistent, the stale numbers were produced by a
different-but-coherent earlier run (not by typos), and the only missing piece is
the S2 matcher that produced 445 hits.  That matcher is not present in git.

Usage:
    python research/convergence/h2/analyze_claim_arithmetic.py
"""

from __future__ import annotations

import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", "..", ".."))
DOC = os.path.join(REPO_ROOT, "research", "horizon", "EXPERIMENT_RESULTS.md")


def cells(line):
    s = line.strip()
    if not s.startswith("|"):
        return None
    s = s[1:-1] if s.endswith("|") else s[1:]
    return [c.strip().strip("`").strip("*").strip() for c in s.split("|")]


def main():
    with open(DOC, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    combos = {}
    fired = {}
    verdicts = {}
    for line in lines:
        c = cells(line)
        if not c:
            continue
        if c[0] in ("CONFIRMED", "REJECTED", "UNKNOWN") and len(c) == 2:
            verdicts[c[0]] = int(c[1])
            continue
        m = re.match(r"^(S\d)\s*\(", c[0])
        if m and len(c) >= 5:
            fired_m = re.search(r"(\d+)\s+fired", " ".join(c[:2]))
            if fired_m:
                fired[m.group(1)] = int(fired_m.group(1))
            continue
        if re.fullmatch(r"S\d(?:\s*\+\s*S\d)+", c[0]) and len(c) >= 5:
            label = re.sub(r"\s+", "", c[0])
            vals = {}
            for idx, key in ((1, "n"), (2, "C"), (3, "R"), (4, "U")):
                vals[key] = int(c[idx]) if re.fullmatch(r"\d+", c[idx]) else None
            combos[label] = vals

    print("quoted verdicts:", verdicts)
    print("quoted per-signal fired:", fired)
    print("quoted combinations:", combos)
    print()

    s2_total = fired.get("S2")
    s3_total = fired.get("S3")
    row_3 = combos["S2+S3+S5"]
    row_2 = combos["S2+S3"]
    row_5 = combos["S2+S5"]
    c_s2s3s5 = row_3["n"]
    c_s2s3 = row_2["n"]
    c_s2s5 = row_5["n"]
    s2_only = s2_total - c_s2s3s5 - c_s2s3 - c_s2s5
    s3_only = s3_total - c_s2s3s5 - c_s2s3
    total = c_s2s3s5 + c_s2s3 + c_s2s5 + s2_only + s3_only

    rejected = (row_3["R"] + row_2["R"] + row_5["R"] + s2_only)
    unknown = (row_2["U"] + s3_only)
    print("derived buckets")
    print(f"  S2-only = S2({s2_total}) - S2S3S5({c_s2s3s5}) - S2S3({c_s2s3}) - S2S5({c_s2s5})"
          f" = {s2_only}")
    print(f"  S3-only = S3({s3_total}) - S2S3S5({c_s2s3s5}) - S2S3({c_s2s3}) = {s3_only}")
    print(f"  total   = {c_s2s3s5} + {c_s2s3} + {c_s2s5} + {s2_only} + {s3_only} = {total}")
    print(f"  REJECTED = S2S3S5.R({row_3['R']}) + S2S3.R({row_2['R']}) "
          f"+ S2S5.R({row_5['R']}) + S2-only({s2_only}) = {rejected}")
    print(f"  UNKNOWN  = S2S3.U({row_2['U']}) + S3-only({s3_only}) = {unknown}")
    print()

    ok = (total == verdicts.get("CONFIRMED", 0) + verdicts["REJECTED"] + verdicts["UNKNOWN"]
          and total == 712 and rejected == verdicts["REJECTED"] and unknown == verdicts["UNKNOWN"])
    print(f"internal consistency: {'PASS' if ok else 'FAIL'}")
    print("interpretation: the stale table is arithmetically coherent only if S2 fired 445")
    print("times under a matcher that the committed code no longer contains.  The committed")
    print("matcher fires 0 times under both documented modes, so its rejection path is dead")


if __name__ == "__main__":
    main()
