"""B-054: confirmatory test of the corrected confirmation window on FRESH injections.

Pre-registered in research/DECISIONS.md D-042 before this script was first run.

The discovery run (D-041) chose one origin per cell. This run excludes any injection month within six
months of that discovery origin and draws three fresh origins per cell (seed 2026), so no injected
observation is reused. Same shapes, same magnitudes, same detector; the only difference is the classifier
window, which is now the two months **after** the alert month.

Pre-declared rule (D-042):
  CONFIRMED iff sustained-change precision >= 0.85 AND balanced accuracy >= 0.50 AND the bootstrap lower
  95 % bound on sustained-change precision exceeds the sustained base rate measured here.

Usage:
    python experiments/b026/confirm_window.py
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b026.spike_vs_shift import (  # noqa: E402
    BASELINE_MONTHS,
    BOOTSTRAPS,
    CONFIRMATION_MONTHS,
    EFFECT_MULTIPLIER,
    MIN_HISTORY,
    MIN_TAIL,
    SEED,
    SHAPES,
    SPIKE_FALLBACK,
    WINDOW_MONTHS,
    bootstrap,
    build_cells,
    classify_posthoc,
    confusion,
    detect,
    eligible_cells,
    inject,
    metrics,
)
from experiments.cycle2_coverage.panel import write_json  # noqa: E402

FRESH_ORIGINS_PER_CELL = 3
GUARD_MONTHS = 6
CONFIRM_SEED = 2026
DISCOVERY = Path("experiments/b026/spike_vs_shift.json")

# pre-declared thresholds (D-042)
DECLARED_PRECISION = 0.85
DECLARED_BALANCED = 0.50


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b026/confirm_window.json")
    args = parser.parse_args(argv)

    discovery = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    discovery_origins: dict[str, int] = discovery["discovery_origins"]
    base_rate_discovery = discovery["metrics"]["sustained_base_rate"]

    rng = random.Random(CONFIRM_SEED)
    cells = build_cells()
    eligible = eligible_cells(cells)
    print(f"eligible cells: {len(eligible)}; discovery origins: {len(discovery_origins)}")

    records: list[dict[str, Any]] = []
    reused = 0
    for company, track, counts in eligible:
        key = f"{company}|{track}"
        known = discovery_origins.get(key)
        candidates = [month for month in range(MIN_HISTORY, WINDOW_MONTHS - MIN_TAIL)
                      if known is None or abs(month - known) > GUARD_MONTHS]
        if not candidates:
            continue
        draws = FRESH_ORIGINS_PER_CELL if len(candidates) >= FRESH_ORIGINS_PER_CELL else 1
        origins = [candidates[rng.randrange(len(candidates))] for _ in range(draws)]
        for origin in origins:
            if known is not None and abs(origin - known) <= GUARD_MONTHS:
                reused += 1
            baseline_counts = counts[origin - BASELINE_MONTHS:origin]
            baseline_rate = (sum(baseline_counts) / len(baseline_counts)
                             if baseline_counts else 0.0)
            if baseline_rate <= 0:
                continue
            elevation = EFFECT_MULTIPLIER * baseline_rate
            for shape in SHAPES:
                injected = inject(counts, origin, shape, elevation)
                alert = detect(injected, origin)
                if alert is None:
                    records.append({"company": company, "track": track, "origin": origin,
                                    "truth": shape, "prediction": "no_alert", "alert": None})
                    continue
                prediction = classify_posthoc(injected, alert, baseline_rate)
                records.append({"company": company, "track": track, "origin": origin,
                                "truth": shape, "prediction": prediction, "alert": alert})

    scored = [record for record in records if record["alert"] is not None
              and record["prediction"] in SHAPES]
    matrix = confusion(scored)
    result = metrics(matrix)
    boot = bootstrap(scored, random.Random(SEED), BOOTSTRAPS)

    precision_ok = (result["sustained_precision"] is not None
                    and result["sustained_precision"] >= DECLARED_PRECISION)
    balanced_ok = (result["balanced_accuracy"] is not None
                   and result["balanced_accuracy"] >= DECLARED_BALANCED)
    ci_low = boot["sustained_precision_ci"][0]
    base_rate = result["sustained_base_rate"]
    ci_ok = ci_low is not None and base_rate is not None and ci_low > base_rate
    confirmed = bool(precision_ok and balanced_ok and ci_ok)
    if confirmed:
        verdict = "CONFIRMED"
    elif precision_ok and not balanced_ok:
        verdict = ("PARTIAL - binary promotion confirmed, three-way classification not")
    elif precision_ok and balanced_ok and not ci_ok:
        verdict = "NOT CONFIRMED - precision interval does not clear the base rate"
    else:
        verdict = "NOT CONFIRMED"

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-042 (pre-registered)",
            "fresh_origins_per_cell": FRESH_ORIGINS_PER_CELL,
            "guard_months_around_discovery_origin": GUARD_MONTHS,
            "seed": CONFIRM_SEED, "bootstraps": BOOTSTRAPS,
            "classifier_window": f"months alert+1 .. alert+{CONFIRMATION_MONTHS}",
            "declared_precision": DECLARED_PRECISION,
            "declared_balanced_accuracy": DECLARED_BALANCED,
            "ci_rule": "bootstrap lower 95% bound on sustained precision must exceed the base rate",
        },
        "counts": {"eligible_cells": len(eligible), "records": len(records),
                   "alerts": sum(1 for record in records if record["alert"] is not None),
                   "scored": len(scored), "origins_within_guard": reused,
                   "discovery_sustained_base_rate": base_rate_discovery},
        "confusion": matrix,
        "metrics": result,
        "bootstrap": boot,
        "decision": {"precision_ok": precision_ok, "balanced_ok": balanced_ok, "ci_ok": ci_ok,
                     "confirmed": confirmed, "verdict": verdict},
    }
    write_json(Path(args.out), payload)

    print("\nconfusion (rows = truth, columns = predicted)")
    print("truth   " + "".join(shape.rjust(10) for shape in SHAPES))
    for shape in SHAPES:
        print(f"{shape:8s}" + "".join(str(matrix[shape][predicted]).rjust(10)
                                      for predicted in SHAPES))
    print(f"\nbalanced accuracy = {result['balanced_accuracy']:.3f} "
          f"ci={[None if value is None else round(value, 3) for value in boot['balanced_accuracy_ci']]}")
    print(f"sustained precision = {result['sustained_precision']:.3f} "
          f"ci={[None if value is None else round(value, 3) for value in boot['sustained_precision_ci']]} "
          f"base rate = {result['sustained_base_rate']:.3f}")
    print(f"recalls: {result['recalls']}")
    print(f"decision: {verdict}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
