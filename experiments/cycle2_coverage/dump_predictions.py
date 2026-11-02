"""Dump per-row holdout predictions for the cycle-2 panels.

``run_backtest`` reports aggregate metrics; cluster-aware inference and lead-time
analysis need the individual (label, probability, cluster) rows. Fitting only the
pre-declared holdout windows costs three fits per panel instead of one per origin,
and the resulting metrics are cross-checked against the frozen backtest artifacts.

Usage:
    python experiments/cycle2_coverage/dump_predictions.py --panel p2 \
        --db data/research.sqlite --out experiments/cycle2_coverage/pred_p2.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.evaluation.backtesting import eligible_training_rows  # noqa: E402
from medradar.intelligence.evaluation.metrics import evaluate  # noqa: E402
from medradar.intelligence.models.baseline import LogisticBaseline  # noqa: E402
from medradar.util import parse_date  # noqa: E402
from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from experiments.cycle2_coverage.run_cycle2 import (  # noqa: E402
    SPEC_FEATURES,
    build_p1,
    build_p2,
)

HOLDOUTS = 3


def lead_days(row: dict[str, Any]) -> int | None:
    if not row.get("label") or not row.get("first_target_event_date"):
        return None
    start = parse_date(row.get("cutoff"))
    end = parse_date(row.get("first_target_event_date"))
    return (end - start).days if start and end else None


def persistence_probabilities(mature: list[dict[str, Any]], origin: str) -> list[float]:
    """Per-row pair-persistence probability, mirroring ``backtesting._persistence_baselines``."""
    training = eligible_training_rows(mature, origin, purge=True, horizon_months=12)
    test = [row for row in mature if row["cutoff"] == origin]
    if not training:
        return []
    prevalence = sum(int(row["label"]) for row in training) / len(training)
    history: dict[Any, list[int]] = {}
    for row in training:
        key = (row.get("company_key"), row.get("track_id"))
        history.setdefault(key, []).append(int(row["label"]))
    values = []
    for row in test:
        seen = history.get((row.get("company_key"), row.get("track_id")))
        values.append(sum(seen) / len(seen) if seen else prevalence)
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--panel", choices=["p1", "p2"], required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if args.panel == "p1":
        panel, _detail = build_p1(db_path)
    else:
        panel, _detail = build_p2(db_path, cohort_size=200, min_material=3,
                                  min_active_years=2)

    mature = [row for row in panel["examples"] if row["maturity"] == "mature"
              and row["label"] is not None]
    origins = sorted({row["cutoff"] for row in mature})
    evaluable = [cutoff for cutoff in origins
                 if eligible_training_rows(mature, cutoff, purge=True, horizon_months=12)]
    holdout_origins = evaluable[-HOLDOUTS:]

    windows = []
    for origin in holdout_origins:
        train = eligible_training_rows(mature, origin, purge=True, horizon_months=12)
        test = [row for row in mature if row["cutoff"] == origin]
        model = LogisticBaseline(SPEC_FEATURES).fit(
            [row["features"] for row in train], [int(row["label"]) for row in train])
        probabilities = model.predict_proba([row["features"] for row in test])
        baseline = persistence_probabilities(mature, origin)
        labels = [int(row["label"]) for row in test]
        metrics = evaluate(labels, probabilities,
                           lead_times=[lead_days(row) for row in test])
        window = {
            "origin": origin,
            "training_rows": len(train),
            "rows": [
                {
                    "entity": row.get("company_key"),
                    "track": row.get("track_id"),
                    "label": int(row["label"]),
                    "probability": probability,
                    "baseline_probability": baseline[index] if index < len(baseline) else None,
                    "lead_days": lead_days(row),
                    "target_date": row.get("first_target_event_date"),
                }
                for index, (row, probability) in enumerate(zip(test, probabilities))
            ],
            "metrics": metrics,
            "baseline_metrics": evaluate(labels, baseline,
                                         lead_times=[lead_days(row) for row in test]),
        }
        windows.append(window)
        print(f"  {args.panel} {origin}: rows={metrics['n']} pos={metrics['positives']} "
              f"pr_auc={metrics['pr_auc']:.6f} baseline_pr_auc={window['baseline_metrics']['pr_auc']:.6f}")

    payload = {
        "panel": args.panel,
        "dataset_version": panel["dataset_version"],
        "specification": {"name": "rd_plus_entry_history", "features": SPEC_FEATURES},
        "holdout_origins": holdout_origins,
        "window_count": len(windows),
        "windows": windows,
    }
    write_json(Path(args.out), payload)
    print(f"wrote {args.out}: {sum(len(w['rows']) for w in windows)} rows over "
          f"{len(windows)} windows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
