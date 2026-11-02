"""B-063: controlled density experiment — does thinning a dense series reproduce the ramp scaling?

Pre-registered in research/DECISIONS.md D-058 before this script was first run.

D-057 found ramp recall rising with density ACROSS UNITS (entity 0.117 -> company 0.142 -> hiring 0.300 ->
track 0.396). That is observational: density and unit type vary together. This script holds the unit fixed -
the 38 dense technology-track series - and thins each one by binomial down-sampling at factors 1, 2, 5, 10 and
20, then re-injects the same shapes and re-runs the same detector and classifier.

Pre-declared decision (D-058):
  EXPERIMENTALLY SUPPORTED iff ramp recall is monotonically non-decreasing in density with Spearman rho >= 0.8
  across the five factors AND the interval at tau=1 does not overlap the interval at tau=20.

Usage:
    python experiments/b026/density_experiment.py
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b026.spike_vs_shift import (  # noqa: E402
    BASELINE_MONTHS,
    BOOTSTRAPS,
    EFFECT_MULTIPLIER,
    MIN_BASELINE_RATE,
    MIN_HISTORY,
    MIN_TAIL,
    SHAPES,
    WINDOW_MONTHS,
    classify_posthoc,
    confusion,
    detect,
    inject,
    metrics,
)
from experiments.b026.validate_track_domain import build_track_series  # noqa: E402
from experiments.cycle2_coverage.panel import write_json  # noqa: E402

FACTORS = (1, 2, 5, 10, 20)
ORIGINS_PER_TRACK = 3
SEED = 6161
RHO_FLOOR = 0.8


def thin(counts: list[int], denominator: int, rng: random.Random) -> list[int]:
    """Binomial down-sampling: preserves temporal shape, reduces counts."""
    if denominator == 1:
        return list(counts)
    thinned = []
    for value in counts:
        kept = 0
        for _ in range(int(value)):
            if rng.random() < 1.0 / denominator:
                kept += 1
        thinned.append(kept)
    return thinned


def spearman(values: list[float], ranks: list[float]) -> float | None:
    n = len(values)
    if n < 3:
        return None
    mean_x = sum(values) / n
    mean_y = sum(ranks) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(values, ranks))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in values))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ranks))
    if denom_x == 0 or denom_y == 0:
        return None
    return numerator / (denom_x * denom_y)


def bootstrap_ramp(records: list[dict[str, Any]], rng: random.Random,
                   reps: int) -> list[float | None]:
    names = sorted({record["track"] for record in records})
    values: list[float | None] = []
    for _ in range(reps):
        sample: list[dict[str, Any]] = []
        for _ in range(len(names)):
            chosen = names[rng.randrange(len(names))]
            sample.extend(record for record in records if record["track"] == chosen)
        ramp_rows = [record for record in sample if record["truth"] == "ramp"
                     and record["prediction"] in SHAPES]
        if ramp_rows:
            values.append(sum(1 for record in ramp_rows if record["prediction"] == "ramp")
                          / len(ramp_rows))
    values.sort()
    if not values:
        return [None, None]
    return [values[int(0.025 * len(values))],
            values[min(len(values) - 1, int(0.975 * len(values)))]]


def run_factor(series: dict[str, list[int]], factor: int, *, rng_thin: random.Random,
               seed: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    total_counts = 0
    total_months = 0
    for track, counts in sorted(series.items()):
        thinned = thin(counts, factor, rng_thin)
        total_counts += sum(thinned)
        total_months += len(thinned)
        baseline_history = sum(thinned[:MIN_HISTORY])
        if baseline_history < MIN_BASELINE_RATE * MIN_HISTORY:
            continue
        candidates = [month for month in range(MIN_HISTORY, WINDOW_MONTHS - MIN_TAIL)]
        if not candidates:
            continue
        draws = ORIGINS_PER_TRACK if len(candidates) >= ORIGINS_PER_TRACK else 1
        origins = [candidates[rng.randrange(len(candidates))] for _ in range(draws)]
        for origin in origins:
            baseline_counts = thinned[origin - BASELINE_MONTHS:origin]
            if not baseline_counts:
                continue
            baseline_rate = sum(baseline_counts) / len(baseline_counts)
            if baseline_rate <= 0:
                continue
            elevation = EFFECT_MULTIPLIER * baseline_rate
            for shape in SHAPES:
                injected = inject(thinned, origin, shape, elevation)
                alert = detect(injected, origin)
                records.append({
                    "track": track, "truth": shape,
                    "prediction": ("no_alert" if alert is None
                                   else classify_posthoc(injected, alert, baseline_rate)),
                    "alert": alert,
                })
    density = total_counts / total_months if total_months else 0.0
    return records, {"mean_events_per_series_month": density,
                     "total_events": total_counts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b026/density_experiment.json")
    args = parser.parse_args(argv)

    series = build_track_series()
    print(f"tracks: {len(series)}; base density "
          f"{sum(sum(c) for c in series.values()) / (len(series) * WINDOW_MONTHS):.2f} events/series-month")

    results: dict[str, Any] = {"design": {
        "decision": "research/DECISIONS.md D-058 (pre-registered)",
        "factors": list(FACTORS), "origins_per_track": ORIGINS_PER_TRACK, "seed": SEED,
        "rho_floor": RHO_FLOOR,
        "method": "binomial thinning of dense track series, then inject and classify as before",
    }, "factors": {}}

    for factor in FACTORS:
        rng_thin = random.Random(SEED + factor)
        records, density = run_factor(series, factor, rng_thin=rng_thin, seed=SEED + 1000 + factor)
        scored = [record for record in records
                  if record["alert"] is not None and record["prediction"] in SHAPES]
        matrix = confusion(scored)
        result = metrics(matrix)
        ramp_ci = bootstrap_ramp(scored, random.Random(SEED + 2000 + factor), BOOTSTRAPS)
        results["factors"][str(factor)] = {
            "density": density, "confusion": matrix, "metrics": result,
            "ramp_recall_ci": ramp_ci,
            "alerts": sum(1 for record in records if record["alert"] is not None),
            "scored": len(scored),
        }
        print(f"tau={factor:>2d} density={density['mean_events_per_series_month']:.2f} "
              f"ramp_recall={result['recalls']['ramp']:.3f} "
              f"ci={[None if v is None else round(v, 3) for v in ramp_ci]} "
              f"precision={result['sustained_precision']:.3f} alerts={len(scored)}")

    # test the pre-declared decision
    ramp_recalls = [results["factors"][str(f)]["metrics"]["recalls"]["ramp"] for f in FACTORS]
    densities = [results["factors"][str(f)]["density"]["mean_events_per_series_month"]
                 for f in FACTORS]
    monotone = all(ramp_recalls[index] <= ramp_recalls[index + 1]
                   for index in range(len(ramp_recalls) - 1))
    rho = spearman(densities, ramp_recalls)
    dense_ci = results["factors"][str(FACTORS[0])]["ramp_recall_ci"]
    sparse_ci = results["factors"][str(FACTORS[-1])]["ramp_recall_ci"]
    disjoint = (dense_ci[0] is not None and sparse_ci[1] is not None
                and dense_ci[0] > sparse_ci[1])
    supported = bool(monotone and rho is not None and rho >= RHO_FLOOR and disjoint)
    results["decision"] = {
        "ramp_recalls_by_factor": dict(zip((str(f) for f in FACTORS), ramp_recalls)),
        "densities_by_factor": dict(zip((str(f) for f in FACTORS), densities)),
        "monotone_in_density": monotone, "spearman_rho": rho,
        "dense_vs_sparse_intervals_disjoint": disjoint,
        "supported": supported,
        "verdict": ("EXPERIMENTALLY SUPPORTED - ramp recall is limited by counts, holding the unit fixed"
                    if supported else
                    "NOT SUPPORTED - the cross-unit gradient is a unit effect, not a density effect"),
    }
    write_json(Path(args.out), results)
    print(f"\nspearman rho (density vs ramp recall) = "
          f"{None if rho is None else round(rho, 3)}; monotone={monotone}; "
          f"dense/sparse intervals disjoint={disjoint}")
    print(f"verdict: {results['decision']['verdict']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
