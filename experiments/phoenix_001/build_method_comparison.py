#!/usr/bin/env python3
"""Build a fair PHOENIX comparison from pre-existing frozen MedRadar artefacts.

No raw store is read or regenerated. Recall@K is recomputed from the frozen K and
Precision@K. All other predictive values are copied with their provenance.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHOENIX = ROOT / "experiments" / "phoenix_001"
V2 = ROOT / "experiments" / "reverse_rd_v2"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(row: dict, windows=None) -> dict:
    k = int(row["k"])
    tp = int(round(row["precision_at_k"] * k))
    return {
        "n": row["n"], "positives": row["positives"], "prevalence": row["prevalence"],
        "average_precision": row["pr_auc"], "precision_at_k": row["precision_at_k"],
        "k": k, "true_positives_at_k": tp, "recall_at_k": tp / row["positives"],
        "false_positive_rate_at_0_5": row["false_positive_rate"],
        "mean_lead_time_days": row.get("mean_lead_time_days"),
        "brier": row.get("brier"), "ece": row.get("ece"),
        "per_window_average_precision": windows,
    }


def subgroup_summary(model: dict) -> dict:
    result = {}
    for kind, groups in (model.get("holdout_subgroups") or {}).items():
        valid = [(name, group) for name, group in groups.items() if group.get("pr_auc") is not None]
        aps = [group["pr_auc"] for _, group in valid]
        result[kind] = {
            "groups_with_ap": len(valid),
            "ap_min": min(aps) if aps else None, "ap_max": max(aps) if aps else None,
            "positive_count_min": min((g["positives"] for _, g in valid), default=None),
            "positive_count_max": max((g["positives"] for _, g in valid), default=None),
            "warning": "Subgroup AP is unstable when positives are sparse; ranges are descriptive, not rankings.",
        }
    return result


def main() -> int:
    continuation = load(V2 / "continuation_metrics.json")
    entry = load(V2 / "entry_metrics.json")
    ablation = load(V2 / "ablation_metrics.json")
    detect = load(ROOT / "experiments" / "detect_v1" / "realdetect.json")
    methods = []

    def add_baselines(target, block, windows_block):
        for name, row in block["baselines"]["predictors"].items():
            windows = (windows_block["baselines"][name]["pr_auc"] or {}) if windows_block else {}
            methods.append({
                "target": target, "method": name, "method_family": "statistical_baseline",
                "source": f"experiments/reverse_rd_v2/{target}_metrics.json",
                "final_origin_metrics": metrics(row, windows),
                "uncertainty": {"three_window_std": windows.get("std"), "note": "Population std across three origins, not a confidence interval"},
            })

    add_baselines("continuation", continuation, continuation.get("holdout_window_summary"))
    add_baselines("entry", entry, entry.get("holdout_window_summary"))

    spec_labels = {
        "continuation": {"A": "regulatory_only", "B": "regulatory_financial", "C": "regulatory_market",
                         "D": "regulatory_publication", "E": "all_available_fusion"},
        "entry": {"A": "shared_regulatory_only", "B": "shared_financial", "C": "entry_specific_features",
                  "D": "entry_financial", "E": "entry_market", "F": "entry_publication", "G": "all_available_fusion"},
    }
    for target in ("continuation", "entry"):
        block = ablation["targets"][target]
        for spec_name, label in spec_labels[target].items():
            spec = block["specs"][spec_name]
            window_values = spec["per_window_pr_auc"]
            windows = {"values": window_values, "mean": spec["window_pr_auc_mean"], "std": spec["window_pr_auc_std"]}
            source_metrics = dict(spec["holdout_metrics"])
            target_lead_time = (continuation if target == "continuation" else entry)["models"][0]["holdout_metrics"]["mean_lead_time_days"]
            source_metrics.update({"n": spec["holdout_rows"], "positives": spec["holdout_positives"],
                                   "prevalence": spec["holdout_prevalence"], "k": 31 if target == "continuation" else 172,
                                   "mean_lead_time_days": target_lead_time})
            methods.append({
                "target": target, "method": label, "method_family": "lightweight_logistic_regression",
                "feature_count": len(spec["features"]),
                "source": "experiments/reverse_rd_v2/ablation_metrics.json",
                "final_origin_metrics": metrics(source_metrics, windows),
                "uncertainty": {
                    "three_window_std": spec["window_pr_auc_std"],
                    "versus_pair_baseline": spec["model_vs_pair_baseline"],
                    "note": "Bootstrap interval is for the final origin; per-window values expose instability.",
                },
            })

    base_model_summaries = {}
    for target, block in (("continuation", continuation), ("entry", entry)):
        base_model_summaries[target] = {
            model["name"]: subgroup_summary(model) for model in block["models"]
        }
    dataset = {
        "continuation": {
            "matured_examples": continuation["dataset"]["examples_mature"],
            "positive_examples": continuation["dataset"]["positives_mature"],
            "material_event_rows": continuation["dataset"]["event_count"],
            "company_count": continuation["dataset"]["company_count"], "pair_count": continuation["dataset"]["pair_count"],
        },
        "entry": {
            "matured_examples": entry["dataset"]["examples_mature"],
            "positive_examples": entry["dataset"]["positives_mature"],
            "material_event_rows": entry["dataset"]["event_count"],
            "company_count": entry["dataset"]["company_count"], "track_count": entry["dataset"]["track_count"],
        },
        "independent_device_application_or_trial_count": None,
        "independence_note": "Raw identifiers are unavailable in this environment, so independent device/application/trial counts and cross-partition duplicates cannot be recomputed. Material event rows are not relabelled as independent devices.",
    }
    detector_comparison = {
        "cells": detect["design"]["cells_tested"],
        "evidence_category": 2,
        "detectors": {
            name: {
                "alerts": value["alerts_total"], "alerts_surviving_bh": value["alerts_surviving_bh"],
                "alert_rate_per_cell": value["alert_rate_per_cell"],
                "chosen_false_alarm_rate": value["calibration"]["chosen_false_alarm_rate"],
                "novelty_comparison": value["novelty_comparison"],
            } for name, value in detect["detectors"].items()
        },
        "conclusion": "No positive novelty evidence supports a claim that change-point detection is superior.",
    }
    artifact_paths = [
        V2 / "continuation_metrics.json", V2 / "entry_metrics.json", V2 / "ablation_metrics.json",
        V2 / "publication_metrics.json", V2 / "market_metrics.json",
        ROOT / "experiments" / "detect_v1" / "realdetect.json",
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "experiments/phoenix_001/hypotheses.json",
        "evidence_category": 3,
        "evidence_category_label": "Conservative simulated prediction using historical backfills and an estimated decision_date+14d knowledge proxy",
        "independent_prospective_validation": False,
        "source_policy": "Read-only frozen artefacts; no raw store, model or prior result was modified or regenerated.",
        "source_artifacts": [{"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for path in artifact_paths],
        "dataset": dataset,
        "holdout_origins": ["2025-04-01", "2025-07-01", "2025-10-01"],
        "methods": methods,
        "subgroup_stability": base_model_summaries,
        "detector_comparison": detector_comparison,
        "leakage_audit": {
            "entity_mapping": {
                "status": "material_unresolved_risk",
                "evidence": "S-028: events lack matched alias/confidence; 84 pre-acquisition events are assigned to parents. S-029: 67.68% of company-mention records would be missed by exact-parent matching; collisions are explicitly rejected.",
                "action": "Do not infer legal-entity or causal innovation histories. Any new module must persist alias, rule, confidence and ownership dates.",
            },
            "left_censoring": {
                "status": "present",
                "evidence": "Bulk history begins 2016-11-01. S-028 reports 230/322 final pairs active before the first origin; 'first' means first observed inside the window.",
                "action": "Targets are first observed entry/re-entry, never first innovation or first market entry.",
            },
            "time_proxy": {
                "status": "estimated_not_observed",
                "evidence": "All historical material events use decision_date+14d. S-028 finds one batch first_seen date and only 6/400 ledger observations with lag<=1d.",
                "action": "All results are category 3 simulation, not category 4 prospective validation.",
            },
            "duplicate_samples": {
                "status": "not_independently_recomputable_here",
                "evidence": "The raw stores are absent and only frozen aggregates are available. Device/application/trial IDs cannot be replayed across partitions.",
                "action": "Report this explicitly; do not claim an independent duplicate audit. Restored-data runs must deduplicate by source IDs and derived lineage before splitting.",
            },
            "cross_source_linkage": {
                "status": "limited_and_partly_blocked",
                "evidence": "No trial-to-FDA target; OpenAlex aliases are noisy; procurement lacks first-publication time; USPTO has zero rows.",
                "action": "H5 is blocked. Procurement and patents remain excluded from predictive gain.",
            },
            "semantic_mapping": {
                "status": "not_detectable_by_asof_replay",
                "evidence": continuation["leakage_audit"]["limitations"],
                "action": "Treat unversioned track/alias mappings as residual leakage even though the stored as-of replay has zero mismatches.",
            },
            "stored_replay": continuation["leakage_audit"],
        },
        "interpretation_guardrails": [
            "Regulatory activity is not innovation, internal R&D, adoption or revenue.",
            "Pair persistence is the key continuation baseline; a full model is not automatically an improvement.",
            "Fusion H9 is rejected only for these sources, targets and windows, not universally.",
            "No GNN was run in S-028. No prospective forecast is validated in PHOENIX.",
        ],
    }
    output = PHOENIX / "method_comparison.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"methods": len(methods), "targets": sorted({m["target"] for m in methods}),
                      "evidence_category": payload["evidence_category"],
                      "independent_prospective_validation": False,
                      "source_artifact_count": len(payload["source_artifacts"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
