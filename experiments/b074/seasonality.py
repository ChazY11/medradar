"""B-037: quantify the seasonal and lane-volume artifacts, and test whether the measured FAR is an upper bound.

Pre-registered in research/DECISIONS.md D-072 before this script was first run.

The detector's operating point (quarterly, rolling z >= 3.5, measured false-alarm rate 0.0179) was computed on raw
counts. The programme's noise controls require the month-of-year and lane-wide volume effects to be estimated and
either removed or explicitly stated, so this script:

  1. estimates a multiplicative factor per calendar month from lane-wide monthly totals and tests it by permutation;
  2. reports the two artifacts named in the design review - the January deficit and a quarter-boundary volume effect;
  3. recomputes the operating point on seasonally adjusted counts and compares alerts, FAR and injected sensitivity;
  4. checks the factor spread *inside* a quarter, since the deployed detector aggregates three months.

Usage:
    python experiments/b074/seasonality.py
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b026.spike_vs_shift import (  # noqa: E402
    BASELINE_MONTHS,
    EFFECT_MULTIPLIER,
    MIN_HISTORY,
    SHAPES,
    classify_posthoc,
    detect,
    inject,
)
from experiments.b027.build_profiles import LANE, load_families  # noqa: E402
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import month_index  # noqa: E402
from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402

MONTHS = 119
SEED = 7373
PERMUTATIONS = 2000
FAR_MATERIAL = 0.001


def build_cells() -> tuple[dict[tuple[str, str], list[int]], list[int]]:
    families = load_families()
    entity_to_company = {entity: key for key, family in families.items()
                         for entity in family["entities"]}
    cells: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0] * MONTHS)
    lane_totals = [0] * MONTHS
    for event in load_regulatory_events(LANE):
        normalised = normalise_applicant(event.get("applicant_raw"))
        track = event.get("track_id")
        index = month_index(event["day"])
        if not normalised or not track or index is None or not 0 <= index < MONTHS:
            continue
        company = entity_to_company.get(entity_key(normalised))
        if company is None:
            continue
        cells[(company, track)][index] += 1
        lane_totals[index] += 1
    return {key: value for key, value in cells.items()}, lane_totals


def month_labels(count: int) -> list[int]:
    """Calendar month index (0 = January) for each position in the lane window, which starts 2016-11."""
    return [(index + 10) % 12 for index in range(count)]


def month_factors(lane_totals: list[int]) -> dict[str, Any]:
    labels = month_labels(len(lane_totals))
    totals: dict[int, int] = defaultdict(int)
    counts: dict[int, int] = defaultdict(int)
    for label, value in zip(labels, lane_totals):
        totals[label] += value
        counts[label] += 1
    overall = sum(lane_totals) / len(lane_totals)
    factors = {month: (totals[month] / counts[month]) / overall for month in range(12)}
    dispersion = sum((value / overall - 1.0) ** 2 for value in lane_totals)
    return {"factors": {str(month): round(value, 4) for month, value in factors.items()},
            "overall_monthly_mean": overall, "dispersion": dispersion,
            "spread_max_over_min": max(factors.values()) / min(factors.values())}


def permutation_test(lane_totals: list[int], observed: float, rng: random.Random,
                     permutations: int) -> dict[str, Any]:
    """Shuffle the month labels: if seasonality is absent, the observed dispersion is unremarkable."""
    labels = month_labels(len(lane_totals))
    overall = sum(lane_totals) / len(lane_totals)
    exceed = 0
    for _ in range(permutations):
        shuffled = labels[:]
        rng.shuffle(shuffled)
        totals: dict[int, int] = defaultdict(int)
        counts: dict[int, int] = defaultdict(int)
        for label, value in zip(shuffled, lane_totals):
            totals[label] += value
            counts[label] += 1
        statistic = sum(((totals[month] / counts[month]) / overall - 1.0) ** 2 for month in range(12))
        if statistic >= observed:
            exceed += 1
    return {"permutations": permutations, "exceedances": exceed,
            "p_value": (exceed + 1) / (permutations + 1)}


def boundary_artifact(lane_totals: list[int]) -> dict[str, Any]:
    """First/last month of each calendar quarter against interior months."""
    labels = month_labels(len(lane_totals))
    buckets: dict[str, list[int]] = {"quarter_start": [], "quarter_interior": [], "quarter_end": []}
    for index, (label, value) in enumerate(zip(labels, lane_totals)):
        position = label % 3          # 0 = first month of the quarter
        bucket = "quarter_start" if position == 0 else ("quarter_end" if position == 2 else "quarter_interior")
        buckets[bucket].append(value)
    means = {name: (sum(values) / len(values) if values else 0.0) for name, values in buckets.items()}
    interior = means["quarter_interior"] or 1.0
    return {"means": {name: round(value, 2) for name, value in means.items()},
            "quarter_start_vs_interior": round(means["quarter_start"] / interior, 4),
            "quarter_end_vs_interior": round(means["quarter_end"] / interior, 4)}


def adjust(series: list[int], factors: dict[int, float], labels: list[int]) -> list[int]:
    return [max(0, round(value / factors[labels[index]])) if factors[labels[index]] > 0 else value
            for index, value in enumerate(series)]


def quarterly_counts(series: list[int], labels: list[int]) -> list[int]:
    quarters: dict[tuple[int, int], int] = defaultdict(int)
    for index, value in enumerate(series):
        year = 2016 + (index + 10) // 12
        quarter = labels[index] // 3
        quarters[(year * 4 + quarter)] += value
    keys = sorted(quarters)
    return [quarters[key] for key in keys]


def run_quarterly_alerts(cells: dict[tuple[str, str], list[int]], labels: list[int],
                         factors: dict[int, float] | None) -> dict[str, Any]:
    """Alert rate of the deployed detector at quarterly resolution, on raw or seasonally adjusted counts."""
    alerts = 0
    opportunities = 0
    for counts in cells.values():
        adjusted = counts if factors is None else adjust(counts, factors, labels)
        quarterly = quarterly_counts(adjusted, labels)
        if len(quarterly) < 12:
            continue
        for origin in range(8, len(quarterly) - 2):
            opportunities += 1
            window = quarterly[origin - 8:origin]
            baseline = sum(window) / len(window)
            if baseline <= 0:
                continue
            zscore = (quarterly[origin] - baseline) / (baseline ** 0.5)
            if zscore >= 3.5:
                alerts += 1
    return {"alerts": alerts, "opportunities": opportunities,
            "alert_rate": alerts / opportunities if opportunities else None}


def run_monthly_sensitivity(cells: dict[tuple[str, str], list[int]], labels: list[int],
                            factors: dict[int, float] | None) -> dict[str, Any]:
    """The same injection design as every previous run, applied to raw or adjusted monthly counts."""
    rng = random.Random(5150)
    per_shape: dict[str, list[int]] = {shape: [0, 0] for shape in SHAPES}
    alerts = 0
    injections = 0
    for counts in cells.values():
        adjusted = counts if factors is None else adjust(counts, factors, labels)
        candidates = [month for month in range(MIN_HISTORY, MONTHS - 6)]
        if not candidates:
            continue
        for _ in range(4):
            origin = candidates[rng.randrange(len(candidates))]
            baseline_counts = adjusted[origin - BASELINE_MONTHS:origin]
            if not baseline_counts:
                continue
            baseline = sum(baseline_counts) / len(baseline_counts)
            if baseline <= 0:
                continue
            elevation = EFFECT_MULTIPLIER * baseline
            for shape in SHAPES:
                injected = inject(adjusted, origin, shape, elevation)
                injections += 1
                alert = detect(injected, origin)
                if alert is None:
                    continue
                alerts += 1
                per_shape[shape][1] += 1
                if classify_posthoc(injected, alert, baseline) == shape:
                    per_shape[shape][0] += 1
    return {"injections": injections, "alerts": alerts,
            "alert_rate": alerts / injections if injections else None,
            "class_accuracy": {shape: (hit / total if total else None)
                               for shape, (hit, total) in per_shape.items()},
            "class_totals": {shape: total for shape, (_, total) in per_shape.items()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b074/seasonality.json")
    args = parser.parse_args(argv)

    cells, lane_totals = build_cells()
    labels = month_labels(MONTHS)
    print(f"cells: {len(cells)}; lane events: {sum(lane_totals)}; months: {MONTHS}")

    factors = month_factors(lane_totals)
    print(f"month factors: spread {factors['spread_max_over_min']:.3f}; "
          f"january {factors['factors']['0']:.3f}; december {factors['factors']['11']:.3f}")
    perm = permutation_test(lane_totals, factors["dispersion"], random.Random(SEED), PERMUTATIONS)
    print(f"permutation p = {perm['p_value']:.4f} ({perm['exceedances']} of {PERMUTATIONS})")

    boundary = boundary_artifact(lane_totals)
    print(f"boundary: start {boundary['quarter_start_vs_interior']:.3f}x, "
          f"end {boundary['quarter_end_vs_interior']:.3f}x of interior months")

    numeric = {month: factors["factors"][str(month)] for month in range(12)}
    raw = run_quarterly_alerts(cells, labels, None)
    adjusted = run_quarterly_alerts(cells, labels, numeric)
    raw_monthly = run_monthly_sensitivity(cells, labels, None)
    adjusted_monthly = run_monthly_sensitivity(cells, labels, numeric)
    print(f"quarterly raw:      alerts {raw['alerts']}/{raw['opportunities']} "
          f"rate {raw['alert_rate']:.4f}")
    print(f"quarterly adjusted: alerts {adjusted['alerts']}/{adjusted['opportunities']} "
          f"rate {adjusted['alert_rate']:.4f}")
    print(f"monthly injections raw {raw_monthly['injections']}: alert rate {raw_monthly['alert_rate']:.4f} "
          f"class {raw_monthly['class_accuracy']}")
    print(f"monthly injections adj {adjusted_monthly['injections']}: "
          f"alert rate {adjusted_monthly['alert_rate']:.4f} class {adjusted_monthly['class_accuracy']}")

    difference = raw["alert_rate"] - adjusted["alert_rate"]
    underpowered = raw["opportunities"] < 200
    if underpowered:
        verdict = "UNDERPOWERED - quantified direction only, no claim about magnitude"
    elif difference > FAR_MATERIAL:
        verdict = ("ALERT RATE OVERSTATES - adjustment lowers the observed alert rate materially; the 0.0179 "
                   "figure must be reported as an upper bound")
    else:
        verdict = "ALERT RATE IS AN UPPER BOUND - adjustment does not lower the observed rate materially"

    payload = {
        "design": {"decision": "research/DECISIONS.md D-072 (pre-registered)",
                   "months": MONTHS, "permutations": PERMUTATIONS, "seed": SEED,
                   "far_material_difference": FAR_MATERIAL},
        "month_factors": factors,
        "permutation": perm,
        "boundary_artifact": boundary,
        "quarterly_raw": raw,
        "quarterly_adjusted": adjusted,
        "monthly_raw": raw_monthly,
        "monthly_adjusted": adjusted_monthly,
        "difference": difference,
        "verdict": verdict,
        "factors_within_a_quarter": {
            "q1": [factors["factors"][str(month)] for month in (0, 1, 2)],
            "q2": [factors["factors"][str(month)] for month in (3, 4, 5)],
            "q3": [factors["factors"][str(month)] for month in (6, 7, 8)],
            "q4": [factors["factors"][str(month)] for month in (9, 10, 11)],
        },
    }
    write_json(Path(args.out), payload)
    print(f"verdict: {verdict}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
