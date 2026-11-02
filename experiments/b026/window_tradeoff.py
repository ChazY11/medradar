"""B-058: confirmation-window sensitivity analysis for the ramp class.

Pre-registered in research/DECISIONS.md D-050 before this script was first run.

The confirmed promotion rule uses a TWO-MONTH confirmation window. It separates spike from sustained well
but cannot separate ramp from level shift (ramp recall 0.117-0.142). A ramp keeps growing, so a longer
window might help - at the cost of slower decisions.

This is a SENSITIVITY ANALYSIS, not a confirmation: the window grid was fixed in advance, and any window that
looks better can only be proposed for re-pre-registration, never used directly.

Recommendation rule (D-050): worth re-pre-registering only if ramp recall > 0.40 WITH sustained precision
>= 0.85 on BOTH units (company and entity).

Usage:
    python experiments/b026/window_tradeoff.py
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b026.confirm_entity_cells import build_entity_cells, to_counts  # noqa: E402
from experiments.b026.spike_vs_shift import (  # noqa: E402
    BASELINE_MONTHS,
    EFFECT_MULTIPLIER,
    MIN_BASELINE_RATE,
    MIN_HISTORY,
    MIN_TAIL,
    SEED,
    SHAPES,
    SPIKE_FALLBACK,
    WINDOW_MONTHS,
    build_cells,
    detect,
    eligible_cells,
    inject,
    load_families,
)
from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from medradar.intelligence.promotion import classify_shape  # noqa: E402

WINDOWS = (1, 2, 3, 4, 6)
ORIGINS_PER_CELL = 3
RECOMMEND_RAMP_RECALL = 0.40
RECOMMEND_PRECISION = 0.85


def classify_with_window(counts: list[int], alert: int, baseline_rate: float,
                         window: int) -> str:
    """Same rule as the confirmed one, but with a configurable confirmation window (months)."""
    following = [counts[month] for month in range(alert + 1,
                                                   min(alert + 1 + window, WINDOW_MONTHS))]
    shape = classify_shape(following, baseline_rate, quarters=len(following),
                           floor=SPIKE_FALLBACK)
    return shape["shape"] if shape["shape"] in SHAPES else "level"


def run_unit(cells: list[tuple[str, str, list[int]]], company_of, *, seed: int,
             window: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    for key_a, key_b, counts in cells:
        company = company_of(key_a)
        candidates = [month for month in range(MIN_HISTORY, WINDOW_MONTHS - MIN_TAIL)]
        if not candidates:
            continue
        draws = ORIGINS_PER_CELL if len(candidates) >= ORIGINS_PER_CELL else 1
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
                if alert is None:
                    continue
                records.append({"company": company, "truth": shape,
                                "prediction": classify_with_window(injected, alert,
                                                                   baseline_rate, window)})
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    matrix = {shape: {other: 0 for other in SHAPES} for shape in SHAPES}
    for record in records:
        if record["prediction"] in SHAPES:
            matrix[record["truth"]][record["prediction"]] += 1
    recall = {}
    for shape in SHAPES:
        total = sum(matrix[shape].values())
        recall[shape] = (matrix[shape][shape] / total) if total else None
    valid = [value for value in recall.values() if value is not None]
    balanced = sum(valid) / len(valid) if valid else None
    sustained = ("level", "ramp")
    true_positive = sum(matrix[shape][other] for shape in sustained for other in sustained)
    predicted_positive = sum(matrix[shape][other] for shape in SHAPES for other in sustained)
    actual_positive = sum(sum(matrix[shape].values()) for shape in sustained)
    return {"matrix": matrix, "recall": recall, "balanced_accuracy": balanced,
            "sustained_precision": (true_positive / predicted_positive)
            if predicted_positive else None,
            "sustained_recall": (true_positive / actual_positive) if actual_positive else None,
            "ramp_as_level": matrix["ramp"]["level"], "ramp_as_ramp": matrix["ramp"]["ramp"],
            "alerts": sum(sum(row.values()) for row in matrix.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b026/window_tradeoff.json")
    args = parser.parse_args(argv)

    families = load_families()
    entity_to_company = {entity: key for key, family in families.items()
                         for entity in family["entities"]}

    company_cells = [(company, track, to_counts(months))
                     for company, track, months in build_cells_items()]
    company_eligible = [item for item in company_cells
                        if sum(item[2][:MIN_HISTORY]) >= MIN_BASELINE_RATE * MIN_HISTORY]
    entity_cells = [(entity, track, to_counts(months))
                    for (entity, track), months in build_entity_cells().items()]
    entity_eligible = [item for item in entity_cells
                       if sum(item[2][:MIN_HISTORY]) >= MIN_BASELINE_RATE * MIN_HISTORY]
    print(f"company cells eligible: {len(company_eligible)}; "
          f"entity cells eligible: {len(entity_eligible)}")

    results: dict[str, Any] = {"design": {
        "decision": "research/DECISIONS.md D-050 (sensitivity analysis, not a confirmation)",
        "windows_months": list(WINDOWS), "origins_per_cell": ORIGINS_PER_CELL,
        "company_seed": 7071, "entity_seed": 7072,
        "recommend_ramp_recall": RECOMMEND_RAMP_RECALL,
        "recommend_precision": RECOMMEND_PRECISION,
        "alert_month_excluded": True,
    }, "units": {}}

    for unit, cells, company_of, seed in (
        ("company", company_eligible, lambda key: key[0], 7071),
        ("entity", entity_eligible, lambda key: entity_to_company.get(key, "unattributed"), 7072),
    ):
        unit_results: dict[str, Any] = {}
        for window in WINDOWS:
            records = run_unit(cells, company_of, seed=seed, window=window)
            unit_results[str(window)] = summarize(records)
            summary = unit_results[str(window)]
            print(f"{unit:8s} window={window}m: BA="
                  f"{summary['balanced_accuracy']:.3f} ramp_recall="
                  f"{summary['recall']['ramp']:.3f} precision="
                  f"{summary['sustained_precision']:.3f} alerts={summary['alerts']}")
        results["units"][unit] = unit_results

    qualifying = []
    for window in WINDOWS:
        ok = True
        for unit in ("company", "entity"):
            summary = results["units"][unit][str(window)]
            ramp = summary["recall"]["ramp"] or 0.0
            precision = summary["sustained_precision"] or 0.0
            if ramp <= RECOMMEND_RAMP_RECALL or precision < RECOMMEND_PRECISION:
                ok = False
        if ok:
            qualifying.append(window)
    results["recommendation"] = {
        "qualifying_windows": qualifying,
        "verdict": ("consider re-pre-registering the longer window: "
                    + ", ".join(f"{window} months" for window in qualifying))
        if qualifying else
        "no window qualifies: the ramp class stays unrecoverable at this counting rate, "
        "and the policy remains at two months",
    }
    write_json(Path(args.out), results)
    print(f"\nrecommendation: {results['recommendation']['verdict']}")
    print(f"wrote {args.out}")
    return 0


def build_cells_items():
    """Company cells as (company, track, months) without re-deriving counts twice."""
    cells = build_cells()
    return [(company, track, months) for (company, track), months in cells.items()]


if __name__ == "__main__":
    raise SystemExit(main())
