"""B-026: can the SHAPE of an alert be recovered from a two-month confirmation window?

Pre-registered in research/DECISIONS.md D-040 before this script was first run.

Three shapes are injected into real (company, track) monthly series at known months:
    spike       one-month pulse
    level       twelve-month step
    ramp        twelve-month linear increase
A fixed detector alerts when the three-month rate exceeds twice the eighteen-month baseline rate.
A transparent rule then classifies the alert using ONLY the alert month and the two months after it.

Reported: 3x3 confusion matrix, balanced accuracy against the 1/3 chance line, and precision/recall for
the binary decision that matters (promote to "technology change" only if the change is sustained), with
company-clustered bootstrap intervals.

Usage:
    python experiments/b026/spike_vs_shift.py
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b027.build_profiles import LANE, load_families  # noqa: E402
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import WINDOW_MONTHS, month_index  # noqa: E402
from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402

SHAPES = ("spike", "level", "ramp")
RATIO_ALERT = 2.0            # detector: 3-month rate / 18-month baseline rate
RECENT_MONTHS = 3
BASELINE_MONTHS = 18
CONFIRMATION_MONTHS = 2      # classifier may use the alert month and two after it
SPIKE_FALLBACK = 1.5         # below this multiple of baseline the change is called a spike
LEVEL_MONTHS = 12
RAMP_MONTHS = 12
EFFECT_MULTIPLIER = 3.0      # injected elevation relative to baseline rate
MIN_BASELINE_RATE = 0.15     # cells with fewer events than this cannot show an increase
MIN_HISTORY = 24
MIN_TAIL = 16                # months needed after the injection month
BOOTSTRAPS = 2000
SEED = 7


# ------------------------------------------------------------------ series
def build_cells() -> dict[tuple[str, str], list[int]]:
    families = load_families()
    events = load_regulatory_events(LANE)
    from experiments.detect_v1.streams import load_product_codes

    codes = load_product_codes(LANE)
    entity_to_company = {entity: key for key, family in families.items()
                         for entity in family["entities"]}
    cells: dict[tuple[str, str], list[int]] = defaultdict(list)
    for event in events:
        normalised = normalise_applicant(event.get("applicant_raw"))
        track = event.get("track_id")
        index = month_index(event["day"])
        if not normalised or not track or index is None:
            continue
        company = entity_to_company.get(entity_key(normalised))
        if company is None:
            continue
        cells[(company, track)].append(index)
    for months in cells.values():
        months.sort()
    return dict(cells)


def to_counts(months: list[int]) -> list[int]:
    counts = [0] * WINDOW_MONTHS
    for month in months:
        if 0 <= month < WINDOW_MONTHS:
            counts[month] += 1
    return counts


def eligible_cells(cells: dict[tuple[str, str], list[int]]) -> list[tuple[str, str, list[int]]]:
    eligible = []
    for key, months in cells.items():
        counts = to_counts(months)
        history = sum(counts[:MIN_HISTORY])
        if history < MIN_BASELINE_RATE * MIN_HISTORY:
            continue
        eligible.append((key[0], key[1], counts))
    return eligible


# ------------------------------------------------------------------ injection
def inject(counts: list[int], origin: int, shape: str, elevation: float) -> list[int]:
    """Add a known shape at ``origin``. ``elevation`` is the extra events per month at peak."""
    injected = list(counts)
    peak = max(1, int(round(elevation)))
    if shape == "spike":
        injected[origin] += peak
    elif shape == "level":
        for offset in range(LEVEL_MONTHS):
            if origin + offset < WINDOW_MONTHS:
                injected[origin + offset] += peak
    elif shape == "ramp":
        for offset in range(RAMP_MONTHS):
            position = origin + offset
            if position >= WINDOW_MONTHS:
                break
            height = max(1, int(round(peak * (offset + 1) / RAMP_MONTHS)))
            injected[position] += height
    else:
        raise ValueError(f"unknown shape {shape}")
    return injected


def detect(counts: list[int], origin: int) -> int | None:
    """Return the alert month (first month at/after origin where the detector fires), or None."""
    for month in range(origin, min(origin + 6, WINDOW_MONTHS - 1)):
        recent = sum(counts[max(0, month - RECENT_MONTHS + 1):month + 1])
        baseline_months = counts[max(0, month - RECENT_MONTHS - BASELINE_MONTHS + 1):
                                 month - RECENT_MONTHS + 1]
        if not baseline_months:
            continue
        baseline_rate = sum(baseline_months) / len(baseline_months)
        if baseline_rate <= 0:
            continue
        if (recent / RECENT_MONTHS) >= RATIO_ALERT * baseline_rate:
            return month
    return None


def classify(counts: list[int], alert: int, baseline_rate: float) -> str:
    """Pre-registered rule: the alert month plus the confirmation months (D-040)."""
    window = [counts[month] for month in range(alert, min(alert + CONFIRMATION_MONTHS + 1,
                                                          WINDOW_MONTHS))]
    if not window:
        return "level"
    post_rate = sum(window) / len(window)
    relative = post_rate / baseline_rate if baseline_rate > 0 else 0.0
    if relative < SPIKE_FALLBACK:
        return "spike"
    if len(window) >= 2 and window[-1] > window[0] and relative >= SPIKE_FALLBACK:
        return "ramp"
    return "level"


def classify_posthoc(counts: list[int], alert: int, baseline_rate: float) -> str:
    """Declared post-hoc variant: EXCLUDE the alert month from the confirmation window.

    The pre-registered rule includes the alert month, and for a spike the alert month *is* the pulse,
    so the burst itself inflates the "post" rate and the rule almost never calls a spike. This variant
    tests whether that specification error, rather than the data, explains the failure.
    """
    window = [counts[month] for month in range(alert + 1, min(alert + 1 + CONFIRMATION_MONTHS,
                                                               WINDOW_MONTHS))]
    if not window:
        return "level"
    post_rate = sum(window) / len(window)
    relative = post_rate / baseline_rate if baseline_rate > 0 else 0.0
    if relative < SPIKE_FALLBACK:
        return "spike"
    if len(window) >= 2 and window[-1] > window[0]:
        return "ramp"
    return "level"


# ------------------------------------------------------------------ evaluation
def confusion(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    matrix = {shape: {predicted: 0 for predicted in SHAPES} for shape in SHAPES}
    for record in records:
        matrix[record["truth"]][record["prediction"]] += 1
    return matrix


def metrics(matrix: dict[str, dict[str, int]]) -> dict[str, Any]:
    recalls = {}
    for shape in SHAPES:
        total = sum(matrix[shape].values())
        recalls[shape] = (matrix[shape][shape] / total) if total else None
    valid = [value for value in recalls.values() if value is not None]
    balanced = sum(valid) / len(valid) if valid else None
    sustained = [record for record in SHAPES if record in ("level", "ramp")]
    true_positive = sum(matrix[shape][predicted] for shape in sustained for predicted in sustained)
    predicted_positive = sum(matrix[shape][predicted] for shape in SHAPES for predicted in sustained)
    actual_positive = sum(sum(matrix[shape].values()) for shape in sustained)
    precision = (true_positive / predicted_positive) if predicted_positive else None
    recall = (true_positive / actual_positive) if actual_positive else None
    return {"recalls": recalls, "balanced_accuracy": balanced,
            "sustained_precision": precision, "sustained_recall": recall,
            "sustained_base_rate": (actual_positive / sum(
                sum(row.values()) for row in matrix.values())) if matrix else None}


def bootstrap(records: list[dict[str, Any]], rng: random.Random, reps: int) -> dict[str, Any]:
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_company[record["company"]].append(record)
    companies = sorted(by_company)
    balanced_values, precision_values = [], []
    for _ in range(reps):
        sample: list[dict[str, Any]] = []
        for _ in range(len(companies)):
            sample.extend(by_company[companies[rng.randrange(len(companies))]])
        result = metrics(confusion(sample))
        if result["balanced_accuracy"] is not None:
            balanced_values.append(result["balanced_accuracy"])
        if result["sustained_precision"] is not None:
            precision_values.append(result["sustained_precision"])
    def interval(values):
        if not values:
            return [None, None]
        values.sort()
        return [values[int(0.025 * len(values))],
                values[min(len(values) - 1, int(0.975 * len(values)))]]
    return {"balanced_accuracy_ci": interval(balanced_values),
            "sustained_precision_ci": interval(precision_values),
            "reps": reps, "companies": len(companies)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b026/spike_vs_shift.json")
    args = parser.parse_args(argv)

    rng = random.Random(SEED)
    cells = build_cells()
    eligible = eligible_cells(cells)
    print(f"cells: {len(cells)}; eligible with a measurable baseline: {len(eligible)}")

    records: list[dict[str, Any]] = []
    discovery_origins: dict[str, int] = {}
    for company, track, counts in eligible:
        origins = [month for month in range(MIN_HISTORY, WINDOW_MONTHS - MIN_TAIL)]
        if not origins:
            continue
        origin = origins[rng.randrange(len(origins))]
        discovery_origins[f"{company}|{track}"] = origin
        baseline_counts = counts[origin - BASELINE_MONTHS:origin]
        baseline_rate = sum(baseline_counts) / len(baseline_counts) if baseline_counts else 0.0
        if baseline_rate <= 0:
            continue
        elevation = EFFECT_MULTIPLIER * baseline_rate
        for shape in SHAPES:
            injected = inject(counts, origin, shape, elevation)
            alert = detect(injected, origin)
            if alert is None:
                records.append({"company": company, "track": track, "true_origin": origin,
                                "truth": shape, "prediction": "no_alert", "alert": None})
                continue
            prediction = classify(injected, alert, baseline_rate)
            records.append({"company": company, "track": track, "true_origin": origin,
                            "truth": shape, "prediction": prediction, "alert": alert,
                            "prediction_posthoc": classify_posthoc(injected, alert,
                                                                   baseline_rate)})
    alerted = [record for record in records if record["alert"] is not None]
    print(f"injections: {len(records)}; alerts: {len(alerted)} "
          f"({len(alerted) / max(len(records), 1):.0%} of injections)")

    scored = [record for record in alerted if record["prediction"] in SHAPES]
    matrix = confusion(scored)
    result = metrics(matrix)
    boot = bootstrap(scored, rng, BOOTSTRAPS)

    # declared post-hoc variant: confirmation window excludes the alert month
    posthoc_records = [{"company": record["company"], "truth": record["truth"],
                        "prediction": record.get("prediction_posthoc", "level")}
                       for record in scored]
    matrix_posthoc = confusion(posthoc_records)
    result_posthoc = metrics(matrix_posthoc)
    boot_posthoc = bootstrap(posthoc_records, random.Random(SEED + 1), BOOTSTRAPS)

    # reference point: a rule that always says "level"
    always_level = [{"company": record["company"], "truth": record["truth"],
                     "prediction": "level"} for record in scored]
    matrix_always = confusion(always_level)
    result_always = metrics(matrix_always)

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-040 (pre-registered)",
            "shapes": list(SHAPES), "ratio_alert": RATIO_ALERT,
            "recent_months": RECENT_MONTHS, "baseline_months": BASELINE_MONTHS,
            "confirmation_months": CONFIRMATION_MONTHS, "spike_fallback": SPIKE_FALLBACK,
            "effect_multiplier": EFFECT_MULTIPLIER, "seed": SEED, "bootstraps": BOOTSTRAPS,
            "chance_balanced_accuracy": 1 / len(SHAPES),
        },
        "counts": {"cells": len(cells), "eligible": len(eligible), "injections": len(records),
                   "alerts": len(alerted),
                   "alerts_by_truth": {shape: sum(1 for record in alerted if record["truth"] == shape)
                                       for shape in SHAPES}},
        "confusion": matrix,
        "metrics": result,
        "bootstrap": boot,
        "posthoc_variant": {
            "description": ("confirmation window excludes the alert month, so a spike's own pulse "
                            "cannot inflate the post-alert rate"),
            "confusion": matrix_posthoc, "metrics": result_posthoc,
            "bootstrap": boot_posthoc,
        },
        "always_level_baseline": {"confusion": matrix_always, "metrics": result_always},
        "discovery_origins": discovery_origins,
        "prediction_distribution": {shape: sum(1 for record in alerted
                                               if record["prediction"] == shape)
                                    for shape in (*SHAPES, "no_alert")},
    }
    write_json(Path(args.out), payload)

    print("\nconfusion (rows = truth, columns = predicted)")
    print("truth   " + "".join(shape.rjust(10) for shape in SHAPES))
    for shape in SHAPES:
        print(f"{shape:8s}" + "".join(str(matrix[shape][predicted]).rjust(10)
                                      for predicted in SHAPES))
    print(f"\nbalanced accuracy = {result['balanced_accuracy']:.3f} "
          f"ci={[None if value is None else round(value, 3) for value in boot['balanced_accuracy_ci']]} "
          f"(chance {1 / len(SHAPES):.3f})")
    print(f"sustained precision = {result['sustained_precision']:.3f} "
          f"recall = {result['sustained_recall']:.3f} "
          f"base rate = {result['sustained_base_rate']:.3f}")

    print("\n== post-hoc variant: confirmation window excludes the alert month ==")
    print("truth   " + "".join(shape.rjust(10) for shape in SHAPES))
    for shape in SHAPES:
        print(f"{shape:8s}" + "".join(str(matrix_posthoc[shape][predicted]).rjust(10)
                                      for predicted in SHAPES))
    print(f"balanced accuracy = {result_posthoc['balanced_accuracy']:.3f} "
          f"ci={[None if value is None else round(value, 3) for value in boot_posthoc['balanced_accuracy_ci']]}")
    print(f"sustained precision = {result_posthoc['sustained_precision']:.3f} "
          f"recall = {result_posthoc['sustained_recall']:.3f}")
    print(f"\n== reference: always predict level ==")
    print(f"balanced accuracy = {result_always['balanced_accuracy']:.3f} "
          f"sustained precision = {result_always['sustained_precision']:.3f}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
