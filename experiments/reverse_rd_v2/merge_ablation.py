#!/usr/bin/env python3
"""Merge per-cell ablation results into the frozen ``ablation_metrics.json``.

Each cell file is produced by ``run_ablation.py`` (one target + one specification,
purged rolling-origin, ``holdouts=3``). This script only aggregates and computes
factual marginal deltas; it never invents numbers and does not rewrite the cells.

Usage
-----
    python experiments/reverse_rd_v2/merge_ablation.py --cells .ablation --out experiments/reverse_rd_v2/ablation_metrics.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medradar.util import utc_now_iso, write_json  # noqa: E402

TARGET_ORDER = ("continuation", "entry")
# For each target: which spec is the reference, and which specs are "added group" deltas.
REFERENCE = {"continuation": "A", "entry": "D"}
GROUPS = {
    "continuation": {
        "B": "financial", "C": "market", "D": "publication",
        "E": "financial+market+publication (all available)",
    },
    "entry": {
        "A": "shared-only baseline (Phase 1 parity, no entry-specific features)",
        "B": "shared+financial (Phase 1 parity)",
        "C": "entry-specific features",
        "E": "market", "F": "publication",
        "G": "financial+market+publication (all available)",
    },
}
METRICS = ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k")


def _load_cells(directory: Path) -> dict[str, dict[str, dict[str, Any]]]:
    cells: dict[str, dict[str, dict[str, Any]]] = {}
    for path in sorted(directory.glob("*.json")):
        if path.name in ("pids.json", "ablation_metrics.json"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "report" not in payload or "target" not in payload:
            continue
        cells.setdefault(payload["target"], {})[payload["spec"]] = payload
    return cells


def _window_stat(model: dict[str, Any], metric: str, field: str = "mean") -> float | None:
    summary = (model.get("holdout_window_summary") or {}).get(metric) or {}
    value = summary.get(field)
    return value if isinstance(value, (int, float)) else None


def _cell_summary(cell: dict[str, Any]) -> dict[str, Any]:
    report = cell["report"]
    model = report["models"][0]
    holdout_metrics = model.get("holdout_metrics") or {}
    baselines = (report.get("baselines") or {}).get("predictors") or {}
    baseline_ap = {name: values.get("pr_auc") for name, values in baselines.items()}
    comparison = (report.get("model_vs_pair_baseline") or {}).get("model_scores", {}).get(model["name"], {})
    return {
        "spec": cell["spec"], "spec_name": cell["spec_name"],
        "features": cell["features"], "feature_counts": cell["feature_group_sizes"],
        "holdout": report["holdout"], "holdout_origins": report["holdout_origins"],
        "holdout_metrics": {metric: holdout_metrics.get(metric) for metric in METRICS},
        "holdout_rows": holdout_metrics.get("n"), "holdout_positives": holdout_metrics.get("positives"),
        "holdout_prevalence": holdout_metrics.get("prevalence"),
        "per_window_pr_auc": [row.get("pr_auc") for row in model.get("holdout_window_metrics", [])],
        "window_pr_auc_mean": _window_stat(model, "pr_auc", "mean"),
        "window_pr_auc_std": _window_stat(model, "pr_auc", "std"),
        "window_brier_mean": _window_stat(model, "brier", "mean"),
        "window_ece_mean": _window_stat(model, "ece", "mean"),
        "baseline_pr_auc": baseline_ap,
        "model_vs_pair_baseline": comparison,
        "runtime_seconds": cell.get("runtime_seconds"),
        "market_coverage": cell.get("market_coverage") or {},
    }


def _delta(added: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for metric in METRICS:
        old = reference["holdout_metrics"].get(metric)
        new = added["holdout_metrics"].get(metric)
        out[metric] = (new - old) if old is not None and new is not None else None
    old_mean = reference.get("window_pr_auc_mean")
    new_mean = added.get("window_pr_auc_mean")
    out["window_pr_auc_mean"] = (new_mean - old_mean) if old_mean is not None and new_mean is not None else None
    return out


FROZEN_FILES = {"continuation": "continuation_metrics.json", "entry": "entry_metrics.json"}
FROZEN_MODEL_SPEC = {"A": 0, "B": 1}


def _frozen_specs(frozen_dir: Path, target: str) -> dict[str, dict[str, Any]]:
    """Load the Phase-1 frozen A/B cells (same protocol) as extra specifications."""
    path = frozen_dir / FROZEN_FILES[target]
    if not path.exists():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    baselines = (report.get("baselines") or {}).get("predictors") or {}
    out: dict[str, dict[str, Any]] = {}
    for spec, index in FROZEN_MODEL_SPEC.items():
        models = report.get("models") or []
        if index >= len(models):
            continue
        model = models[index]
        holdout_metrics = model.get("holdout_metrics") or {}
        comparison = (report.get("model_vs_pair_baseline") or {}).get("model_scores", {}).get(
            model.get("name"), {})
        out[spec] = {
            "spec": spec, "spec_name": model.get("description") or model.get("name"),
            "features": model.get("features") or [], "feature_counts": {},
            "holdout": report.get("holdout"), "holdout_origins": report.get("holdout_origins"),
            "holdout_metrics": {metric: holdout_metrics.get(metric) for metric in METRICS},
            "holdout_rows": holdout_metrics.get("n"), "holdout_positives": holdout_metrics.get("positives"),
            "holdout_prevalence": holdout_metrics.get("prevalence"),
            "per_window_pr_auc": [row.get("pr_auc") for row in model.get("holdout_window_metrics", [])],
            "window_pr_auc_mean": _window_stat(model, "pr_auc", "mean"),
            "window_pr_auc_std": _window_stat(model, "pr_auc", "std"),
            "window_brier_mean": _window_stat(model, "brier", "mean"),
            "window_ece_mean": _window_stat(model, "ece", "mean"),
            "baseline_pr_auc": {name: values.get("pr_auc") for name, values in baselines.items()},
            "model_vs_pair_baseline": comparison,
            "runtime_seconds": None,
            "source": "frozen_v2_metrics",
        }
    return out


def merge(cells_dir: Path, frozen_dir: Path) -> dict[str, Any]:
    cells = _load_cells(cells_dir)
    merged: dict[str, Any] = {
        "experiment": "reverse_rd_v2_feature_group_ablation",
        "generated_at": utc_now_iso(),
        "protocol": {
            "evaluation": "purged/embargoed expanding-window rolling origin",
            "holdouts": 3, "horizon_months": 12, "min_train_origins": 3,
            "model": "dependency-free logistic regression (fixed hyperparameters), identical rows across specs",
            "feature_selection": "one specification per run; every spec trained on exactly the same examples",
            "targets": {
                "continuation": "reverse_rd_v1: any material public FDA 510(k)/original-or-panel-track PMA activity for an already-active company-track pair in the next 12 months",
                "entry": "first_entry_v1: first material public FDA activity in a track the company had not touched for >= 36 months before the cutoff",
            },
            "excluded_sources": {
                "procurement": "USAspending snapshot is not point-in-time usable (pit_usable=0); excluded from historical gain claims",
                "patents": "USPTO Open Data Portal requires an API key; no patent rows were collected or evaluated",
                "hiring": "no stable legal source evaluated in this phase",
            },
        },
        "targets": {},
    }
    for target in TARGET_ORDER:
        target_cells = cells.get(target, {})
        if not target_cells:
            continue
        specs = {spec: _cell_summary(cell) for spec, cell in sorted(target_cells.items())}
        for spec, summary in _frozen_specs(frozen_dir, target).items():
            specs.setdefault(spec, summary)
        reference_spec = REFERENCE[target]
        reference = specs.get(reference_spec)
        deltas = {}
        if reference:
            for spec, description in GROUPS[target].items():
                if spec in specs:
                    deltas[spec] = {"vs": reference_spec, "group": description,
                                    "delta": _delta(specs[spec], reference)}
        merged["targets"][target] = {
            "dataset_version": next(iter(target_cells.values()))["dataset_version"],
            "reference_spec": reference_spec,
            "specs": specs,
            "marginal_deltas": deltas,
            "best_spec_by_holdout_pr_auc": max(
                (spec for spec in specs if specs[spec]["holdout_metrics"].get("pr_auc") is not None),
                key=lambda spec: specs[spec]["holdout_metrics"]["pr_auc"], default=None),
            "specs_evaluated": sorted(specs),
            "specs_missing": [spec for spec in GROUPS[target] if spec not in specs],
        }
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=Path, required=True)
    parser.add_argument("--frozen-dir", type=Path, default=ROOT / "experiments" / "reverse_rd_v2")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    merged = merge(args.cells, args.frozen_dir)
    write_json(args.out, merged)
    for target, block in merged["targets"].items():
        print(f"== {target} (reference {block['reference_spec']}) ==")
        for spec, summary in block["specs"].items():
            metrics = summary["holdout_metrics"]
            print(f"  {spec}: AP={metrics.get('pr_auc'):.6f} brier={metrics.get('brier'):.6f} "
                  f"ece={metrics.get('ece'):.6f} n={summary['holdout_rows']} "
                  f"pos={summary['holdout_positives']}")
        for spec, delta in block["marginal_deltas"].items():
            print(f"  delta {spec} vs {delta['vs']} ({delta['group']}): "
                  f"AP={delta['delta']['pr_auc']} window_mean={delta['delta']['window_pr_auc_mean']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
