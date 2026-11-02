"""The retraction-to-rule map used by Figure 1 of the methods paper.

Editorial data, but not free-floating: every event names the decision that records it, and every rule names the
mechanism it is now enforced by. The figure and the verifier both read this module, so the drawing and the check
cannot drift apart.

Rules (from papers/PAPER_METHODS_v1.md section 2):
  1 state the unit you measure
  2 a ratio is not evidence
  3 a benchmark outcome must not use the window that triggered the signal
  4 a holdout cannot confirm a hypothesis nominated with its help
  5 a negative conclusion about data availability is as falsifiable as a positive claim
  6 robustness in the preferred direction is not validation
  7 check the pipeline, not just the statistics
  8 report class-specific recall, not only aggregate accuracy
  9 a forecast registered after its outcome is known is a label
"""
from __future__ import annotations

from typing import Any

RULES = {
    1: "state the unit you measure",
    2: "a ratio is not evidence",
    3: "a benchmark outcome must not use the triggering window",
    4: "a holdout cannot confirm a post-hoc nomination",
    5: "a negative about data availability is falsifiable",
    6: "robustness in the preferred direction is not validation",
    7: "check the pipeline, not just the statistics",
    8: "report class-specific recall, not only aggregate accuracy",
    9: "a forecast after its outcome is known is a label",
}

#: (label, status, decision, rules motivated)
EVENTS: list[tuple[str, str, str, list[int]]] = [
    ("entity-appearance entry signal", "retracted", "D-025", [1, 6, 7]),
    ("lane co-movement", "retracted", "D-021", [3, 8]),
    ("cross-lane corroboration", "retracted", "D-023", [3, 7]),
    ("IVD entry wave", "retracted", "D-027", [1, 4, 7]),
    ("aesthetics split sample", "retracted", "D-027", [4]),
    ("hiring coverage conclusion", "retracted", "D-029", [5, 7]),
    ("density scaling", "confirmed after failure", "D-059", [2, 3, 9]),
    ("promotion rule", "confirmed", "D-043", [1, 8]),
    ("pipeline filter", "unestablished", "D-065", [2, 8]),
    ("backfilled forecasts", "excluded", "D-066", [9]),
]

STATUS_COLOURS = {
    "retracted": "#c0392b",
    "confirmed": "#1e8449",
    "confirmed after failure": "#b7950b",
    "unestablished": "#7f8c8d",
    "excluded": "#5d6d7e",
}


def map_data() -> list[dict[str, Any]]:
    """Rows in plotting order, with the rules each event motivated."""
    return [{"event": label, "status": status, "decision": decision, "rules": sorted(rules)}
            for label, status, decision, rules in EVENTS]


def filled_cells() -> int:
    return sum(len(record["rules"]) for record in map_data())


def verifier_expectations() -> dict[str, Any]:
    return {"events": len(EVENTS), "rules": len(RULES), "filled_cells": filled_cells(),
            "rows": map_data()}
