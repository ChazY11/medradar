"""Build papers/CLAIMS_NEGATIVE.json — every number in the negative-result paper, with its artifact.

Same discipline as the other two papers: a number may not appear in the paper unless an artifact contains it, and the
verifier checks both directions (paper -> claims -> artifact).

    python papers/build_claims_negative.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

EVIDENCE = "research/studies/early_signal_5firms/CLAIMS_EVIDENCE.json"

CLAIMS = [
    ("N1", "two-stream primary cells", "5", EVIDENCE, '"two_stream_cells": 5'),
    ("N2", "cells touched by any stream", "47", EVIDENCE, '"cells_with_any_stream": 47'),
    ("N3", "clinical trial records", "55,592", EVIDENCE, '"trials_total": 55592'),
    ("N4", "trials assigned to the study device tracks", "0", EVIDENCE,
     '"trials_on_device_tracks": 0'),
    ("N5", "SEC 8-K records", "20,976", EVIDENCE, '"eightk_total": 20976'),
    ("N6", "8-K records carrying a company key", "1,360", EVIDENCE,
     '"eightk_with_company_key": 1360'),
    ("N7", "eligible pairs in the assumed crosswalk", "3", EVIDENCE,
     '"eligible_pairs_assumed_crosswalk": 3'),
    ("N8", "primary onsets in the expanded evaluation window", "0", EVIDENCE,
     '"primary_onsets_evaluation": 0'),
    ("N9", "onsets in the two-track run", "1", EVIDENCE, '"twotrack_onsets_evaluation": 1'),
    ("N10", "candidate quarters after twelve months of silence", "1", EVIDENCE,
     '"ladder_frozen_candidates": 1'),
    ("N11", "qualifying onsets under the frozen definition", "1", EVIDENCE,
     '"ladder_frozen_onsets": 1'),
    ("N12", "candidate quarters after twenty-four months of silence", "0", EVIDENCE,
     '"ladder_24m_candidates": 0'),
    ("N13", "skipped follow-on events at firm level", "303,942", EVIDENCE,
     '"firm_level_multiplicity_skipped": 303942'),
    ("N14", "cells in the incidence ladder", "16", EVIDENCE, '"ladder_cells": 16'),
    ("N15", "cells with an onset under the frozen definition", "1 / 16", EVIDENCE,
     '"ladder_frozen_cells_with_onset": 1'),
    ("N16", "event-level detector delay at x2", "185.5", EVIDENCE, '"phase1d_delay_a_m2": 185.5'),
    ("N17", "quarterly detector delay at x2", "48.5", EVIDENCE, '"phase1d_delay_b_m2": 48.5'),
    ("N18", "event-level power at x2", "0.762", EVIDENCE, '"phase1d_power_a_m2": 0.762'),
    ("N19", "quarterly power at x2", "0.333", EVIDENCE, '"phase1d_power_b_m2": 0.333'),
    ("N20", "paired delay difference at x2", "133.9", EVIDENCE, '"phase1d_diff_m2": 133.9'),
    ("N21", "paired delay difference lower bound", "71.5", EVIDENCE,
     '"phase1d_diff_m2_interval"'),
    ("N22", "paired delay difference at x3", "32.7", EVIDENCE, '"phase1d_diff_m3": 32.7'),
    ("N23", "event-level realised false-alarm rate", "0.095", EVIDENCE, '"phase1d_far_a": 0.095'),
    ("N24", "quarterly realised false-alarm rate", "0.029", EVIDENCE, '"phase1d_far_b": 0.029'),
]


def main() -> int:
    out = Path("papers/CLAIMS_NEGATIVE.json")
    failures, records = [], []
    for claim_id, statement, value, source, needle in CLAIMS:
        path = Path(source)
        if not path.exists():
            failures.append((claim_id, f"missing source {source}"))
            continue
        text = path.read_text(encoding="utf-8")
        if needle not in text:
            failures.append((claim_id, f"{needle!r} not found in {source}"))
            continue
        records.append({"id": claim_id, "statement": statement, "value": value,
                        "source": source, "source_needle": needle})
    out.write_text(json.dumps({"claims": records}, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"verified {len(records)} of {len(CLAIMS)} claims against artifacts")
    for claim_id, problem in failures:
        print(f"  FAIL {claim_id}: {problem}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
