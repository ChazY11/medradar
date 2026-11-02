"""B-064: confirm the density scaling with a robust criterion on FRESH draws.

Pre-registered in research/DECISIONS.md D-060 before this script was first run.

The first controlled density experiment (D-058/D-059) failed its bar on strict monotonicity and interval
separation, although ramp recall halved with density and rank correlation was 0.882. D-059 recorded that the
criterion, not the data, was the weak part. This run repeats the design with ENTIRELY FRESH random draws and a
criterion fixed in advance:

  CONFIRMED iff Spearman rho(density, ramp recall) >= 0.8
           AND dense ramp recall (tau=1) >= 2 x sparse ramp recall (tau=20)
  (no strict-monotonicity clause - that gate was the defect)

Disclosure: this is a revised pre-registration after a failure, and any confirmation must be stated that way.

Usage:
    python experiments/b026/density_confirm.py
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b026.density_experiment import (  # noqa: E402
    FACTORS,
    ORIGINS_PER_TRACK,
    bootstrap_ramp,
    run_factor,
    spearman,
)
from experiments.b026.spike_vs_shift import SHAPES, confusion, metrics  # noqa: E402
from experiments.b026.validate_track_domain import build_track_series  # noqa: E402
from experiments.cycle2_coverage.panel import write_json  # noqa: E402

THINNING_SEED = 7171
ORIGIN_SEED = 8181
BOOTSTRAP_SEED = 9191
RHO_FLOOR = 0.8
EFFECT_RATIO_FLOOR = 2.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b026/density_confirm.json")
    args = parser.parse_args(argv)

    series = build_track_series()
    print(f"tracks: {len(series)}; fresh thinning seed {THINNING_SEED}")

    results: dict[str, Any] = {"design": {
        "decision": "research/DECISIONS.md D-060 (revised pre-registration after D-059)",
        "factors": list(FACTORS), "origins_per_track": ORIGINS_PER_TRACK,
        "thinning_seed": THINNING_SEED, "origin_seed": ORIGIN_SEED,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "rho_floor": RHO_FLOOR, "effect_ratio_floor": EFFECT_RATIO_FLOOR,
        "criterion": "rho >= 0.8 AND dense ramp recall >= 2 x sparse ramp recall; no monotonicity clause",
        "disclosure": "revised criterion after D-059 failed; fresh draws only",
    }, "factors": {}}

    for index, factor in enumerate(FACTORS):
        rng_thin = random.Random(THINNING_SEED + factor)
        records, density = run_factor(series, factor, rng_thin=rng_thin,
                                      seed=ORIGIN_SEED + index * 10)
        scored = [record for record in records
                  if record["alert"] is not None and record["prediction"] in SHAPES]
        matrix = confusion(scored)
        result = metrics(matrix)
        ramp_ci = bootstrap_ramp(scored, random.Random(BOOTSTRAP_SEED + index), 2000)
        results["factors"][str(factor)] = {
            "density": density, "confusion": matrix, "metrics": result,
            "ramp_recall_ci": ramp_ci, "scored": len(scored),
        }
        print(f"tau={factor:>2d} density={density['mean_events_per_series_month']:.2f} "
              f"ramp_recall={result['recalls']['ramp']:.3f} "
              f"ci={[None if v is None else round(v, 3) for v in ramp_ci]} "
              f"precision={result['sustained_precision']:.3f} scored={len(scored)}")

    ramp_recalls = [results["factors"][str(f)]["metrics"]["recalls"]["ramp"] for f in FACTORS]
    densities = [results["factors"][str(f)]["density"]["mean_events_per_series_month"]
                 for f in FACTORS]
    rho = spearman(densities, ramp_recalls)
    dense_recall = ramp_recalls[0]
    sparse_recall = ramp_recalls[-1]
    ratio = (dense_recall / sparse_recall) if sparse_recall else None
    rho_ok = rho is not None and rho >= RHO_FLOOR
    effect_ok = ratio is not None and ratio >= EFFECT_RATIO_FLOOR
    confirmed = bool(rho_ok and effect_ok)
    results["decision"] = {
        "rho": rho, "rho_ok": rho_ok,
        "dense_recall": dense_recall, "sparse_recall": sparse_recall, "effect_ratio": ratio,
        "effect_ok": effect_ok, "confirmed": confirmed,
        "verdict": ("CONFIRMED under the revised criterion on fresh draws - ramp recoverability is limited by "
                    "counts, holding the unit fixed (post-failure revised criterion; disclose as such)"
                    if confirmed else
                    "NOT CONFIRMED - the density scaling remains suggestive only and no density floor may be "
                    "stated"),
    }
    write_json(Path(args.out), results)
    print(f"\nrho={None if rho is None else round(rho, 3)} (floor {RHO_FLOOR}); "
          f"dense={dense_recall:.3f} sparse={sparse_recall:.3f} "
          f"ratio={None if ratio is None else round(ratio, 2)}x (floor {EFFECT_RATIO_FLOOR}x)")
    print(f"verdict: {results['decision']['verdict']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
