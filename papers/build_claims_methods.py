"""Build papers/CLAIMS_METHODS.json: every quantitative claim in the methods paper, with its source.

Same discipline as the empirical paper: the paper may not contain a number that cannot be found in a committed
artifact. Each claim declares the value as written, the source file and the exact substring to look for.

    python papers/build_claims_methods.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CLAIMS = [
    ("K1", "share of entry events that were entity appearances", "79 %", "research/RESULTS/cycle7_retraction_2026-11-02.md", "79 %"),
    ("K2", "naive ratio rule flags", "35 of 53", "research/DECISIONS.md", "35 of 53"),
    ("K3", "exact binomial detections", "4", "research/DECISIONS.md", "supports **4**"),
    ("K4", "per-company MDE range", "1.77× to 22.93×", "research/DECISIONS.md", "1.77× to 22.93×"),
    ("K5", "pre-registered rolling-origin lift", "0.49", "research/DECISIONS.md", "0.49"),
    ("K6", "corrected rolling-origin lift", "1.22", "research/DECISIONS.md", "1.22"),
    ("K7", "tracks nominated in the clean design", "3", "research/DECISIONS.md", "3 nominated"),
    ("K8", "tracks confirmed in the clean design", "0", "research/DECISIONS.md", "0 confirmed"),
    ("K9", "firms with posting URLs after the collector fix", "11", "research/DECISIONS.md", "11 companies with posting URLs"),
    ("K10", "forecasts that matured at registration", "7", "research/DECISIONS.md", "7 of the 32 forecasts"),
    ("K11", "Brier of the backfilled forecasts", "0.337", "research/DECISIONS.md", "0.337"),
    ("K12", "density monotonicity inversion", "0.018", "research/DECISIONS.md", "0.018"),
    ("K13", "density interval overlap", "0.023", "research/DECISIONS.md", "0.023"),
    ("K14", "first density rank correlation", "0.882", "research/DECISIONS.md", "0.882"),
    ("K15", "confirmed density rank correlation", "0.908", "research/DECISIONS.md", "0.908"),
    ("K16", "confirmed density effect ratio", "2.18×", "research/DECISIONS.md", "2.18×"),
    ("K17", "pipeline promoted persistence", "0.800", "research/DECISIONS.md", "0.800"),
    ("K18", "pipeline unpromoted persistence", "0.667", "research/DECISIONS.md", "0.667"),
    ("K19", "pipeline control persistence", "0.373", "research/DECISIONS.md", "0.373"),
    ("K20", "pipeline promotion difference", "+0.133", "research/DECISIONS.md", "0.133"),
    ("K21", "pipeline promotion interval lower bound", "−0.074", "research/DECISIONS.md", "\u22120.074"),
    ("K22", "pipeline promotion interval upper bound", "0.344", "research/DECISIONS.md", "0.344"),
    ("K23", "rule map filled cells", "21 filled cells", "papers/figures/figures_data.json",
     '"filled_cells": 21'),
    ("K24", "events in the rule map", "ten events", "papers/figures/figures_data.json",
     '"points": 10'),
    ("K25", "rules in the rule map", "nine rules", "papers/figures/figures_data.json", '"rules": 9'),
]


def read_any(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", "replace")


def main() -> int:
    out = Path("papers/CLAIMS_METHODS.json")
    failures, records = [], []
    for claim_id, statement, value, source, needle in CLAIMS:
        path = Path(source)
        if not path.exists():
            failures.append((claim_id, f"missing source {source}"))
            continue
        if needle not in read_any(path):
            failures.append((claim_id, f"{needle!r} not found in {source}"))
            continue
        records.append({"id": claim_id, "statement": statement, "value": value,
                        "source": source, "source_needle": needle})
    out.write_text(json.dumps({"claims": records}, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"verified {len(records)} of {len(CLAIMS)} claims")
    for claim_id, problem in failures:
        print(f"  FAIL {claim_id}: {problem}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
