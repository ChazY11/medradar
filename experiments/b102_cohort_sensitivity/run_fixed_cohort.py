#!/usr/bin/env python3
"""B-017 / b102: fixed-cohort sensitivity run for the cycle-2 P2 entry panel.

The committed cycle-2 P2 result was produced on a cohort that was *recomputed*
from the research store at run time.  Recomputing it today yields 195 of the
artefact's 200 entity keys plus 5 different ones (the "5/200 gap", DECISIONS
D-008).  This script closes that gap: it builds the P2 panel from the artefact's
**exact 200 entity keys** in ``config/universe_v1.json`` and re-runs the frozen
P2 specification end-to-end:

  * features ``rd_plus_entry_history`` (16 features, no financials);
  * 12-month horizon, 36-month dormancy, quarterly origins;
  * purge rule ``cutoff + 12 months <= origin``;
  * 3 holdout windows (the last 3 origins with a purged training set);
  * ``LogisticBaseline(epochs=180, learning_rate=0.15, l2=1.0)``;
  * per-window and pooled AP against the per-pair persistence baseline;
  * cluster-aware paired bootstrap (entity and company x track clusters,
    resamples=2000, seed=7), MDE from the observed bootstrap SE.

The universe selection is *not* re-implemented: the caller passes the artefact's
keys and the panel is built with the committed ``cycle2_coverage.panel``
builder.  The recomputation is only used to *describe* the 5/200 gap.

Usage:
    python experiments/b102_cohort_sensitivity/run_fixed_cohort.py
    python experiments/b102_cohort_sensitivity/run_fixed_cohort.py --skip-backtest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(ROOT))

from medradar.intelligence.evaluation.backtesting import (  # noqa: E402
    eligible_training_rows,
    run_backtest,
)
from medradar.intelligence.evaluation.metrics import evaluate  # noqa: E402
from medradar.intelligence.models.baseline import LogisticBaseline  # noqa: E402
from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402
from experiments.cycle2_coverage.analyze_cycle2 import (  # noqa: E402
    analyze_inference,
    analyze_per_window,
    window_summary,
)
from experiments.cycle2_coverage.dump_predictions import (  # noqa: E402
    lead_days,
    persistence_probabilities,
)
from experiments.cycle2_coverage.panel import (  # noqa: E402
    P2_DATASET_VERSION,
    assign_entity,
    build_entry_panel,
    write_json,
)
from experiments.cycle2_coverage.run_cycle2 import (  # noqa: E402
    BASE_FEATURES,
    SPEC_FEATURES,
    SPEC_NAME,
    build_p2,
    load_regulatory_events,
)

DEFAULT_DB = ROOT / "data" / "research.sqlite"
DEFAULT_COHORT = ROOT / "config" / "universe_v1.json"
DEFAULT_CYCLE2_DIR = ROOT / "experiments" / "cycle2_coverage"
DEFAULT_OUT_DIR = SCRIPT_DIR
DEFAULT_REPORT = DEFAULT_OUT_DIR / "fixed_cohort_report.json"
DEFAULT_BACKTEST = DEFAULT_OUT_DIR / "backtest_fixed_cohort.json"
DEFAULT_HOLDOUTS = 3
HORIZON_MONTHS = 12
SEED = 7
RESAMPLES = 2000
MODEL_SPEC = {"epochs": 180, "learning_rate": 0.15, "l2": 1.0}


def spec_block(holdouts: int) -> dict[str, Any]:
    return {
        "features": SPEC_NAME,
        "n_features": len(SPEC_FEATURES),
        "horizon_months": HORIZON_MONTHS,
        "purge_rule": "cutoff + 12 months <= origin",
        "holdouts": holdouts,
        "model": "LogisticBaseline(epochs=180, learning_rate=0.15, l2=1.0)",
        "metric": "average precision (pr_auc)",
        "baseline": "per-pair persistence base rate (cycle-2 committed comparator)",
        "bootstrap": {"clusters": ["entity", "company x track"], "resamples": RESAMPLES,
                      "seed": SEED, "confidence_level": 0.95},
        "mde": "evalstats.mde_from_se(entity bootstrap se_delta)",
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_artifact_cohort(path: str | Path) -> dict[str, Any]:
    """The artefact's exact cohort of entity keys (order preserved, validated)."""
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"cohort artefact not found: {resolved}")
    document = json.loads(resolved.read_text(encoding="utf-8"))
    cohort = document.get("cohort") or {}
    keys = [str(key) for key in cohort.get("entity_keys") or []]
    if not keys:
        raise ValueError(f"{resolved} has no cohort.entity_keys")
    if len(set(keys)) != len(keys):
        raise ValueError("cohort entity keys contain duplicates")
    expected = cohort.get("max_entities")
    if expected is not None and len(keys) != int(expected):
        raise ValueError(f"cohort has {len(keys)} keys but max_entities={expected}")
    return {
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "entity_keys": keys,
        "key_set": set(keys),
        "count": len(keys),
        "metadata": {key: cohort[key] for key in sorted(cohort) if key != "entity_keys"},
    }


# ------------------------------------------------------------------ restriction
def restrict_events_to_cohort(
    events: Iterable[Mapping[str, Any]], cohort_keys: set[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep events whose deterministic entity key is **exactly** in ``cohort_keys``.

    No normalisation, prefix or substring matching happens here: the event was
    already assigned its key by the frozen ``normalise_applicant``/``entity_key``
    functions, and membership is plain set equality.  Returns the kept events and
    the sorted keys that never occur in the event stream.
    """
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        key = str(event.get("entity") or "")
        if key in cohort_keys:
            kept.append(dict(event))
            seen.add(key)
    missing = sorted(cohort_keys - seen)
    return kept, missing


def build_fixed_panel(db_path: str | Path, cohort: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the committed P2 panel from the artefact's exact cohort keys."""
    events = load_regulatory_events(Path(db_path))
    assigned = assign_entity(events, normalise_applicant, entity_key)
    cohort_keys = cohort["key_set"]
    panel_events, missing_keys = restrict_events_to_cohort(assigned, cohort_keys)
    if not panel_events:
        raise ValueError("no material events for the artefact cohort")
    panel = build_entry_panel(
        panel_events,
        entity_field="entity",
        dataset_version=P2_DATASET_VERSION,
        coverage_end_reference="2026-10-15",
    )
    entity_events = {str(event["entity"]): event for event in panel_events}
    detail = {
        "cohort_entity_keys": list(cohort["entity_keys"]),
        "cohort_key_count": cohort["count"],
        "event_rows_loaded": len(events),
        "event_rows_in_cohort": len(panel_events),
        "entities_with_material_events": len(entity_events),
        "cohort_keys_without_material_events": missing_keys,
        "cohort_keys_without_usable_panel_events": sorted(
            set(cohort["entity_keys"]) - {str(row["company_key"]) for row in panel["examples"]}
        ),
        "panel": {
            "n_examples": panel["n_examples"],
            "n_positives": panel["n_positives"],
            "entity_count": panel["entity_count"],
            "track_count": panel["track_count"],
            "observed_pair_count": panel["observed_pair_count"],
            "event_count": panel["event_count"],
            "origins": len(panel["cutoffs"]),
            "coverage_start": panel["coverage_start"],
            "coverage_end": panel["coverage_end"],
            "cutoffs": panel["cutoffs"],
            "candidates_by_origin": panel["candidates_by_origin"],
            "positives_by_origin": panel["positives_by_origin"],
            "skipped_pending_examples": panel["skipped_pending_examples"],
        },
    }
    return panel, detail


# ------------------------------------------------------------- gap quantification
def recomputed_cohort_gap(db_path: str | Path, artifact_keys: set[str]) -> dict[str, Any]:
    """Recompute the cycle-2 P2 cohort exactly as the committed run did, and diff."""
    panel, detail = build_p2(
        Path(db_path), cohort_size=200, min_material=3, min_active_years=2
    )
    universe = detail["universe"]
    computed_keys = set(universe["cohort_entity_keys"])
    crosscheck = universe.get("cohort_artifact_crosscheck") or {}
    per_entity_examples: dict[str, dict[str, int]] = {}
    for row in panel["examples"]:
        key = str(row["company_key"])
        bucket = per_entity_examples.setdefault(key, {"rows": 0, "positives": 0})
        bucket["rows"] += 1
        bucket["positives"] += int(row["label"])
    return {
        "artifact_keys": len(artifact_keys),
        "computed_keys": len(computed_keys),
        "intersection": len(artifact_keys & computed_keys),
        "only_in_artifact": sorted(artifact_keys - computed_keys),
        "only_computed": sorted(computed_keys - artifact_keys),
        "symmetric_difference": len(artifact_keys ^ computed_keys),
        "artifact_crosscheck": crosscheck,
        "computed_panel_n_examples": panel["n_examples"],
        "computed_panel_n_positives": panel["n_positives"],
        "examples_by_key": per_entity_examples,
    }


def gap_impact(fixed_detail: Mapping[str, Any], gap: Mapping[str, Any],
               fixed_panel: Mapping[str, Any]) -> dict[str, Any]:
    """Attribute fixed-vs-committed panel differences to the swapped keys."""
    artifact_only = set(gap["only_in_artifact"])
    computed_only = set(gap["only_computed"])
    fixed_by_key: dict[str, dict[str, int]] = {}
    for row in fixed_panel["examples"]:
        key = str(row["company_key"])
        bucket = fixed_by_key.setdefault(key, {"rows": 0, "positives": 0})
        bucket["rows"] += 1
        bucket["positives"] += int(row["label"])
    computed_by_key = gap["examples_by_key"]
    return {
        "artifact_only_keys": sorted(artifact_only),
        "computed_only_keys": sorted(computed_only),
        "fixed_panel_rows_from_artifact_only_keys": sum(
            fixed_by_key.get(key, {}).get("rows", 0) for key in artifact_only),
        "fixed_panel_positives_from_artifact_only_keys": sum(
            fixed_by_key.get(key, {}).get("positives", 0) for key in artifact_only),
        "computed_panel_rows_from_computed_only_keys": sum(
            computed_by_key.get(key, {}).get("rows", 0) for key in computed_only),
        "computed_panel_positives_from_computed_only_keys": sum(
            computed_by_key.get(key, {}).get("positives", 0) for key in computed_only),
        "note": (
            "The committed artefact cohort was recomputed at run time; the fixed-cohort panel "
            "uses the committed artefact keys. The swapped 5+5 keys change the panel directly and "
            "also shift per-origin active-entity/track sets, so the metric deltas below are the "
            "measured net effect, not only the rows on the swapped keys."
        ),
    }


# ---------------------------------------------------------------- predictions
def build_prediction_windows(
    panel: Mapping[str, Any], *, holdouts: int = DEFAULT_HOLDOUTS
) -> dict[str, Any]:
    """Per-row holdout predictions, replicating ``dump_predictions.py`` exactly."""
    mature = [
        row for row in panel["examples"]
        if row["maturity"] == "mature" and row["label"] is not None
    ]
    origins = sorted({row["cutoff"] for row in mature})
    evaluable = [
        cutoff for cutoff in origins
        if eligible_training_rows(mature, cutoff, purge=True, horizon_months=HORIZON_MONTHS)
    ]
    holdout_origins = evaluable[-holdouts:]
    windows = []
    for origin in holdout_origins:
        train = eligible_training_rows(
            mature, origin, purge=True, horizon_months=HORIZON_MONTHS)
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
    return {
        "panel": "p2_fixed_cohort",
        "dataset_version": panel["dataset_version"],
        "specification": {"name": SPEC_NAME, "features": SPEC_FEATURES},
        "holdout_origins": holdout_origins,
        "window_count": len(windows),
        "windows": windows,
    }


def pool_prediction_rows(predictions: Mapping[str, Any]) -> tuple[list[int], list[float],
                                                                  list[float], list[str], list[str]]:
    labels: list[int] = []
    model: list[float] = []
    baseline: list[float] = []
    entities: list[str] = []
    pairs: list[str] = []
    for window in predictions["windows"]:
        for row in window["rows"]:
            if row.get("baseline_probability") is None:
                continue
            labels.append(int(row["label"]))
            model.append(float(row["probability"]))
            baseline.append(float(row["baseline_probability"]))
            entities.append(f"E:{row['entity']}")
            pairs.append(f"P:{row['entity']}|{row['track']}")
    return labels, model, baseline, entities, pairs


def analyze_predictions(predictions: Mapping[str, Any]) -> dict[str, Any]:
    labels, model, baseline, entities, pairs = pool_prediction_rows(predictions)
    inference = analyze_inference(labels, model, baseline, entities, pairs)
    per_window = analyze_per_window(predictions)
    majority: dict[str, Any] = {}
    for clustering in ("entity", "pair"):
        flags = [row.get(f"excludes_zero_{clustering}") for row in per_window]
        majority[clustering] = {
            "windows_total": len(flags),
            "windows_excluding_zero": sum(1 for flag in flags if flag),
            "majority": sum(1 for flag in flags if flag) > len(flags) / 2,
            "deltas": [round(row["delta_ap"], 6) for row in per_window],
            "sign_stable_positive": all(row["delta_ap"] > 0 for row in per_window),
        }
    pooled = inference.get("pooled", {})
    bootstrap = inference.get("clustered_bootstrap") or {}

    def excludes_zero(clustering: str) -> bool:
        entry = bootstrap.get(clustering) or {}
        low = entry.get("ci_low")
        return low is not None and low > 0

    return {
        "prediction_rows": len(labels),
        "inference": inference,
        "per_window_inference": per_window,
        "decision_inputs": {
            "per_window_majority": majority,
            "pooled_entity_ci_excludes_zero": excludes_zero("entity"),
            "pooled_pair_ci_excludes_zero": excludes_zero("pair"),
            "pooled_delta": (
                pooled.get("model_pr_auc") - pooled.get("baseline_pr_auc")
                if pooled.get("model_pr_auc") is not None else None
            ),
            "rule_satisfied": (
                all(block.get("majority") for block in majority.values())
                and excludes_zero("entity") and excludes_zero("pair")
            ),
        },
    }


# ------------------------------------------------------------------ comparison
def origin_value(origin: str) -> str:
    return str(origin)


def summarize_backtest(backtest: Mapping[str, Any]) -> list[dict[str, Any]]:
    return window_summary(dict(backtest))


def mde_value(inference: Mapping[str, Any]) -> float | None:
    mde = (inference.get("mde") or {}).get("observed_from_entity_cluster_se") or {}
    value = mde.get("mde_delta_ap")
    return float(value) if value is not None else None


def build_comparison(
    old_analysis: Mapping[str, Any],
    new_windows: list[dict[str, Any]],
    new_analysis: Mapping[str, Any],
) -> dict[str, Any]:
    """Old (committed, recomputed cohort) vs new (fixed artefact cohort)."""
    old = (old_analysis.get("panels") or {}).get("p2") or {}
    old_windows = {str(row["origin"]): row for row in old.get("windows") or []}
    old_per_window = {str(row["origin"]): row for row in old.get("per_window_inference") or []}
    old_inference = old.get("inference") or {}
    old_decision = old.get("decision_inputs") or {}
    new_per_window = {str(row["origin"]): row
                      for row in new_analysis["per_window_inference"]}
    new_inference = new_analysis["inference"]
    new_decision = new_analysis["decision_inputs"]

    table = []
    for window in new_windows:
        origin = str(window["origin"])
        old_row = old_windows.get(origin, {})
        old_ci = old_per_window.get(origin, {})
        new_ci = new_per_window.get(origin, {})
        table.append({
            "origin": origin,
            "rows": window["rows"],
            "positives": window["positives"],
            "old_rows": old_row.get("rows"),
            "old_positives": old_row.get("positives"),
            "model_pr_auc": window["model_pr_auc"],
            "old_model_pr_auc": old_row.get("model_pr_auc"),
            "baseline_pr_auc": window["baseline_pr_auc"],
            "old_baseline_pr_auc": old_row.get("baseline_pr_auc"),
            "delta_ap": window["delta_ap"],
            "old_delta_ap": old_row.get("delta_ap"),
            "delta_ap_change": (
                window["delta_ap"] - old_row["delta_ap"]
                if window["delta_ap"] is not None and old_row.get("delta_ap") is not None else None
            ),
            "new_ci_entity": new_ci.get("ci_entity"),
            "old_ci_entity": old_ci.get("ci_entity"),
            "new_ci_pair": new_ci.get("ci_pair"),
            "old_ci_pair": old_ci.get("ci_pair"),
            "new_excludes_zero_entity": new_ci.get("excludes_zero_entity"),
            "old_excludes_zero_entity": old_ci.get("excludes_zero_entity"),
            "new_excludes_zero_pair": new_ci.get("excludes_zero_pair"),
            "old_excludes_zero_pair": old_ci.get("excludes_zero_pair"),
        })

    old_pooled = old_inference.get("pooled") or {}
    new_pooled = new_inference.get("pooled") or {}
    old_delta = old_decision.get("pooled_delta")
    new_delta = new_decision.get("pooled_delta")
    old_mde = mde_value(old_inference)
    new_mde = mde_value(new_inference)
    old_majority = old_decision.get("per_window_majority") or {}
    new_majority = new_decision["per_window_majority"]
    old_rule = bool(old_decision.get("rule_satisfied"))
    new_rule = bool(new_decision["rule_satisfied"])

    direction_unchanged = (
        old_delta is not None and new_delta is not None
        and (old_delta > 0) == (new_delta > 0)
    )
    sign_stable = all(
        block.get("sign_stable_positive") for block in new_majority.values()
    )
    return {
        "headline_old": {
            "pooled_delta_ap": old_delta,
            "mde_delta_ap": old_mde,
            "windows_excluding_zero_entity": (old_majority.get("entity") or {}).get("windows_excluding_zero"),
            "windows_excluding_zero_pair": (old_majority.get("pair") or {}).get("windows_excluding_zero"),
            "per_window_delta_ap": (old_majority.get("entity") or {}).get("deltas"),
            "rule_satisfied": old_rule,
        },
        "headline_new": {
            "pooled_delta_ap": new_delta,
            "mde_delta_ap": new_mde,
            "windows_excluding_zero_entity": (new_majority.get("entity") or {}).get("windows_excluding_zero"),
            "windows_excluding_zero_pair": (new_majority.get("pair") or {}).get("windows_excluding_zero"),
            "per_window_delta_ap": (new_majority.get("entity") or {}).get("deltas"),
            "rule_satisfied": new_rule,
        },
        "pooled": {
            "new_rows": new_pooled.get("rows"),
            "old_rows": old_pooled.get("rows"),
            "new_positives": new_pooled.get("positives"),
            "old_positives": old_pooled.get("positives"),
            "new_model_pr_auc": new_pooled.get("model_pr_auc"),
            "old_model_pr_auc": old_pooled.get("model_pr_auc"),
            "new_baseline_pr_auc": new_pooled.get("baseline_pr_auc"),
            "old_baseline_pr_auc": old_pooled.get("baseline_pr_auc"),
            "delta_change": (
                new_delta - old_delta
                if new_delta is not None and old_delta is not None else None
            ),
            "new_entity_ci": (new_inference.get("clustered_bootstrap") or {}).get("entity"),
            "old_entity_ci": (old_inference.get("clustered_bootstrap") or {}).get("entity"),
            "new_pair_ci": (new_inference.get("clustered_bootstrap") or {}).get("pair"),
            "old_pair_ci": (old_inference.get("clustered_bootstrap") or {}).get("pair"),
            "mde_change": (new_mde - old_mde
                           if new_mde is not None and old_mde is not None else None),
            "delta_above_mde_new": (new_delta > new_mde
                                    if new_delta is not None and new_mde is not None else None),
            "delta_above_mde_old": (old_delta > old_mde
                                    if old_delta is not None and old_mde is not None else None),
        },
        "per_window": table,
        "verdict": {
            "direction_unchanged": direction_unchanged,
            "sign_stable_positive": sign_stable,
            "windows_excluding_zero_unchanged": (
                (new_majority.get("entity") or {}).get("windows_excluding_zero")
                == (old_majority.get("entity") or {}).get("windows_excluding_zero")
                and (new_majority.get("pair") or {}).get("windows_excluding_zero")
                == (old_majority.get("pair") or {}).get("windows_excluding_zero")
            ),
            "rule_satisfied_unchanged": old_rule == new_rule,
            "conclusion_unchanged": bool(
                direction_unchanged
                and sign_stable
                and old_rule == new_rule
                and ((new_majority.get("entity") or {}).get("windows_excluding_zero")
                     == (old_majority.get("entity") or {}).get("windows_excluding_zero"))
                and ((new_majority.get("pair") or {}).get("windows_excluding_zero")
                     == (old_majority.get("pair") or {}).get("windows_excluding_zero"))
            ),
            "magnitude_retained": (
                abs(new_delta) / abs(old_delta)
                if new_delta is not None and old_delta not in (None, 0) else None
            ),
        },
    }


# ---------------------------------------------------------------------- report
def run(
    db_path: Path,
    cohort_path: Path,
    cycle2_dir: Path,
    *,
    holdouts: int = DEFAULT_HOLDOUTS,
    skip_backtest: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    cohort = load_artifact_cohort(cohort_path)
    panel, detail = build_fixed_panel(db_path, cohort)
    old_analysis = json.loads((cycle2_dir / "analysis.json").read_text(encoding="utf-8"))
    old_panel = json.loads((cycle2_dir / "panel_p2.json").read_text(encoding="utf-8"))

    gap = recomputed_cohort_gap(db_path, cohort["key_set"])
    predictions = build_prediction_windows(panel, holdouts=holdouts)
    new_analysis = analyze_predictions(predictions)

    backtest: dict[str, Any] | None = None
    backtest_windows: list[dict[str, Any]] = []
    if not skip_backtest:
        backtest = run_backtest(
            panel["examples"], list(BASE_FEATURES), [],
            min_train_origins=3, horizon_months=HORIZON_MONTHS, holdouts=holdouts,
            specifications=[(SPEC_NAME, "R&D history + entry-specific history, no financial "
                                      "features (same specification as cycle-2 P2)", SPEC_FEATURES)],
            experiment="b102_p2_fixed_cohort",
            data_provenance={
                "panel": "P2 deterministic legal applicant entities, fixed to the artefact cohort",
                "entity_field": "entity",
                "cohort_source": str(cohort_path),
                "cohort_keys": cohort["count"],
                "cohort_sha256": cohort["sha256"],
                "note": "cohort selection is NOT recomputed; it is the committed artefact's key list",
            },
        )
        backtest_windows = summarize_backtest(backtest)
        # The frozen spec must report the same window metrics from the full backtest
        # and from the per-window prediction fits; a mismatch means the harness drifted.
        for backtest_window, prediction_window in zip(backtest_windows, predictions["windows"]):
            if backtest_window["model_pr_auc"] is None or prediction_window["metrics"]["pr_auc"] is None:
                continue
            if abs(backtest_window["model_pr_auc"] - prediction_window["metrics"]["pr_auc"]) > 1e-9:
                raise AssertionError(
                    f"prediction dump disagrees with backtest at {backtest_window['origin']}: "
                    f"{backtest_window['model_pr_auc']} vs {prediction_window['metrics']['pr_auc']}")

    comparison = build_comparison(old_analysis, backtest_windows or _windows_from_predictions(predictions), new_analysis)
    report = {
        "schema": "b102.fixed_cohort_report.v1",
        "backlog_item": "B-017",
        "question": (
            "Re-run the cycle-2 P2 pipeline on the exact 200 cohort keys of config/universe_v1.json "
            "and report whether the conclusion is unchanged."
        ),
        "spec": spec_block(holdouts),
        "inputs": {
            "db": {"path": str(db_path), "sha256": sha256_file(db_path)},
            "cohort": {"path": str(cohort_path), "sha256": cohort["sha256"],
                       "count": cohort["count"], "metadata": cohort["metadata"]},
            "committed_analysis": str(cycle2_dir / "analysis.json"),
        },
        "cohort_gap": gap,
        "panel": {"fixed": detail["panel"], "committed_p2": old_panel.get("panel", {})},
        "panel_difference": {
            "fixed_n_examples": detail["panel"]["n_examples"],
            "committed_n_examples": (old_panel.get("panel") or {}).get("n_examples"),
            "n_examples_change": (
                detail["panel"]["n_examples"] - (old_panel.get("panel") or {}).get("n_examples", 0)
            ),
            "fixed_n_positives": detail["panel"]["n_positives"],
            "committed_n_positives": (old_panel.get("panel") or {}).get("n_positives"),
            "fixed_entity_count": detail["panel"]["entity_count"],
            "committed_entity_count": (old_panel.get("panel") or {}).get("entity_count"),
            "fixed_origins": detail["panel"]["origins"],
            "committed_origins": (old_panel.get("panel") or {}).get("origins"),
        },
        "gap_impact": gap_impact(detail, gap, panel),
        "backtest": {
            "run": not skip_backtest,
            "holdout_origins": (backtest or {}).get("holdout_origins")
            or predictions["holdout_origins"],
            "windows": backtest_windows,
            "note": (
                "Full run_backtest with the frozen P2 specification."
                if not skip_backtest else
                "Skipped (--skip-backtest); window metrics come from the identical per-window "
                "prediction fits, which the committed pipeline also used for inference."
            ),
        },
        "inference": {
            "fixed_cohort": new_analysis,
            "committed_recomputed_cohort": {
                "prediction_rows": (old_analysis.get("panels", {}).get("p2") or {}).get("prediction_rows"),
                "inference": (old_analysis.get("panels", {}).get("p2") or {}).get("inference"),
                "per_window_inference": (old_analysis.get("panels", {}).get("p2") or {}).get("per_window_inference"),
                "decision_inputs": (old_analysis.get("panels", {}).get("p2") or {}).get("decision_inputs"),
            },
        },
        "comparison": comparison,
        "artifacts": {
            "fixed_cohort_report.json": {"committed": False, "regenerable": True},
            "backtest_fixed_cohort.json": {
                "committed": False,
                "regenerable": True,
                "note": "full run_backtest artefact for the fixed-cohort panel"
                if not skip_backtest else "not written (--skip-backtest)",
            },
        },
    }
    return report, backtest


def _windows_from_predictions(predictions: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for window in predictions["windows"]:
        metrics = window.get("metrics") or {}
        baseline = window.get("baseline_metrics") or {}
        rows.append({
            "origin": window["origin"],
            "rows": metrics.get("n", len(window.get("rows") or [])),
            "positives": metrics.get("positives"),
            "model_pr_auc": metrics.get("pr_auc"),
            "baseline_pr_auc": baseline.get("pr_auc"),
            "delta_ap": (metrics.get("pr_auc") - baseline.get("pr_auc")
                         if metrics.get("pr_auc") is not None
                         and baseline.get("pr_auc") is not None else None),
        })
    return rows


# ------------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="B-017 fixed-cohort sensitivity run")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--cohort", default=str(DEFAULT_COHORT))
    parser.add_argument("--cycle2-dir", default=str(DEFAULT_CYCLE2_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--report", default=None)
    parser.add_argument("--backtest-out", default=None)
    parser.add_argument("--holdouts", type=int, default=DEFAULT_HOLDOUTS)
    parser.add_argument("--skip-backtest", action="store_true",
                        help="only fit the 3 holdout windows (faster; inference-identical)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    report_path = Path(args.report) if args.report else out_dir / "fixed_cohort_report.json"
    backtest_path = Path(args.backtest_out) if args.backtest_out else out_dir / "backtest_fixed_cohort.json"
    try:
        report, backtest = run(
            Path(args.db), Path(args.cohort), Path(args.cycle2_dir),
            holdouts=args.holdouts, skip_backtest=args.skip_backtest,
        )
    except (FileNotFoundError, ValueError, AssertionError) as error:
        print(f"[b102] FAIL: {error}", file=sys.stderr)
        return 2
    write_json(report_path, report)
    if backtest is not None:
        write_json(backtest_path, backtest)
    comparison = report["comparison"]
    old = comparison["headline_old"]
    new = comparison["headline_new"]
    print(
        f"[b102] fixed cohort {report['cohort_gap']['artifact_keys']} keys "
        f"(gap {report['cohort_gap']['symmetric_difference']}) | "
        f"pooled delta old={old['pooled_delta_ap']:.6f} new={new['pooled_delta_ap']:.6f} | "
        f"MDE old={old['mde_delta_ap']:.6f} new={new['mde_delta_ap']:.6f} | "
        f"windows excl. zero old={old['windows_excluding_zero_entity']}/{old['windows_excluding_zero_pair']} "
        f"new={new['windows_excluding_zero_entity']}/{new['windows_excluding_zero_pair']} | "
        f"conclusion_unchanged={comparison['verdict']['conclusion_unchanged']}"
    )
    print(f"[b102] wrote {report_path}" + (f" and {backtest_path}" if backtest is not None else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
