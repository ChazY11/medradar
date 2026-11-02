"""Evidence table for the negative-result paper: every number the paper cites, computed once.

The paper must not contain a number that cannot be found in a committed artifact. Most of its numbers already live in
study artifacts; the two that did not (8-K records carrying a company key, and the trial count on device tracks) are
computed here so the claim map has a single machine-checkable source.

    python experiments/b090/paper_evidence.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
STUDY = Path("research/studies/early_signal_5firms")
OUT = STUDY / "CLAIMS_EVIDENCE.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)

    inventory = json.loads((STUDY / "CELL_INVENTORY.json").read_text(encoding="utf-8"))
    expanded = json.loads((STUDY / "CONCURRENT_DETECTION_EXPANDED.json").read_text(encoding="utf-8"))
    twotrack = json.loads((STUDY / "CONCURRENT_DETECTION.json").read_text(encoding="utf-8"))
    ladder = json.loads((STUDY / "ONSET_LADDER.json").read_text(encoding="utf-8"))
    earlier = json.loads((STUDY / "EARLIER_SOURCE_AUDIT.json").read_text(encoding="utf-8"))
    probe = json.loads((STUDY / "LEAD_LAG_PROBE.json").read_text(encoding="utf-8"))

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    trials_total = con.execute("select count(*) from events where kind='trial'").fetchone()[0]
    eightk_total = con.execute("select count(*) from events where kind='8k_catalyst'").fetchone()[0]
    eightk_with_key = con.execute(
        "select count(*) from events where kind='8k_catalyst' and company_key is not null").fetchone()[0]
    device_tracks = ("imaging_us", "respiratory")
    trials_placeholder = ",".join("?" for _ in device_tracks)
    trials_on_device_tracks = con.execute(
        f"select count(*) from events where kind='trial' and track_id in ({trials_placeholder})",
        device_tracks).fetchone()[0]
    con.close()

    frozen = ladder["totals_by_definition"]["silence4q_episode4q_min2"]
    strict = ladder["totals_by_definition"]["silence8q_episode8q_min3"]
    s1_pairs = probe["g1"]["scope_s1"]["eligible_pairs_by_lag"]["0"]
    s2_pairs = probe["g1"]["scope_s2_assumed_crosswalk"]["eligible_pairs_by_lag"]["0"]
    firm_multiplicity = max(
        block["by_lag"]["0"]["multiplicity_skipped"]
        for block in probe["scope_s3_descriptive"].values())

    evidence = {
        "schema": "claims_evidence_v1",
        "paper": "papers/PAPER_NEGATIVE_v1.md",
        "store": str(STORE).replace("\\", "/"),
        "cells_with_any_stream": inventory["counts"]["cells_with_any_stream"],
        "two_stream_cells": inventory["counts"]["both_streams"],
        "regulatory_only_cells": len(inventory["regulatory_only"]),
        "trials_total": trials_total,
        "trials_on_device_tracks": trials_on_device_tracks,
        "eightk_total": eightk_total,
        "eightk_with_company_key": eightk_with_key,
        "eligible_pairs_primary_scope": s1_pairs,
        "eligible_pairs_assumed_crosswalk": s2_pairs,
        "firm_level_multiplicity_skipped": firm_multiplicity,
        "primary_onsets_evaluation": expanded["totals"]["primary_onsets"],
        "primary_cells": expanded["totals"]["primary_cells"],
        "secondary_cells": expanded["totals"]["secondary_cells"],
        "twotrack_onsets_evaluation": twotrack["totals"]["onsets_evaluation"],
        "ladder_frozen_candidates": frozen["candidates"],
        "ladder_frozen_onsets": frozen["onsets"],
        "ladder_frozen_cells_with_onset": frozen["cells_with_onset"],
        "ladder_24m_candidates": strict["candidates"],
        "ladder_24m_onsets": strict["onsets"],
        "ladder_cells": ladder["cells"],
        "earlier_source_verdict": earlier["pair_feasibility"]["verdict"],
        "expansion_verdict": expanded["verdict"],
        "twotrack_verdict": twotrack["verdict"],
    }
    Path(args.out).write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8", newline="\n")
    for key in ("two_stream_cells", "trials_total", "trials_on_device_tracks", "eightk_total",
                "eightk_with_company_key", "eligibility_pairs_primary_scope" if False else
                "eligible_pairs_assumed_crosswalk", "primary_onsets_evaluation",
                "twotrack_onsets_evaluation", "ladder_frozen_candidates", "ladder_frozen_onsets",
                "ladder_24m_candidates", "firm_level_multiplicity_skipped"):
        print(f"  {key:34s} {evidence[key]}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
