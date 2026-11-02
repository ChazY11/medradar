"""B-062: third-unit validation of the promotion rule at market-aggregate (track) level.

Pre-registered in research/DECISIONS.md D-056 before this script was first run.

The rule has been tested on company cells, legal-entity cells and a second recording process (job postings) -
all sparse counting regimes. This run applies the identical detector, classifier, shapes and 3x elevation to
**monthly counts per technology track**, summed across companies: 38 tracks, all eligible, median 270 events
per track. If the rule holds here it survives a ~1000x change in counting density; if it does not, the rule is
recorded as calibrated for sparse series and not transferable to aggregated ones.

Usage:
    python experiments/b026/validate_track_domain.py
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
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
from experiments.b027.build_profiles import LANE  # noqa: E402
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import month_index  # noqa: E402

ORIGINS_PER_TRACK = 3
SEED = 5150
DECLARED_PRECISION = 0.85
DECLARED_BALANCED = 0.50
UNDERPOWERED_INTERVAL = 0.30


def build_track_series() -> dict[str, list[int]]:
    events = load_regulatory_events(LANE)
    series: dict[str, list[int]] = defaultdict(lambda: [0] * WINDOW_MONTHS)
    for event in events:
        track = event.get("track_id")
        index = month_index(event["day"])
        if track and index is not None:
            series[track][index] += 1
    return dict(series)


def bootstrap_tracks(records: list[dict[str, Any]], rng: random.Random,
                     reps: int) -> dict[str, Any]:
    """Resample tracks (the units) with replacement; returns intervals on the headline metrics."""
    names = sorted({record["company"] for record in records})
    balanced, precision = [], []
    for _ in range(reps):
        sample: list[dict[str, Any]] = []
        for _ in range(len(names)):
            chosen = names[rng.randrange(len(names))]
            sample.extend(record for record in records if record["company"] == chosen)
        result = metrics(confusion([record for record in sample
                                    if record["prediction"] in SHAPES]))
        if result["balanced_accuracy"] is not None:
            balanced.append(result["balanced_accuracy"])
        if result["sustained_precision"] is not None:
            precision.append(result["sustained_precision"])

    def interval(values):
        if not values:
            return [None, None]
        values.sort()
        return [values[int(0.025 * len(values))],
                values[min(len(values) - 1, int(0.975 * len(values)))]]

    return {"balanced_ci": interval(balanced), "precision_ci": interval(precision),
            "tracks": len(names), "reps": reps}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b026/validate_track_domain.json")
    args = parser.parse_args(argv)

    rng = random.Random(SEED)
    series = build_track_series()
    eligible = {track: counts for track, counts in series.items()
                if sum(counts[:MIN_HISTORY]) >= MIN_BASELINE_RATE * MIN_HISTORY}
    print(f"tracks: {len(series)}; eligible: {len(eligible)}; "
          f"median events per track: {sorted(sum(c) for c in series.values())[len(series) // 2]}")

    records: list[dict[str, Any]] = []
    for track, counts in sorted(eligible.items()):
        candidates = [month for month in range(MIN_HISTORY, WINDOW_MONTHS - MIN_TAIL)]
        if not candidates:
            continue
        draws = ORIGINS_PER_TRACK if len(candidates) >= ORIGINS_PER_TRACK else 1
        origins = [candidates[rng.randrange(len(candidates))] for _ in range(draws)]
        for origin in origins:
            baseline_counts = counts[origin - BASELINE_MONTHS:origin]
            if not baseline_counts:
                continue
            baseline_rate = sum(baseline_counts) / len(baseline_counts)
            if baseline_rate <= 0:
                continue
            elevation = EFFECT_MULTIPLIER * baseline_rate
            for shape in SHAPES:
                injected = inject(counts, origin, shape, elevation)
                alert = detect(injected, origin)
                records.append({
                    "company": track, "truth": shape,
                    "prediction": ("no_alert" if alert is None
                                   else classify_posthoc(injected, alert, baseline_rate)),
                    "alert": alert,
                })

    scored = [record for record in records
              if record["alert"] is not None and record["prediction"] in SHAPES]
    matrix = confusion(scored)
    result = metrics(matrix)
    boot = bootstrap_tracks(scored, random.Random(SEED + 1), BOOTSTRAPS)

    precision_ok = (result["sustained_precision"] is not None
                    and result["sustained_precision"] >= DECLARED_PRECISION)
    balanced_ok = (result["balanced_accuracy"] is not None
                   and result["balanced_accuracy"] >= DECLARED_BALANCED)
    width = (boot["precision_ci"][1] - boot["precision_ci"][0]
             if boot["precision_ci"][0] is not None else None)
    underpowered = width is not None and width > UNDERPOWERED_INTERVAL
    if underpowered:
        verdict = ("UNDERPOWERED - the precision interval is wider than the declared tolerance, so "
                   "neither consistency nor inconsistency may be claimed")
    elif precision_ok and balanced_ok:
        verdict = "CONSISTENT at market-aggregate level"
    else:
        verdict = ("NOT CONSISTENT - the rule is count-regime dependent and must not be transferred to "
                   "aggregated series without re-measurement")

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-056 (pre-registered)",
            "unit": "technology track (monthly counts summed across companies)",
            "origins_per_track": ORIGINS_PER_TRACK, "seed": SEED,
            "classifier_window": "two months after the alert, alert month excluded",
            "declared_precision": DECLARED_PRECISION,
            "declared_balanced_accuracy": DECLARED_BALANCED,
            "underpowered_interval": UNDERPOWERED_INTERVAL,
            "bootstrap": "tracks resampled (units are not nested)",
        },
        "counts": {"tracks": len(series), "eligible": len(eligible),
                   "records": len(records),
                   "alerts": sum(1 for record in records if record["alert"] is not None),
                   "scored": len(scored)},
        "confusion": matrix,
        "metrics": result,
        "bootstrap": boot,
        "decision": {"precision_ok": precision_ok, "balanced_ok": balanced_ok,
                     "interval_width": width, "underpowered": underpowered, "verdict": verdict},
    }
    write_json(Path(args.out), payload)

    print("\nconfusion (rows = truth, columns = predicted)")
    print("truth   " + "".join(shape.rjust(10) for shape in SHAPES))
    for shape in SHAPES:
        print(f"{shape:8s}" + "".join(str(matrix[shape][predicted]).rjust(10)
                                     for predicted in SHAPES))
    print(f"\nbalanced accuracy = {result['balanced_accuracy']:.3f} "
          f"ci={[None if v is None else round(v, 3) for v in boot['balanced_ci']]}")
    print(f"sustained precision = {result['sustained_precision']:.3f} "
          f"ci={[None if v is None else round(v, 3) for v in boot['precision_ci']]} "
          f"base rate = {result['sustained_base_rate']:.3f}")
    print(f"recalls: {result['recalls']}")
    print(f"decision: {verdict}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
