"""B-055: confirm the promotion rule at the LEGAL-ENTITY unit.

Pre-registered in research/DECISIONS.md D-047 before this script was first run.

The D-043 confirmation used fresh injection months but the same 65 company-level cells. This run repeats
the confirmatory design on a different unit of analysis: the legal entity rather than the curated company.
Entity cells are finer, more numerous, and not independent of company cells (each entity belongs to a
company), so the result speaks to aggregation level, not to independence.

Pre-declared rule (identical to D-042): CONFIRMED iff sustained-change precision >= 0.85 AND balanced
accuracy >= 0.50 AND the bootstrap lower 95 % bound on precision exceeds the sustained base rate here.

Usage:
    python experiments/b026/confirm_entity_cells.py
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
    BOOTSTRAPS,
    CONFIRMATION_MONTHS,
    EFFECT_MULTIPLIER,
    MIN_BASELINE_RATE,
    MIN_HISTORY,
    MIN_TAIL,
    SHAPES,
    WINDOW_MONTHS,
    bootstrap,
    classify_posthoc,
    confusion,
    detect,
    inject,
    metrics,
)
from experiments.b026.spike_vs_shift import LANE  # noqa: E402
from experiments.b026.spike_vs_shift import load_families  # noqa: E402
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import month_index  # noqa: E402
from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402

ORIGINS_PER_CELL = 3
ENTITY_SEED = 4040
DECLARED_PRECISION = 0.85
DECLARED_BALANCED = 0.50


def build_entity_cells(detailed_path: Path | None = None) -> dict[tuple[str, str], list[int]]:
    """(legal entity, track) -> sorted month indices. Also records each entity's company."""
    families = load_families()
    entity_to_company = {entity: key for key, family in families.items()
                         for entity in family["entities"]}
    events = load_regulatory_events(LANE)
    cells: dict[tuple[str, str], list[int]] = defaultdict(list)
    for event in events:
        normalised = normalise_applicant(event.get("applicant_raw"))
        track = event.get("track_id")
        index = month_index(event["day"])
        if not normalised or not track or index is None:
            continue
        entity = entity_key(normalised)
        cells[(entity, track)].append(index)
    for months in cells.values():
        months.sort()
    if detailed_path is not None:
        mapping = {entity: company for entity, company in entity_to_company.items()}
        detailed_path.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8", newline="\n")
    return dict(cells)


def to_counts(months: list[int]) -> list[int]:
    counts = [0] * WINDOW_MONTHS
    for month in months:
        if 0 <= month < WINDOW_MONTHS:
            counts[month] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b026/confirm_entity_cells.json")
    args = parser.parse_args(argv)

    families = load_families()
    entity_to_company = {entity: key for key, family in families.items()
                         for entity in family["entities"]}
    rng = random.Random(ENTITY_SEED)
    cells = build_entity_cells()
    print(f"entity-track cells: {len(cells)}")

    eligible: list[tuple[str, str, list[int]]] = []
    for (entity, track), months in cells.items():
        counts = to_counts(months)
        if sum(counts[:MIN_HISTORY]) < MIN_BASELINE_RATE * MIN_HISTORY:
            continue
        eligible.append((entity, track, counts))
    print(f"eligible entity cells: {len(eligible)}")

    records: list[dict[str, Any]] = []
    for entity, track, counts in eligible:
        company = entity_to_company.get(entity, "unattributed")
        candidates = [month for month in range(MIN_HISTORY, WINDOW_MONTHS - MIN_TAIL)]
        if not candidates:
            continue
        draws = ORIGINS_PER_CELL if len(candidates) >= ORIGINS_PER_CELL else 1
        origins = [candidates[rng.randrange(len(candidates))] for _ in range(draws)]
        for origin in origins:
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
                    records.append({"company": company, "entity": entity, "track": track,
                                    "origin": origin, "truth": shape,
                                    "prediction": "no_alert", "alert": None})
                    continue
                prediction = classify_posthoc(injected, alert, baseline_rate)
                records.append({"company": company, "entity": entity, "track": track,
                                "origin": origin, "truth": shape,
                                "prediction": prediction, "alert": alert})

    scored = [record for record in records
              if record["alert"] is not None and record["prediction"] in SHAPES]
    matrix = confusion(scored)
    result = metrics(matrix)
    boot = bootstrap(scored, random.Random(SEED_FOR_BOOTSTRAP := 4041), BOOTSTRAPS)

    precision_ok = (result["sustained_precision"] is not None
                    and result["sustained_precision"] >= DECLARED_PRECISION)
    balanced_ok = (result["balanced_accuracy"] is not None
                   and result["balanced_accuracy"] >= DECLARED_BALANCED)
    ci_low = boot["sustained_precision_ci"][0]
    base_rate = result["sustained_base_rate"]
    ci_ok = ci_low is not None and base_rate is not None and ci_low > base_rate
    if precision_ok and balanced_ok and ci_ok:
        verdict = "CONFIRMED AT ENTITY LEVEL"
    elif precision_ok and not balanced_ok:
        verdict = ("PARTIAL - binary promotion confirmed at entity level, three-way classification not")
    elif precision_ok and balanced_ok and not ci_ok:
        verdict = "NOT CONFIRMED - precision interval does not clear the base rate"
    else:
        verdict = "NOT CONFIRMED AT ENTITY LEVEL"

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-047 (pre-registered)",
            "unit": "legal entity x technology track",
            "origins_per_cell": ORIGINS_PER_CELL, "seed": ENTITY_SEED,
            "classifier_window": f"months alert+1 .. alert+{CONFIRMATION_MONTHS}",
            "declared_precision": DECLARED_PRECISION,
            "declared_balanced_accuracy": DECLARED_BALANCED,
            "dependence_note": ("entity cells nest inside company cells, so this tests aggregation "
                                "level, not independence"),
            "bootstrap_clustering": "by company of the entity",
        },
        "counts": {"entity_cells": len(cells), "eligible": len(eligible),
                   "records": len(records),
                   "alerts": sum(1 for record in records if record["alert"] is not None),
                   "scored": len(scored),
                   "companies": len({record["company"] for record in scored})},
        "confusion": matrix,
        "metrics": result,
        "bootstrap": boot,
        "decision": {"precision_ok": precision_ok, "balanced_ok": balanced_ok, "ci_ok": ci_ok,
                     "verdict": verdict},
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
