"""Check that the extended benchmark still reproduces the frozen cycle-3 numbers.

Compares the current benchmark.json against the committed one (git HEAD) for the three
default panels, so a harness change cannot silently rewrite a published result.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PATH = "experiments/detect_v1/benchmark.json"


def load_json(text: str):
    return json.loads(text)


def main() -> int:
    try:
        frozen_text = subprocess.run(
            ["git", "show", f"HEAD:{PATH}"], capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError as exc:
        print("could not read frozen benchmark from git:", exc)
        return 1
    frozen = load_json(frozen_text)
    current = load_json(Path(PATH).read_text(encoding="utf-8"))

    failures = 0
    for level in ("track", "track_clean", "domain"):
        old = frozen["levels"][level]
        new = current["levels"][level]
        for name, old_block in old["detectors"].items():
            if "frontier" not in old_block:
                continue
            new_block = new["detectors"][name]
            old_points = {p["knob"]: p for p in old_block["frontier"]}
            new_points = {p["knob"]: p for p in new_block["frontier"]}
            if set(old_points) != set(new_points):
                print(f"  [{level}/{name}] knob set changed")
                failures += 1
                continue
            for knob, point in old_points.items():
                other = new_points[knob]
                for field in ("false_alarm_rate", "detection_probability",
                              "median_delay_months"):
                    if point[field] != other[field]:
                        print(f"  MISMATCH [{level}/{name}/{knob}] {field}: "
                              f"frozen={point[field]} now={other[field]}")
                        failures += 1
    print(f"\nreproduction: {'PASS' if not failures else f'FAIL ({failures} mismatches)'}")
    print(f"frozen levels: {list(frozen['levels'])}")
    print(f"current levels: {list(current['levels'])}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
