"""B-067: rolling-origin evaluation of the PROMOTION PIPELINE on real history.

Pre-registered in research/DECISIONS.md D-064 before this script was first run.

Every component of the alerting pipeline has been validated in isolation (detector at D-045, calibration at
D-033, promotion rule at D-043/D-048/D-057/D-061). This is the first test of the pipeline end to end: does the
promotion filter improve the downstream hit rate on real history?

At each quarterly origin the deployed detector flags cells; the confirmed two-quarter rule then decides whether
to promote; the outcome is whether activity persisted in the four quarters after the confirmation window.

Pre-declared decision (D-064): PROMOTION ADDS VALUE iff P(persisted | promoted) exceeds
P(persisted | unpromoted) with a company-clustered bootstrap interval on the difference excluding zero.

Usage:
    python experiments/b067/promotion_rolling_origin.py
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b027.build_profiles import LANE, load_families  # noqa: E402
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import month_index  # noqa: E402
from medradar.intelligence.promotion import RAMP_REPORTING_FLOOR, classify_shape  # noqa: E402
from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402

Z_THRESHOLD = 3.5
BASELINE_QUARTERS = 8          # 24 months of memory, per D-045
CONFIRMATION_QUARTERS = 2
FOLLOWUP_QUARTERS = 4
FIRST_ORIGIN = (2019 - 2016) * 4 + 0          # 2019-Q1 as a quarter index in the lane window
LAST_ORIGIN = (2024 - 2016) * 4 + 3           # 2024-Q4
BOOTSTRAPS = 2000
SEED = 4242


def quarter_index(month: int) -> int:
    """Month index in the 2016-11 window -> quarter index."""
    year, month_of_year = divmod(month + 10, 12)   # month 0 == 2016-11
    return year * 4 + month_of_year // 3


def build_quarter_cells() -> dict[tuple[str, str], list[int]]:
    families = load_families()
    entity_to_company = {entity: key for key, family in families.items()
                         for entity in family["entities"]}
    cells: dict[tuple[str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for event in load_regulatory_events(LANE):
        normalised = normalise_applicant(event.get("applicant_raw"))
        track = event.get("track_id")
        index = month_index(event["day"])
        if not normalised or not track or index is None:
            continue
        company = entity_to_company.get(entity_key(normalised))
        if company is None:
            continue
        cells[(company, track)][quarter_index(index)] += 1
    return {key: dict(value) for key, value in cells.items()}


def evaluate() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cells = build_quarter_cells()
    records: list[dict[str, Any]] = []
    control: list[dict[str, Any]] = []
    for origin in range(FIRST_ORIGIN, LAST_ORIGIN + 1):
        for (company, track), counts in cells.items():
            history = [counts.get(quarter, 0) for quarter in range(origin - BASELINE_QUARTERS, origin)]
            baseline = sum(history) / len(history)
            if baseline <= 0:
                continue
            current = counts.get(origin, 0)
            zscore = (current - baseline) / (baseline ** 0.5)
            if zscore < Z_THRESHOLD:
                # control group: same cell-quarters that did not alert
                follow = [counts.get(origin + offset, 0)
                          for offset in range(CONFIRMATION_QUARTERS + 1,
                                              CONFIRMATION_QUARTERS + 1 + FOLLOWUP_QUARTERS)]
                control.append({"company": company,
                                "persisted": (sum(follow) / len(follow)) >= baseline})
                continue
            window = [counts.get(origin + offset, 0)
                      for offset in range(1, CONFIRMATION_QUARTERS + 1)]
            shape = classify_shape(window, baseline)["shape"]
            monthly_baseline = baseline / 3.0
            if shape == "ramp" and monthly_baseline < RAMP_REPORTING_FLOOR:
                shape = "sustained_unresolved"
            promoted = shape in ("level", "ramp", "sustained_unresolved")
            follow = [counts.get(origin + offset, 0)
                      for offset in range(CONFIRMATION_QUARTERS + 1,
                                          CONFIRMATION_QUARTERS + 1 + FOLLOWUP_QUARTERS)]
            future = sum(follow) / len(follow)
            records.append({"company": company, "track": track, "origin": origin,
                            "baseline": baseline, "current": current, "z": zscore,
                            "shape": shape, "promoted": promoted,
                            "future": future, "persisted": future >= baseline})
    summary = {
        "cells": len(cells),
        "origins": [FIRST_ORIGIN, LAST_ORIGIN],
        "alerts": len(records),
        "promoted": sum(1 for record in records if record["promoted"]),
        "unpromoted": sum(1 for record in records if not record["promoted"]),
        "control": len(control),
    }
    return records, {"summary": summary, "control": control}


def rate(rows: list[dict[str, Any]], key: str = "persisted") -> float | None:
    return (sum(1 for row in rows if row[key]) / len(rows)) if rows else None


def clustered_bootstrap(records: list[dict[str, Any]], control: list[dict[str, Any]],
                        rng: random.Random, reps: int) -> dict[str, Any]:
    by_company: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {"promoted": [], "unpromoted": [], "control": []})
    for record in records:
        by_company[record["company"]]["promoted" if record["promoted"] else "unpromoted"].append(record)
    for record in control:
        by_company[record["company"]]["control"].append(record)
    names = sorted(by_company)
    differences, promotion_rates, control_rates = [], [], []
    for _ in range(reps):
        sample = {"promoted": [], "unpromoted": [], "control": []}
        for _ in range(len(names)):
            chosen = names[rng.randrange(len(names))]
            for bucket in sample:
                sample[bucket].extend(by_company[chosen][bucket])
        promoted_rate = rate(sample["promoted"])
        unpromoted_rate = rate(sample["unpromoted"])
        control_rate = rate(sample["control"])
        if promoted_rate is not None and unpromoted_rate is not None:
            differences.append(promoted_rate - unpromoted_rate)
        if promoted_rate is not None:
            promotion_rates.append(promoted_rate)
        if control_rate is not None:
            control_rates.append(control_rate)

    def interval(values):
        if not values:
            return [None, None]
        values.sort()
        return [values[int(0.025 * len(values))],
                values[min(len(values) - 1, int(0.975 * len(values)))]]

    return {"difference_ci": interval(differences),
            "promoted_ci": interval(promotion_rates),
            "control_ci": interval(control_rates),
            "reps": reps, "companies": len(names)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b067/promotion_rolling_origin.json")
    args = parser.parse_args(argv)

    records, extra = evaluate()
    control = extra["control"]
    summary = extra["summary"]
    promoted = [record for record in records if record["promoted"]]
    unpromoted = [record for record in records if not record["promoted"]]
    boot = clustered_bootstrap(records, control, random.Random(SEED), BOOTSTRAPS)

    promoted_rate = rate(promoted)
    unpromoted_rate = rate(unpromoted)
    control_rate = rate(control)
    difference = (promoted_rate - unpromoted_rate
                  if promoted_rate is not None and unpromoted_rate is not None else None)
    ci_low, ci_high = boot["difference_ci"]
    adds_value = bool(ci_low is not None and ci_low > 0)

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-064 (pre-registered)",
            "z_threshold": Z_THRESHOLD, "baseline_quarters": BASELINE_QUARTERS,
            "confirmation_quarters": CONFIRMATION_QUARTERS, "followup_quarters": FOLLOWUP_QUARTERS,
            "origins": "2019-Q1 .. 2024-Q4",
            "outcome": "mean quarterly count in t+3..t+6 at least the alert-time baseline",
            "bootstrap": "companies resampled", "seed": SEED, "reps": BOOTSTRAPS,
        },
        "counts": summary,
        "rates": {"promoted": promoted_rate, "unpromoted": unpromoted_rate,
                  "control": control_rate, "difference": difference},
        "bootstrap": boot,
        "decision": {"adds_value": adds_value,
                     "verdict": ("PROMOTION ADDS VALUE - promoted alerts persist more often than "
                                 "unpromoted ones with an interval excluding zero"
                                 if adds_value else
                                 "NO ADDED VALUE - the promotion filter is a documentation discipline, "
                                 "not a measured predictive improvement")},
    }
    write_json(Path(args.out), payload)

    print(f"cells {summary['cells']}; alerts {summary['alerts']} "
          f"(promoted {summary['promoted']}, unpromoted {summary['unpromoted']}); "
          f"control cell-quarters {summary['control']}")
    print(f"P(persisted) promoted={promoted_rate:.3f} ci="
          f"{[None if v is None else round(v, 3) for v in boot['promoted_ci']]} "
          f"unpromoted={unpromoted_rate} control={control_rate}")
    print(f"difference={None if difference is None else round(difference, 3)} "
          f"ci={[None if v is None else round(v, 3) for v in boot['difference_ci']]}")
    print(f"verdict: {payload['decision']['verdict']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
