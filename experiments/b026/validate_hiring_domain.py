"""B-059: second-domain validation of the promotion rule on the archived-hiring lane.

Pre-registered in research/DECISIONS.md D-052 before this script was first run.

The rule was confirmed on company cells and on legal-entity cells, but both are the same corpus (FDA
premarket submissions). This run applies the identical detector, classifier, shapes and 3x elevation to
**seven company-level monthly job-posting series** from the archived-hiring lane - a different recording
process - and reads the result against a rule fixed in advance. Seven series is a declared power limitation.

Usage:
    python experiments/b026/validate_hiring_domain.py
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
from experiments.cycle2_coverage.panel import write_json  # noqa: E402

PANEL = Path("experiments/b030/hiring_panel_v2.json")
ORIGINS_PER_SERIES = 3
SEED = 9091
DECLARED_PRECISION = 0.85
DECLARED_BALANCED = 0.50
UNDERPOWERED_INTERVAL = 0.30


def load_series() -> dict[str, list[int]]:
    """Company monthly posting counts mapped onto the 119-month regulatory window."""
    payload = json.loads(PANEL.read_text(encoding="utf-8"))
    series: dict[str, list[int]] = {}
    for company, block in payload["companies"].items():
        monthly = block.get("monthly") or {}
        if not monthly:
            continue
        counts = [0] * WINDOW_MONTHS
        for key, value in monthly.items():
            text = str(key).replace("-", "")
            if len(text) != 6:
                continue
            year, month = int(text[:4]), int(text[4:6])
            index = (year - 2016) * 12 + (month - 11)
            if index < 0:
                index = (year - 2016) * 12 + (month + 1)
            if 0 <= index < WINDOW_MONTHS:
                counts[index] += int(value)
        if sum(counts) > 0:
            series[company] = counts
    return series


def eligible(series: dict[str, list[int]]) -> dict[str, list[int]]:
    selected = {}
    for company, counts in series.items():
        if sum(counts[:MIN_HISTORY]) < MIN_BASELINE_RATE * MIN_HISTORY:
            continue
        selected[company] = counts
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b026/validate_hiring_domain.json")
    args = parser.parse_args(argv)

    rng = random.Random(SEED)
    series = load_series()
    selected = eligible(series)
    print(f"hiring series: {len(series)}; eligible under the unchanged floors: {len(selected)} "
          f"({', '.join(sorted(selected))})")

    records: list[dict[str, Any]] = []
    for company, counts in sorted(selected.items()):
        candidates = [month for month in range(MIN_HISTORY, WINDOW_MONTHS - MIN_TAIL)]
        draws = ORIGINS_PER_SERIES if len(candidates) >= ORIGINS_PER_SERIES else 1
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
                    records.append({"company": company, "truth": shape,
                                    "prediction": "no_alert", "alert": None})
                    continue
                records.append({"company": company, "truth": shape,
                                "prediction": classify_posthoc(injected, alert, baseline_rate),
                                "alert": alert})

    scored = [record for record in records
              if record["alert"] is not None and record["prediction"] in SHAPES]
    matrix = confusion(scored)
    result = metrics(matrix)
    boot = bootstrap(scored, random.Random(SEED + 1), BOOTSTRAPS)

    precision_ok = (result["sustained_precision"] is not None
                    and result["sustained_precision"] >= DECLARED_PRECISION)
    balanced_ok = (result["balanced_accuracy"] is not None
                   and result["balanced_accuracy"] >= DECLARED_BALANCED)
    interval_width = None
    if boot["sustained_precision_ci"][0] is not None:
        interval_width = boot["sustained_precision_ci"][1] - boot["sustained_precision_ci"][0]
    underpowered = interval_width is not None and interval_width > UNDERPOWERED_INTERVAL

    if underpowered:
        verdict = ("UNDERPOWERED - the precision interval is wider than the declared tolerance, "
                   "so neither consistency nor inconsistency may be claimed")
    elif precision_ok and balanced_ok:
        verdict = "CONSISTENT with the confirmed rule on a second domain"
    else:
        verdict = ("NOT CONSISTENT - the rule is corpus-specific and portability claims are withdrawn")

    payload = {
        "design": {
            "decision": "research/DECISIONS.md D-052 (pre-registered)",
            "domain": "archived job-posting lane (Internet Archive CDX)",
            "origins_per_series": ORIGINS_PER_SERIES, "seed": SEED,
            "classifier_window": "two months after the alert, alert month excluded",
            "declared_precision": DECLARED_PRECISION,
            "declared_balanced_accuracy": DECLARED_BALANCED,
            "underpowered_interval": UNDERPOWERED_INTERVAL,
            "power_caveat": "seven eligible series; declared before the run",
        },
        "counts": {"series_available": len(series), "series_eligible": len(selected),
                   "records": len(records),
                   "alerts": sum(1 for record in records if record["alert"] is not None),
                   "scored": len(scored)},
        "confusion": matrix,
        "metrics": result,
        "bootstrap": boot,
        "decision": {"precision_ok": precision_ok, "balanced_ok": balanced_ok,
                     "interval_width": interval_width, "underpowered": underpowered,
                     "verdict": verdict},
    }
    write_json(Path(args.out), payload)

    print("\nconfusion (rows = truth, columns = predicted)")
    print("truth   " + "".join(shape.rjust(10) for shape in SHAPES))
    for shape in SHAPES:
        print(f"{shape:8s}" + "".join(str(matrix[shape][predicted]).rjust(10)
                                     for predicted in SHAPES))
    if result["balanced_accuracy"] is not None:
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
