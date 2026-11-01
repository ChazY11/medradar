#!/usr/bin/env python3
"""Behavioural v1 acceptance checks for the Market-to-R&D layer.

This is deliberately not a self-certification checklist: it runs the offline
test suite in a subprocess, parses the committed experiment artifacts, and
recomputes numbers from the stored per-origin data instead of trusting the
prose around them. Everything runs offline against the repository.

Known external exclusion: ``tests/test_tkg.py`` has a pre-existing integration
regression on the integration base branch and is owned by another fixer; it is
excluded from the offline suite here and recorded in the output, never silently
ignored.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "experiments" / "reverse_rd_v1"
EXCLUDED_SUITE = {
    "tests/test_tkg.py": (
        "KNOWN EXTERNAL FAILURE on the integration base (snapshot hash regression); owned by another "
        "fixer, unrelated to the Market-to-R&D layer."
    ),
}
EVIDENCE_FIELDS = {"feature", "contribution", "raw_value", "standardized_value", "median_imputed", "coefficient"}


def _fail(checks: dict, name: str, detail: str | None = None) -> None:
    checks[name] = False
    if detail:
        checks[f"{name}_detail"] = detail


def _check_offline_suite(checks: dict) -> None:
    command = [sys.executable, "-m", "pytest", "tests/", "-q", "--ignore=tests/test_tkg.py"]
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=1800)
    print(result.stdout)
    checks["offline_selftest"] = result.returncode == 0
    checks["offline_selftest_command"] = " ".join(command[1:])
    checks["offline_selftest_excluded"] = EXCLUDED_SUITE
    if result.returncode != 0:
        checks["offline_selftest_tail"] = "\n".join(result.stdout.strip().splitlines()[-15:])


def _recompute_stability(model: dict) -> dict:
    """Recompute PR-AUC stability from the stored per-origin rows, not the summary."""
    values = [row["pr_auc"] for row in model.get("origin_metrics", [])
              if not row.get("is_holdout") and row.get("pr_auc") is not None]
    if not values:
        return {"origins": 0, "pr_auc_mean": None, "pr_auc_std": None,
                "pr_auc_min": None, "pr_auc_max": None}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {"origins": len(values), "pr_auc_mean": mean, "pr_auc_std": math.sqrt(variance),
            "pr_auc_min": min(values), "pr_auc_max": max(values)}


def _check_experiment(checks: dict) -> None:
    metrics_path = EXPERIMENT / "metrics.json"
    forecasts_path = EXPERIMENT / "forecasts.json"
    required = ["config.json", "data_provenance.json", "metrics.json", "forecasts.json",
                "procurement_summary.json", "REPORT.md"]
    checks["experiment_artifacts"] = all((EXPERIMENT / name).exists() for name in required)
    if not checks["experiment_artifacts"]:
        _fail(checks, "required_metric_keys", f"missing artifacts: {required}")
        return
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    forecasts = json.loads(forecasts_path.read_text(encoding="utf-8"))
    model_names = [model.get("name") for model in metrics.get("models", [])]

    required_metrics = {"pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k",
                        "mean_lead_time_days"}
    checks["required_metric_keys"] = (
        model_names == ["rd_only", "rd_financial"]
        and all(required_metrics.issubset((model.get("holdout_metrics") or {}).keys())
                for model in metrics["models"]))
    checks["rolling_origins_at_least_4"] = len(metrics.get("origins") or []) >= 4
    checks["holdout_present"] = bool(metrics.get("holdout"))

    # F1: purge must be the default and the leaky variant must be explicit.
    purge = metrics.get("purge") or {}
    checks["purge_default"] = purge.get("default") is True
    checks["leaky_labels_diagnostic_present"] = (
        (metrics.get("leaky_labels_diagnostic") or {}).get("role") == "diagnostic_only")
    checks["model_training_label_policy"] = all(
        model.get("training_label_policy") == "matured_by_origin" for model in metrics["models"])

    # F2: persistence baselines present and the paired bootstrap interval ordered.
    baselines = metrics.get("baselines") or {}
    predictors = baselines.get("predictors") or {}
    checks["persistence_baselines_present"] = all(
        name in predictors for name in ("constant_training_prevalence", "company_base_rate",
                                        "track_base_rate", "pair_base_rate"))
    checks["persistence_baselines_metrics"] = all(
        predictors[name].get("pr_auc") is not None and predictors[name].get("brier") is not None
        for name in predictors)
    comparison = metrics.get("model_vs_pair_baseline") or {}
    checks["paired_bootstrap_present"] = (
        comparison.get("resamples") == 2000 and comparison.get("seed") == 7
        and all(entry.get("ci_low") is not None and entry.get("ci_high") is not None
                and entry["ci_low"] <= entry["ci_high"]
                for entry in (comparison.get("model_scores") or {}).values()))
    checks["persistence_baseline_reported"] = predictors.get("pair_base_rate", {}).get("pr_auc") is not None

    # F3: leakage audit must report a real method, a nonzero workload and no mismatches.
    leakage = metrics.get("leakage_audit") or {}
    checks["leakage_audit_present"] = (
        bool(leakage.get("checked_examples")) and leakage.get("checked_examples") > 0
        and leakage.get("method") == "independent_as_of_replay"
        and leakage.get("ok") is True
        and leakage.get("mismatch_count") == 0)

    # Recompute the reported PR-AUC stability from stored per-origin rows.
    def stability_matches(model: dict) -> bool:
        reported = model.get("forecast_horizon_stability") or {}
        predicted = _recompute_stability(model)
        if reported.get("origins") != predicted["origins"]:
            return False
        for key in ("pr_auc_mean", "pr_auc_std", "pr_auc_min", "pr_auc_max"):
            left, right = reported.get(key), predicted[key]
            if left is None or right is None:
                if left is not right:
                    return False
            elif not math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9):
                return False
        return True

    checks["recomputed_origin_stability"] = all(stability_matches(model) for model in metrics["models"])

    # Recompute the financial-features marginal value from the committed metrics.
    marginal = metrics.get("financial_marginal_value") or {}
    if len(metrics["models"]) == 2:
        first, second = metrics["models"]
        recomputed = {
            key: second["holdout_metrics"][key] - first["holdout_metrics"][key]
            for key in ("pr_auc", "brier", "ece", "false_positive_rate", "precision_at_k")
        }
        checks["recomputed_financial_marginal_value"] = all(
            marginal.get(key) is not None
            and math.isclose(marginal[key], recomputed[key], rel_tol=1e-12, abs_tol=1e-12)
            for key in recomputed)
    else:
        checks["recomputed_financial_marginal_value"] = False

    # F5: forecast evidence must be self-describing and internally consistent.
    evidence_rows = 0
    evidence_consistent = True
    for forecast in forecasts:
        for key in ("supporting_evidence", "contradictory_evidence"):
            for item in forecast.get(key) or []:
                evidence_rows += 1
                if not EVIDENCE_FIELDS.issubset(item.keys()):
                    evidence_consistent = False
                    continue
                if not math.isclose(item["contribution"],
                                    item["coefficient"] * item["standardized_value"],
                                    rel_tol=1e-9, abs_tol=1e-9):
                    evidence_consistent = False
                if item["raw_value"] is not None and float(item["raw_value"]) != float(item["value"]):
                    evidence_consistent = False
                if item["median_imputed"] and item["raw_value"] is not None:
                    evidence_consistent = False
    checks["forecast_evidence_self_describing"] = evidence_consistent and evidence_rows > 0
    checks["forecast_evidence_rows"] = evidence_rows
    checks["forecasts_pending"] = bool(forecasts) and all(
        forecast.get("status") == "pending" for forecast in forecasts)

    # REPORT.md must use the machine-readable, purged numbers (not stale leaky ones).
    report = (EXPERIMENT / "REPORT.md").read_text(encoding="utf-8")
    required_numbers = []
    for model in metrics["models"]:
        for key in ("pr_auc", "brier", "ece", "false_positive_rate"):
            value = model["holdout_metrics"].get(key)
            if value is not None:
                required_numbers.append(f"{value:.6f}")
    pair_auc = predictors.get("pair_base_rate", {}).get("pr_auc")
    if pair_auc is not None:
        required_numbers.append(f"{pair_auc:.6f}")
    missing = [number for number in required_numbers if number not in report]
    checks["report_matches_metrics"] = not missing
    if missing:
        checks["report_missing_numbers"] = missing[:10]


def _check_provenance(checks: dict) -> None:
    metrics_path = EXPERIMENT / "metrics.json"
    provenance_path = EXPERIMENT / "data_provenance.json"
    if not metrics_path.exists() or not provenance_path.exists():
        checks["real_data_provenance"] = False
        return
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    dataset = metrics.get("dataset") or {}
    checks["real_data_provenance"] = (
        bool(provenance.get("retrieved_at"))
        and int(dataset.get("event_count") or 0) > 1000
        and int(dataset.get("stored_examples") or 0) > 1000
        and int(provenance.get("financial_fact_rows") or 0) > 0
        and int(provenance.get("procurement_award_rows") or 0) > 0)
    checks["no_raw_data_committed"] = not any(
        path.suffix in {".sqlite", ".zip", ".gz"} for path in (ROOT / "experiments").rglob("*"))


def main() -> int:
    checks: dict[str, object] = {"version": "v1"}
    _check_offline_suite(checks)
    _check_experiment(checks)
    _check_provenance(checks)
    ok = all(value is True for key, value in checks.items()
             if key != "version"
             and not key.endswith(("_detail", "_command", "_excluded", "_rows", "_tail", "_numbers")))
    print(json.dumps({"version": "v1", "ok": ok, "checks": checks}, indent=2, sort_keys=True, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
