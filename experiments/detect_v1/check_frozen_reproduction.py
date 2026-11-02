"""Guard against silently rewriting published benchmark numbers.

Two classes of level are treated differently, on purpose:

* **Monthly panels** (``track``, ``track_clean``, ``domain``) are FROZEN. They must match
  the committed ``benchmark.json`` value-for-value, otherwise a harness change has
  silently altered a published result and the run fails.
* **Bin-width panels** (``track_quarterly`` and any future width) are reported as
  *changed* with their old and new read-outs, because detector memory scaling was
  introduced deliberately (DECISIONS D-020) and it necessarily changes them. Silent
  change would be the failure; a disclosed change is the point.

Exit code 0 iff every monthly panel is unchanged.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PATH = "experiments/detect_v1/benchmark.json"
FROZEN_LEVELS = ("track", "track_clean", "domain")
BUDGET = "0.02"


def frozen_payload() -> dict | None:
    try:
        text = subprocess.run(["git", "show", f"HEAD:{PATH}"],
                              capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    return json.loads(text)


def compare_points(old: dict, new: dict) -> list[str]:
    problems: list[str] = []
    old_points = {point["knob"]: point for point in old["frontier"]}
    new_points = {point["knob"]: point for point in new["frontier"]}
    if set(old_points) != set(new_points):
        return ["knob set changed"]
    for knob, point in old_points.items():
        other = new_points[knob]
        for field in ("false_alarm_rate", "detection_probability", "median_delay_months"):
            if point[field] != other[field]:
                problems.append(f"knob {knob} {field}: frozen={point[field]} now={other[field]}")
    return problems


def readout(level_block: dict) -> dict[str, float | None]:
    points = level_block["frontier_readout"].get(BUDGET, {})
    return {name: point.get("detection_probability") for name, point in points.items()}


def main() -> int:
    frozen = frozen_payload()
    current = json.loads(Path(PATH).read_text(encoding="utf-8"))
    if frozen is None:
        print("could not read the frozen benchmark from git; treating as first run")
        return 0

    failures = 0
    print("== frozen monthly panels (must be identical) ==")
    for level in FROZEN_LEVELS:
        if level not in frozen["levels"] or level not in current["levels"]:
            print(f"  [{level}] missing from one side")
            failures += 1
            continue
        problems: list[str] = []
        for name, old_block in frozen["levels"][level]["detectors"].items():
            if "frontier" not in old_block:
                continue
            problems.extend(compare_points(old_block, current["levels"][level]["detectors"][name]))
        if problems:
            failures += len(problems)
            for problem in problems[:5]:
                print(f"  MISMATCH [{level}] {problem}")
        else:
            print(f"  [{level}] identical")

    print("\n== bin-width panels (disclosed change, not a failure) ==")
    for level in sorted(set(frozen["levels"]) | set(current["levels"])):
        if level in FROZEN_LEVELS:
            continue
        if level not in frozen["levels"] or level not in current["levels"]:
            print(f"  [{level}] present on one side only")
            continue
        old_read, new_read = readout(frozen["levels"][level]), readout(current["levels"][level])
        if old_read == new_read:
            print(f"  [{level}] unchanged")
        else:
            print(f"  [{level}] CHANGED (disclosed in DECISIONS D-020):")
            for name in sorted(old_read):
                if old_read[name] != new_read[name]:
                    print(f"      {name:24s} was {old_read[name]} now {new_read[name]}")

    print(f"\nmonthly-panel reproduction: {'PASS' if not failures else f'FAIL ({failures})'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
