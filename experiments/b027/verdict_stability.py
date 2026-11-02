"""Quantify how stable profile verdicts are across the point-in-time snapshot chain.

For every company, read its momentum direction in each frozen snapshot and report:
  * companies whose verdict never changed,
  * companies whose verdict changed at least once,
  * companies that *reversed* (decreasing -> increasing or the reverse).
A verdict that flips with the as-of date is a statement about noise as much as about the company.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

SNAPSHOTS = Path("experiments/b027/snapshots")
OUT = Path("experiments/b027/verdict_stability.json")


def main() -> int:
    directories = sorted(path for path in SNAPSHOTS.iterdir() if path.is_dir())
    sequences: dict[str, list[str]] = defaultdict(list)
    dates = []
    for directory in directories:
        payload = json.loads((directory / "profiles.json").read_text(encoding="utf-8"))
        dates.append(payload["as_of"])
        for company, profile in payload["profiles"].items():
            momentum = profile["momentum"]
            sequences[company].append(momentum.get("direction", momentum.get("status")))

    stable, changed, reversed_count = 0, 0, 0
    reversals = []
    detail = {}
    for company, sequence in sequences.items():
        distinct = {value for value in sequence
                    if value not in ("insufficient_window", "no_events")}
        if len(distinct) <= 1:
            stable += 1
        else:
            changed += 1
        pair_reversal = any(
            {sequence[index], sequence[index + 1]} == {"increasing", "decreasing"}
            for index in range(len(sequence) - 1))
        if pair_reversal:
            reversed_count += 1
            reversals.append({"company": company, "sequence": sequence})
        detail[company] = {"sequence": sequence, "distinct": sorted(distinct),
                           "reversed": pair_reversal}
    payload = {
        "snapshots": [directory.name for directory in directories],
        "as_of_dates": dates,
        "companies": len(sequences),
        "stable_verdict": stable,
        "changed_verdict": changed,
        "reversed_verdict": reversed_count,
        "reversals": reversals,
        "detail": detail,
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"snapshots: {len(dates)} ({dates[0]} .. {dates[-1]})")
    print(f"companies: {len(sequences)}")
    print(f"stable verdict across all snapshots: {stable}")
    print(f"changed verdict at least once: {changed}")
    print(f"reversed (increasing <-> decreasing): {reversed_count}")
    for row in reversals[:8]:
        flags = " -> ".join(row["sequence"])
        print(f"   {row['company']:20s} {flags}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
