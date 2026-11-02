#!/usr/bin/env python3
"""Check that every decimal quoted in the v2 report/docs exists in the v2 artifacts.

This is a guard against transcription drift between prose and JSON, not a proof
of correctness: it verifies that each quoted decimal is a number present in
``config.json``, ``continuation_metrics.json``, ``entry_metrics.json`` or
``data_provenance.json`` at some displayed precision. Percentages of artifact
rates and their complements are allowed; a small set of protocol constants is
whitelisted because they describe the fixed algorithm rather than a result.

Usage (from the repository root):

    python experiments/reverse_rd_v2/check_numbers.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "experiments" / "reverse_rd_v2"
DOCUMENTS = (EXPERIMENT / "REPORT.md", ROOT / "docs" / "PHASE1.md")
# Fixed algorithm/protocol constants that are prose, not measured results.
PROTOCOL_CONSTANTS = {"0.15", "1.0", "2.0", "0.5", "0.95", "180", "2000", "11", "12", "24", "36", "120"}
TOKEN = re.compile(r"[-\u2212]?\d+\.\d+")


def _walk(node, out: list[float]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _walk(value, out)
    elif isinstance(node, list):
        for value in node:
            _walk(value, out)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out.append(float(node))


def _allowed_values() -> set[str]:
    values: list[float] = []
    for name in ("config.json", "continuation_metrics.json", "entry_metrics.json", "data_provenance.json"):
        _walk(json.loads((EXPERIMENT / name).read_text(encoding="utf-8")), values)
    allowed: set[str] = set(PROTOCOL_CONSTANTS)
    for value in values:
        for digits in (1, 2, 3, 4, 5, 6):
            allowed.add(f"{value:.{digits}f}")
            allowed.add(f"{abs(value) * 100:.{digits}f}")
            allowed.add(f"{abs(1.0 - abs(value)) * 100:.{digits}f}")
    return allowed


def main() -> int:
    allowed = _allowed_values()
    failed = False
    for path in DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        missing = sorted({token.replace("\u2212", "-") for token in TOKEN.findall(text)}
                         - allowed)
        status = "ok" if not missing else "MISMATCH"
        print(f"{path.relative_to(ROOT)}: {status}")
        for token in missing:
            print(f"   number not in artifacts: {token}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
