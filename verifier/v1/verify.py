#!/usr/bin/env python3
"""Behavioural v1 acceptance checks for the Market-to-R&D layer.

This is deliberately not a self-certification checklist: it runs the full
offline test suite in a subprocess, parses the committed experiment artifacts,
and recomputes numbers from the stored per-origin data instead of trusting the
prose around them. Everything runs offline against the repository.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "experiments" / "reverse_rd_v1"
EVIDENCE_FIELDS = {"feature", "contribution", "raw_value", "standardized_value", "median_imputed", "coefficient"}


def _fail(checks: dict, name: str, detail: str | None = None) -> None:
    checks[name] = False
    if detail:
        checks[f"{name}_detail"] = detail


def _check_offline_suite(checks: dict) -> None:
    command = [sys.executable, "-m", "pytest", "tests/", "-q"]
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=1800)
    print(result.stdout)
    checks["offline_selftest"] = result.returncode == 0
    checks["offline_selftest_command"] = " ".join(command[1:])
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


def _check_v2_experiment(checks: dict) -> None:
    """Phase 1/2 frozen artefacts: entry target, multi-window, feature ablation."""
    v2 = ROOT / "experiments" / "reverse_rd_v2"
    required = ["config.json", "continuation_metrics.json", "entry_metrics.json", "ablation_metrics.json"]
    checks["v2_artifacts_present"] = all((v2 / name).exists() for name in required)
    if not checks["v2_artifacts_present"]:
        return
    continuation = json.loads((v2 / "continuation_metrics.json").read_text(encoding="utf-8"))
    entry = json.loads((v2 / "entry_metrics.json").read_text(encoding="utf-8"))
    ablation = json.loads((v2 / "ablation_metrics.json").read_text(encoding="utf-8"))
    checks["v2_multi_window_holdouts"] = (
        continuation.get("holdouts") == 3 and entry.get("holdouts") == 3
        and len(continuation.get("holdout_origins") or []) == 3
        and len(entry.get("holdout_origins") or []) == 3)
    entry_dataset = entry.get("dataset") or {}
    checks["v2_entry_target_defined"] = (
        entry_dataset.get("dataset_version") == "first_entry_v1"
        and int(entry_dataset.get("examples_mature") or 0) > 1000
        and int(entry_dataset.get("positives_mature") or 0) > 0
        and bool(entry_dataset.get("left_censoring")))
    checks["v2_purged_and_audited"] = (
        (entry.get("purge") or {}).get("default") is True
        and (continuation.get("purge") or {}).get("default") is True
        and (continuation.get("leakage_audit") or {}).get("ok") is True
        and (entry.get("leakage_audit") or {}).get("ok") is True)
    v1 = json.loads((EXPERIMENT / "metrics.json").read_text(encoding="utf-8"))
    v1_ap = {model["name"]: model["holdout_metrics"].get("pr_auc") for model in v1.get("models", [])}
    v2_ap = {model["name"]: model["holdout_metrics"].get("pr_auc") for model in continuation.get("models", [])}
    checks["v2_continuation_reproduces_v1"] = bool(v1_ap) and all(
        v1_ap.get(name) is not None and v2_ap.get(name) is not None
        and math.isclose(v1_ap[name], v2_ap[name], rel_tol=1e-9, abs_tol=1e-9)
        for name in v1_ap)
    targets = ablation.get("targets") or {}
    checks["v2_ablation_targets"] = set(targets) >= {"continuation", "entry"}
    checks["v2_ablation_reference_specs"] = all(
        block.get("reference_spec") in (block.get("specs") or {}) for block in targets.values())
    checks["v2_ablation_spec_metrics"] = all(
        all(spec.get("holdout_metrics", {}).get("pr_auc") is not None
            for spec in (block.get("specs") or {}).values())
        for block in targets.values())
    excluded = (ablation.get("protocol") or {}).get("excluded_sources") or {}
    checks["v2_excluded_sources_documented"] = "procurement" in excluded and "patents" in excluded
    checks["v2_no_patent_feature_claims"] = not any(
        name.startswith("pat_")
        for block in targets.values()
        for spec in (block.get("specs") or {}).values()
        for name in (spec.get("features") or []))


def _check_phase3(checks: dict) -> None:
    """Phase 3 artefacts: canonical nowcast registry, TKG real import, research agent."""
    v3 = ROOT / "experiments" / "reverse_rd_v2"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        import tempfile
        from datetime import datetime, timedelta, timezone

        from medradar.forecast_registry import ForecastRegistry
        from medradar.intelligence import graph_context  # noqa: F401
        from medradar.intelligence.forecasting import cycle, registry_adapter  # noqa: F401
        from medradar import research_agent  # noqa: F401
        checks["v3_modules_importable"] = True
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        checks["v3_modules_importable"] = False
        checks["v3_modules_import_error"] = str(exc)[:200]
        return
    sha = "a" * 64
    spec = {
        "idempotency_key": "verify-nowcast", "record_kind": "nowcast", "p": 0.4,
        "horizon_months": 12, "information_cutoff": "2026-01-01T00:00:00Z",
        "window_start": "2026-01-01T00:00:00Z", "model_version": "verify-model-1",
        "feature_version": "verify-features-1",
        "target": {"type": "company_track", "id": "acme:track", "attrs": {"company": "acme"}},
        "evidence": {"source_locator": "sqlite://verify", "evidence_kind": "source_observed",
                     "evidence_sha256": sha,
                     "provenance": [{"source_locator": "sqlite://verify/src", "evidence_sha256": sha}]},
    }
    clock = lambda: datetime(2026, 6, 1, tzinfo=timezone.utc)  # noqa: E731
    with ForecastRegistry(":memory:", clock=clock) as registry:
        record = registry.register(spec)
        checks["v3_nowcast_registered"] = (
            record["record_kind"] == "nowcast"
            and record["window_start"] == "2026-01-01T00:00:00.000000Z"
            and record["window_end"] == "2027-01-01T00:00:00.000000Z")
        try:
            registry.register({**spec, "idempotency_key": "verify-closed",
                               "window_start": "2020-01-01T00:00:00Z",
                               "information_cutoff": "2020-01-01T00:00:00Z"})
            checks["v3_closed_window_nowcast_rejected"] = False
        except Exception:  # noqa: BLE001 - rejection is the expected behaviour
            checks["v3_closed_window_nowcast_rejected"] = True
    tkg_path = v3 / "tkg_import_report.json"
    if tkg_path.exists():
        tkg = json.loads(tkg_path.read_text(encoding="utf-8"))
        checks["v3_tkg_real_data_report"] = (
            int((tkg.get("import") or {}).get("counters", {}).get("rows_seen") or 0) > 1000
            and int((tkg.get("store_counts") or {}).get("nodes") or 0) > 0
            and (tkg.get("checks") or {}).get("passed") is True
            and (tkg.get("checks") or {}).get("reimport_idempotent") is True)
    else:
        checks["v3_tkg_real_data_report"] = False
    demo_path = v3 / "agent_demo.json"
    if demo_path.exists():
        demo = json.loads(demo_path.read_text(encoding="utf-8"))
        summary = demo.get("summary") or {}
        verification = demo.get("verification") or {}
        checks["v3_agent_demo_cited"] = (
            int(summary.get("questions") or 0) >= 3
            and int(summary.get("claims") or 0) > 0
            and int(summary.get("unique_citations") or 0) > 0
            and verification.get("ok") is True
            and not verification.get("citations_missing"))
        checks["v3_agent_registry_used"] = (
            (demo.get("registry") or {}).get("present") is True
            and "registry_forecast" in (summary.get("citation_kinds") or []))
        checks["v3_agent_tkg_used"] = (demo.get("tkg") or {}).get("present") is True
    else:
        checks["v3_agent_demo_cited"] = False
    cycle_path = v3 / "forecast_cycle_report.json"
    if cycle_path.exists():
        cycle_report = json.loads(cycle_path.read_text(encoding="utf-8"))
        registry_block = cycle_report.get("registry") or {}
        checks["v3_cycle_registered_nowcasts"] = (
            int((cycle_report.get("counts") or {}).get("horizon_records") or 0) > 0
            and int(registry_block.get("by_record_kind", {}).get("nowcast") or 0) > 0
            and (cycle_report.get("calibration") or {}).get("status") == "insufficient_matured_forecasts")
    else:
        checks["v3_cycle_registered_nowcasts"] = False
    checks["v3_docs_present"] = all(
        (ROOT / "docs" / name).is_file()
        for name in ("PHASE3.md", "PHASE3_REGISTRY.md", "PHASE3_AGENT.md", "TKG_INTEGRATION.md"))


def main() -> int:
    checks: dict[str, object] = {"version": "v1"}
    _check_offline_suite(checks)
    _check_experiment(checks)
    _check_provenance(checks)
    _check_v2_experiment(checks)
    _check_phase3(checks)
    ok = all(value is True for key, value in checks.items()
             if key != "version"
             and not key.endswith(("_detail", "_command", "_excluded", "_rows", "_tail", "_numbers")))
    print(json.dumps({"version": "v1", "ok": ok, "checks": checks}, indent=2, sort_keys=True, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
