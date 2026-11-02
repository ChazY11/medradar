"""B-050: rolling-origin benchmark of the change signal.

Pre-registered in research/DECISIONS.md D-035 before this script was first run.

At each origin month t (every six months, 2019-12 .. 2025-06) the script uses ONLY events up to t to
flag cells as increasing or decreasing, then asks whether the following 12 months actually moved that
way:

    unit        (curated company, technology track) cell
    signal      two-sided exact binomial test, recent 12 months vs prior 12 months, alpha = 0.05
    outcome     does the next 12 months contain more (or fewer) events than the recent block?
    estimand    P(outcome | flagged) vs P(outcome | not flagged), with a company-clustered bootstrap
    baselines   raw ratio rule (recent/prior >= 1.25) and persistence (recent > prior, no test),
                scored on exactly the same cells and origins

No look-ahead: the signal at t never sees data after t.

Usage:
    python experiments/b050/rolling_origin.py
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.b027.build_profiles import (  # noqa: E402
    LANE,
    load_families,
    resolve_regulatory,
)
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.streams import WINDOW_MONTHS, month_index  # noqa: E402
from medradar.intelligence.profile import _binom_two_sided_p  # noqa: E402

ORIGINS = list(range(37, WINDOW_MONTHS - 12, 6))   # 2019-12 .. 2025-06 in month indices
BLOCK = 12
MIN_HISTORY = 8
MIN_PRIOR = 3
ALPHA = 0.05
NAIVE_RATIO = 1.25
BOOTSTRAPS = 2000
SEED = 7


def build_cells() -> dict[tuple[str, str], list[int]]:
    families = load_families()
    events = load_regulatory_events(LANE)
    codes = __import__("experiments.detect_v1.streams", fromlist=["load_product_codes"]).load_product_codes(LANE)
    regulatory = resolve_regulatory(events, families, codes)
    cells: dict[tuple[str, str], list[int]] = defaultdict(list)
    for company, rows in regulatory.items():
        for row in rows:
            # b027.resolve_regulatory emits an ISO date string (it began doing so when the
            # as-of truncation was added in 5dffaab); month_index() expects a date.  Accept
            # both so the benchmark can still be regenerated from the current pipeline.
            raw = row["date"]
            day = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
            index = month_index(day)
            if index is not None:
                cells[(company, row["track"])].append(index)
    for months in cells.values():
        months.sort()
    return dict(cells)


def count_in(months: list[int], low: int, high: int) -> int:
    """Count events with low < month <= high."""
    return sum(1 for month in months if low < month <= high)


def classify(recent: int, prior: int) -> dict[str, Any]:
    total = recent + prior
    p_value = _binom_two_sided_p(recent, total, 0.5) if total else 1.0
    ratio = (recent / prior) if prior else None
    return {
        "recent": recent, "prior": prior, "ratio": ratio, "p_value": p_value,
        "flagged_increase": bool(p_value < ALPHA and recent > prior),
        "flagged_decrease": bool(p_value < ALPHA and recent < prior),
        "naive_increase": bool(ratio is not None and ratio >= NAIVE_RATIO),
        "naive_decrease": bool(ratio is not None and ratio <= 1 / NAIVE_RATIO),
        "persistence_increase": bool(recent > prior),
        "persistence_decrease": bool(recent < prior),
    }


def observations(cells: dict[tuple[str, str], list[int]]) -> list[dict[str, Any]]:
    """Build one row per (company, track, origin).

    Two outcomes are recorded, and the difference between them is the whole point:

    * ``future_increase`` compares the future block with the RECENT block. This is the outcome
      pre-registered in D-035, and it is mechanically biased: a cell is flagged because its recent
      block is unusually high, so the next block tends to be lower even at a constant rate
      (regression to the mean). Its lift cannot separate mean reversion from anti-momentum.
    * ``future_above_baseline`` compares the future block with the cell's own **long-run rate** up to
      the origin (``history_rate * BLOCK``). This removes the mechanical dependence on the recent
      block, so a lift away from 1 here is not produced by the conditioning. It is recorded as a
      declared post-hoc supplement to the pre-registered design.
    """
    rows: list[dict[str, Any]] = []
    for origin in ORIGINS:
        for (company, track), months in cells.items():
            history = [month for month in months if month <= origin]
            if len(history) < MIN_HISTORY:
                continue
            recent = count_in(history, origin - BLOCK, origin)
            prior = count_in(history, origin - 2 * BLOCK, origin - BLOCK)
            if prior < MIN_PRIOR:
                continue
            future = count_in(months, origin, origin + BLOCK)
            history_rate = len(history) / (origin + 1)
            expected_future = history_rate * BLOCK
            signal = classify(recent, prior)
            rows.append({
                "company": company, "track": track, "origin": origin,
                "recent": recent, "prior": prior, "future": future,
                "expected_future": expected_future,
                "future_increase": future > recent,
                "future_decrease": future < recent,
                "future_above_baseline": future > expected_future,
                "future_below_baseline": future < expected_future,
                **signal,
            })
    return rows


def precision(rows: list[dict[str, Any]], flag_key: str, outcome_key: str) -> dict[str, Any]:
    flagged = [row for row in rows if row[flag_key]]
    unflagged = [row for row in rows if not row[flag_key]]
    def rate(subset):
        return (sum(1 for row in subset if row[outcome_key]) / len(subset)) if subset else None
    p_flag = rate(flagged)
    p_unflag = rate(unflagged)
    lift = (p_flag / p_unflag) if p_flag is not None and p_unflag else None
    return {"flagged": len(flagged), "unflagged": len(unflagged),
            "precision_flagged": p_flag, "precision_unflagged": p_unflag, "lift": lift}


def clustered_bootstrap(rows: list[dict[str, Any]], flag_key: str, outcome_key: str,
                        rng: random.Random, reps: int) -> dict[str, Any]:
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_company[row["company"]].append(row)
    companies = sorted(by_company)
    lifts, precisions = [], []
    for _ in range(reps):
        sample: list[dict[str, Any]] = []
        for _ in range(len(companies)):
            sample.extend(by_company[companies[rng.randrange(len(companies))]])
        for row in sample:
            row["_x"] = row[flag_key]
        result = precision(sample, flag_key, outcome_key)
        for row in sample:
            row.pop("_x", None)
        if result["lift"] is not None:
            lifts.append(result["lift"])
        if result["precision_flagged"] is not None:
            precisions.append(result["precision_flagged"])
    lifts.sort()
    precisions.sort()
    def interval(values):
        if not values:
            return [None, None]
        return [values[int(0.025 * len(values))], values[min(len(values) - 1, int(0.975 * len(values)))]]
    return {"lift_ci": interval(lifts), "precision_flagged_ci": interval(precisions),
            "reps": reps, "companies": len(companies)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b050/rolling_origin.json")
    args = parser.parse_args(argv)

    cells = build_cells()
    print(f"cells: {len(cells)}; origins: {ORIGINS[0]}..{ORIGINS[-1]} ({len(ORIGINS)} origins)")
    rows = observations(cells)
    print(f"observations: {len(rows)} (company-origin-cell)")

    rng = random.Random(SEED)
    report: dict[str, Any] = {"design": {
        "decision": "research/DECISIONS.md D-035 (pre-registered)",
        "origins": ORIGINS, "block_months": BLOCK, "min_history": MIN_HISTORY,
        "min_prior": MIN_PRIOR, "alpha": ALPHA, "naive_ratio": NAIVE_RATIO,
        "bootstraps": BOOTSTRAPS, "seed": SEED,
        "outcome": "future 12-month count vs recent 12-month count",
    }, "counts": {"cells": len(cells), "observations": len(rows),
                  "companies": len({row["company"] for row in rows})},
       "predictors": {}}

    predictors = (
        # pre-registered (D-035): outcome compared with the RECENT block
        ("calibrated_increase_vs_recent", "flagged_increase", "future_increase"),
        ("naive_increase_vs_recent", "naive_increase", "future_increase"),
        ("persistence_increase_vs_recent", "persistence_increase", "future_increase"),
        ("calibrated_decrease_vs_recent", "flagged_decrease", "future_decrease"),
        ("naive_decrease_vs_recent", "naive_decrease", "future_decrease"),
        ("persistence_decrease_vs_recent", "persistence_decrease", "future_decrease"),
        # post-hoc supplement: outcome compared with the LONG-RUN rate (removes the regression-to-
        # the-mean bias that the recent-block comparison builds in)
        ("calibrated_increase_vs_baseline", "flagged_increase", "future_above_baseline"),
        ("naive_increase_vs_baseline", "naive_increase", "future_above_baseline"),
        ("persistence_increase_vs_baseline", "persistence_increase", "future_above_baseline"),
        ("calibrated_decrease_vs_baseline", "flagged_decrease", "future_below_baseline"),
        ("naive_decrease_vs_baseline", "naive_decrease", "future_below_baseline"),
        ("persistence_decrease_vs_baseline", "persistence_decrease", "future_below_baseline"),
    )
    for label, flag_key, outcome_key in predictors:
        point = precision(rows, flag_key, outcome_key)
        boot = clustered_bootstrap(rows, flag_key, outcome_key, rng, BOOTSTRAPS)
        report["predictors"][label] = {**point, **boot}
        print(f"{label:34s} flagged={point['flagged']:5d} "
              f"P(outcome|flag)="
              f"{'n/a' if point['precision_flagged'] is None else round(point['precision_flagged'], 3)} "
              f"P(outcome|noflag)="
              f"{'n/a' if point['precision_unflagged'] is None else round(point['precision_unflagged'], 3)} "
              f"lift={'n/a' if point['lift'] is None else round(point['lift'], 3)} "
              f"ci={[None if value is None else round(value, 2) for value in boot['lift_ci']]}")

    report["resolution"] = {
        "pre_registered_design_flaw": (
            "comparing the future block with the recent block conditions on the recent block being "
            "unusually high for flagged cells, so lift below 1 is expected at a constant rate "
            "(regression to the mean). The pre-registered numerator cannot separate that from "
            "anti-momentum; the _vs_baseline predictors are the declared post-hoc correction."),
        "calibrated_flags": report["predictors"]["calibrated_increase_vs_baseline"]["flagged"],
        "note": ("with this many calibrated flags the precision interval is wide; a null is reported "
                 "with its interval rather than as evidence of no predictability"),
    }
    write_json(Path(args.out), report)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
