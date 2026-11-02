"""Correct the lane-event counts in the cycle-16 documents to the measured values.

The values written while drafting were not read from the freeze logs. The measured counts are:
  2020-12-31 -> 12,853 of 31,802 lane events
  2022-12-31 -> 19,182
  2024-12-31 -> 25,772
"""
from __future__ import annotations

from pathlib import Path

REPLACEMENTS = [
    ("17,797 lane events", "12,853 lane events"),
    ("| 17,797 |", "| 12,853 |"),
    ("24,913", "19,182"),
    ("32,135", "25,772"),
]

FILES = [Path("research/DECISIONS.md"), Path("research/RESULTS/cycle16_point_in_time_2026-11-03.md")]


def main() -> int:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        original = text
        for old, new in REPLACEMENTS:
            text = text.replace(old, new)
        if text != original:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"corrected {path}")
        else:
            print(f"no change needed in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
