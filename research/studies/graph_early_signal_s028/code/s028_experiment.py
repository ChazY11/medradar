"""S-028 experiment driver: rolling-origin, purged, paired graph-vs-baseline.

Two modes:

``--validate-frozen``
    Rebuild the frozen cycle-2 P1 panel (material label, H=12m, company_key) and
    reproduce its published holdout APs. This is the mandatory harness check:
    if it fails, no S-028 number may be reported.

``--mode main``
    The pre-registered S-028 experiment on the qualifying-event target, for the
    primary (H=4 quarters) and secondary (H=2 quarters) horizons, including the
    B0/B1/B2/B3 baselines, G1 graph features, G2 degree-preserving randomised
    graphs (R repetitions) and the G3 ablations.

Usage:
    python s028_experiment.py --validate-frozen
    python s028_experiment.py --mode main --randomisations 20
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import numpy as np  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from medradar.intelligence.evaluation.backtesting import matured_by  # noqa: E402
from medradar.intelligence.evaluation.metrics import evaluate, pr_auc  # noqa: E402
from medradar.util import add_months, iso, parse_date  # noqa: E402

from s028_lib import (  # noqa: E402
    B3_FEATURES, BASE_FEATURES, CENTRALITY_FEATURES, COOCCURRENCE_FEATURES,
    FastLogisticRegression, G1_FEATURES, PEER_ENTRY_FEATURES, SIMILARITY_FEATURES,
    SnapshotSeries, TWOHOP_FEATURES, ap_parity_check, build_entry_panel, fast_ap,
    load_events, paired_cluster_bootstrap, parity_check, verify_frozen_db, write_json,
)

STUDY = Path(__file__).resolve().parents[1]
ARTIFACTS = STUDY / "artifacts"
DB = Path(r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite")
MIN_TRAIN_ORIGINS = 3
HOLDOUTS = 3
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 7
MDE_Z = 1.959964 + 0.841621  # 97.5% and 80% standard normal quantiles


# ------------------------------------------------------------------- learners
def make_logistic(features: list[str]) -> FastLogisticRegression:
    return FastLogisticRegression(features)


def make_hgb(features: list[str]) -> Any:
    return _HGB(features)


class _HGB:
    """Fixed-hyperparameter gradient boosting wrapper with the same API."""

    def __init__(self, features: list[str]) -> None:
        self.feature_names = list(features)
        self.medians: dict[str, float] = {}
        self.model = HistGradientBoostingClassifier(
            max_depth=3, max_iter=120, learning_rate=0.06, l2_regularization=1.0,
            min_samples_leaf=40, random_state=20261104)

    def _matrix(self, rows: list[dict[str, Any]], fit: bool = False) -> np.ndarray:
        matrix = np.empty((len(rows), len(self.feature_names)), dtype=float)
        for j, name in enumerate(self.feature_names):
            column = []
            for row in rows:
                value = row.get(name)
                try:
                    value = float(value) if value is not None else float("nan")
                except (TypeError, ValueError):
                    value = float("nan")
                column.append(value if math.isfinite(value) else float("nan"))
            matrix[:, j] = column
        return matrix

    def fit(self, rows: list[dict[str, Any]], labels: list[int]) -> "_HGB":
        self.model.fit(self._matrix(rows), labels)
        return self

    def predict_proba(self, rows: list[dict[str, Any]]) -> list[float]:
        return self.model.predict_proba(self._matrix(rows))[:, 1].tolist()


# ---------------------------------------------------------------- evaluation
def eligible_training_rows(rows: list[dict[str, Any]], origin: str,
                           horizon_months: int) -> list[dict[str, Any]]:
    """Purged expanding window: a row may train origin t iff cutoff + H <= t."""
    out = []
    for row in rows:
        cutoff = parse_date(row["cutoff"])
        if cutoff is None or cutoff >= parse_date(origin):
            continue
        if not matured_by(cutoff, parse_date(origin), horizon_months):
            continue
        out.append(row)
    return out


def evaluable_origins(rows: list[dict[str, Any]], origins: list[str],
                      horizon_months: int) -> list[str]:
    return [origin for origin in origins
            if eligible_training_rows(rows, origin, horizon_months)]


def run_spec(rows: list[dict[str, Any]], features: list[str], learner: str,
             origins: list[str], horizon_months: int) -> dict[str, Any]:
    """Fit at every origin from ``MIN_TRAIN_ORIGINS`` and return per-origin predictions."""
    predictions: dict[str, Any] = {}
    for index, origin in enumerate(origins):
        if index < MIN_TRAIN_ORIGINS:
            continue
        train = eligible_training_rows(rows, origin, horizon_months)
        test = [row for row in rows if row["cutoff"] == origin]
        if not train or not test or len({row["label"] for row in train}) < 2:
            continue
        model = make_logistic(features) if learner == "logistic" else make_hgb(features)
        model.fit([row["features"] for row in train], [int(row["label"]) for row in train])
        probabilities = model.predict_proba([row["features"] for row in test])
        predictions[origin] = {
            "labels": [int(row["label"]) for row in test],
            "probs": probabilities,
            "companies": [row["company_key"] for row in test],
            "tracks": [row["track_id"] for row in test],
            "pairs": [f"{row['company_key']}|{row['track_id']}" for row in test],
            "lead_days": _lead_days(test),
        }
    return predictions


def _lead_days(rows: list[dict[str, Any]]) -> list[int | None]:
    out = []
    for row in rows:
        if not row["label"] or not row.get("first_target_event_date"):
            out.append(None)
            continue
        start, end = parse_date(row["cutoff"]), parse_date(row["first_target_event_date"])
        out.append((end - start).days if start and end else None)
    return out


def persistence_predictions(rows: list[dict[str, Any]], origins: list[str],
                            horizon_months: int) -> dict[str, dict[str, list[float]]]:
    """Frozen B0 predictors: constant, company, track and pair base rates."""
    result: dict[str, dict[str, list[float]]] = {}
    for origin in origins:
        train = eligible_training_rows(rows, origin, horizon_months)
        test = [row for row in rows if row["cutoff"] == origin]
        if not train or not test:
            continue
        prevalence = sum(int(row["label"]) for row in train) / len(train)
        entry: dict[str, list[float]] = {}
        for name, key_fn in (
                ("constant_training_prevalence", lambda row: None),
                ("company_base_rate", lambda row: row["company_key"]),
                ("track_base_rate", lambda row: row["track_id"]),
                ("pair_base_rate", lambda row: (row["company_key"], row["track_id"]))):
            history: dict[Any, list[int]] = defaultdict(list)
            for row in train:
                history[key_fn(row)].append(int(row["label"]))
            entry[name] = [sum(history[key_fn(row)]) / len(history[key_fn(row)])
                           if history.get(key_fn(row)) else prevalence for row in test]
        result[origin] = entry
    return result


def metrics(labels: list[int], probs: list[float], leads: list[int | None] | None = None) -> dict[str, Any]:
    base = evaluate(labels, probs, lead_times=leads or [])
    n, positives = len(labels), sum(labels)
    k = max(1, math.ceil(n * 0.10))
    ranking = sorted(zip(probs, labels), key=lambda pair: pair[0], reverse=True)[:k]
    hit = sum(label for _, label in ranking)
    out = {**base,
           "roc_auc": float(roc_auc_score(labels, probs)) if 0 < positives < n else None,
           "recall_at_k": hit / positives if positives else None,
           "n": n, "positives": positives}
    return out


def _ap(labels: list[int], probs: list[float]) -> float | None:
    return fast_ap(labels, probs)


def cluster_bootstrap_delta(pred_a: dict[str, Any], pred_b: dict[str, Any],
                           windows: list[str], *, resamples: int = BOOTSTRAP_RESAMPLES,
                           seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Paired bootstrap of AP(a) - AP(b) under both pre-registered clusterings."""
    company = paired_cluster_bootstrap(pred_a, pred_b, windows, "company",
                                       resamples=resamples, seed=seed)
    pair = paired_cluster_bootstrap(pred_a, pred_b, windows, "pair",
                                    resamples=resamples, seed=seed)
    return {"company": company, "pair": pair}


def summarise(predictions: dict[str, Any], origins: list[str], holdouts: list[str]) -> dict[str, Any]:
    per_window = {}
    for origin in holdouts:
        block = predictions.get(origin)
        if block is None:
            per_window[origin] = {"evaluable": False}
            continue
        per_window[origin] = {"evaluable": True,
                              **metrics(block["labels"], block["probs"], block["lead_days"])}
    pooled_labels, pooled_probs, pooled_leads = [], [], []
    for origin in holdouts:
        block = predictions.get(origin)
        if block is None:
            continue
        pooled_labels.extend(block["labels"])
        pooled_probs.extend(block["probs"])
        pooled_leads.extend(block["lead_days"])
    pooled = metrics(pooled_labels, pooled_probs, pooled_leads) if pooled_labels else {}
    return {"per_window": per_window, "pooled": pooled}


# --------------------------------------------------------------------- modes
def validate_frozen() -> dict[str, Any]:
    print("== frozen-harness validation ==")
    verify_frozen_db(DB)
    events = load_events(DB)
    panel = build_entry_panel(events, entity_field="company_key", horizon_months=12,
                              label_kind="material", dataset_version="first_entry_v1")
    rows = panel["examples"]
    origins = panel["cutoffs"]
    print(f"panel: {len(rows)} rows, {panel['n_positives']} positives, {len(origins)} origins")
    checks = parity_check(rows, [int(r["label"]) for r in rows], list(B3_FEATURES))
    print("learner parity:", checks)
    ap_parity = ap_parity_check()
    print("AP parity:", ap_parity)
    predictions = run_spec(rows, list(B3_FEATURES), "logistic", origins, 12)
    persistence = persistence_predictions(rows, origins, 12)
    holdouts = evaluable_origins(rows, origins, 12)[-HOLDOUTS:]
    frozen_reference = {
        "2025-04-01": {"rows": 1722, "positives": 25, "ap": 0.137085, "persistence": 0.079463},
        "2025-07-01": {"rows": 1721, "positives": 27, "ap": 0.095027, "persistence": 0.047244},
        "2025-10-01": {"rows": 1716, "positives": 26, "ap": 0.100476, "persistence": 0.027826},
    }
    comparison = {}
    for origin in holdouts:
        block = predictions[origin]
        pair = persistence[origin]["pair_base_rate"]
        observed_ap = _ap(block["labels"], block["probs"])
        observed_persistence = _ap(block["labels"], pair)
        reference = frozen_reference.get(origin, {})
        comparison[origin] = {
            "rows": len(block["labels"]), "positives": sum(block["labels"]),
            "expected_rows": reference.get("rows"), "expected_positives": reference.get("positives"),
            "ap": observed_ap, "expected_ap": reference.get("ap"),
            "persistence_ap": observed_persistence,
            "expected_persistence_ap": reference.get("persistence"),
            "ap_abs_diff": (abs(observed_ap - reference["ap"])
                            if observed_ap is not None and reference.get("ap") else None),
            "ok_rows": len(block["labels"]) == reference.get("rows"),
            "ok_positives": sum(block["labels"]) == reference.get("positives"),
            "ok_ap": (abs(observed_ap - reference["ap"]) < 5e-6
                      if observed_ap is not None and reference.get("ap") else False),
        }
    pooled_labels, pooled_probs, pooled_pair = [], [], []
    for origin in holdouts:
        pooled_labels.extend(predictions[origin]["labels"])
        pooled_probs.extend(predictions[origin]["probs"])
        pooled_pair.extend(persistence[origin]["pair_base_rate"])
    pooled = {"rows": len(pooled_labels), "positives": sum(pooled_labels),
              "ap": _ap(pooled_labels, pooled_probs),
              "expected_ap": 0.101060,
              "persistence_ap": _ap(pooled_labels, pooled_pair),
              "expected_persistence_ap": 0.044614}
    pooled["ok_rows"] = pooled["rows"] == 5159
    pooled["ok_positives"] = pooled["positives"] == 78
    pooled["ok_ap"] = abs(pooled["ap"] - pooled["expected_ap"]) < 5e-6
    pooled["ok_persistence"] = abs(pooled["persistence_ap"]
                                   - pooled["expected_persistence_ap"]) < 5e-6
    overall = (all(value["ok_rows"] and value["ok_positives"] and value["ok_ap"]
                   for value in comparison.values())
               and pooled["ok_rows"] and pooled["ok_positives"]
               and pooled["ok_ap"] and pooled["ok_persistence"])
    result = {"mode": "frozen_validation", "panel": {
        "n_examples": len(rows), "n_positives": panel["n_positives"],
        "origins": len(origins), "holdouts": holdouts},
        "learner_parity": checks, "ap_parity": ap_parity,
        "per_window": comparison, "pooled": pooled,
        "overall_ok": overall and ap_parity["ok"]}
    write_json(ARTIFACTS / "frozen_validation.json", result)
    print(json.dumps(comparison, indent=2))
    print("pooled:", json.dumps(pooled, indent=2))
    print("OVERALL:", "PASS" if overall else "FAIL")
    return result


SPEC_DEFINITIONS: dict[str, list[str]] = {
    "B1_history10": list(BASE_FEATURES),
    "B2_frozen_spec16": list(B3_FEATURES),
    "G1_graph": list(B3_FEATURES) + list(G1_FEATURES),
    "G3_no_peer_entry": list(B3_FEATURES) + [f for f in G1_FEATURES if f not in PEER_ENTRY_FEATURES],
    "G3_no_similarity": list(B3_FEATURES) + [f for f in G1_FEATURES if f not in SIMILARITY_FEATURES],
    "G3_no_twohop": list(B3_FEATURES) + [f for f in G1_FEATURES if f not in TWOHOP_FEATURES],
    "G3_no_cooccurrence": list(B3_FEATURES) + [f for f in G1_FEATURES if f not in COOCCURRENCE_FEATURES],
    "G3_no_centrality": list(B3_FEATURES) + [f for f in G1_FEATURES if f not in CENTRALITY_FEATURES],
    "G3_no_decay": list(B3_FEATURES) + [f for f in G1_FEATURES
                                        if f not in ("g_coentry_decay", "g_twohop_activity_decay")],
}
FEATURE_NAMES = {"B1_history10": list(BASE_FEATURES), "B2_frozen_spec16": list(B3_FEATURES),
                 "G1_graph": list(B3_FEATURES) + list(G1_FEATURES)}
for _name, _features in SPEC_DEFINITIONS.items():
    FEATURE_NAMES[_name] = _features


def attach_graph(rows: list[dict[str, Any]], series: SnapshotSeries) -> list[dict[str, Any]]:
    """Return copies of ``rows`` whose feature dict includes this snapshot series."""
    out = []
    for row in rows:
        features = dict(row["features"])
        features.update(series.features_for(row["cutoff"], row["company_key"], row["track_id"]))
        clone = dict(row)
        clone["features"] = features
        out.append(clone)
    return out


def run_horizon(events: list[dict[str, Any]], horizon_quarters: int, *,
                randomisations: int, label: str) -> dict[str, Any]:
    horizon_months = horizon_quarters * 3
    started = time.time()
    panel = build_entry_panel(events, entity_field="company_key",
                              horizon_months=horizon_months, label_kind="qualifying",
                              dataset_version=f"s028_{label}")
    base_rows = panel["examples"]
    origins = panel["cutoffs"]
    holdouts = evaluable_origins(base_rows, origins, horizon_months)[-HOLDOUTS:]
    print(f"[{label}] rows={len(base_rows)} pos={panel['n_positives']} origins={len(origins)} "
          f"holdouts={holdouts}", flush=True)

    series = SnapshotSeries(events, origins)
    rows_with_graph = attach_graph(base_rows, series)

    result: dict[str, Any] = {
        "mode": "main", "label": label, "horizon_quarters": horizon_quarters,
        "horizon_months": horizon_months, "panel": {
            "n_examples": len(base_rows), "n_positives": panel["n_positives"],
            "base_rate": panel["n_positives"] / len(base_rows) if base_rows else None,
            "origins": len(origins), "origins_list": origins,
            "holdouts": holdouts,
            "positives_by_origin": panel["positives_by_origin"],
            "candidates_by_origin": panel["candidates_by_origin"],
            "coverage_start": panel["coverage_start"], "coverage_end": panel["coverage_end"],
            "entity_count": panel["entity_count"], "track_count": panel["track_count"],
            "observed_pair_count": panel["observed_pair_count"]},
        "specs": {}, "b0": {}, "times": {},
    }

    # B0 persistence baselines
    persistence = persistence_predictions(base_rows, origins, horizon_months)
    b0 = {}
    for name in ("constant_training_prevalence", "company_base_rate", "track_base_rate",
                 "pair_base_rate"):
        block = {origin: {"labels": [int(r["label"]) for r in base_rows if r["cutoff"] == origin],
                          "probs": persistence[origin][name],
                          "companies": [r["company_key"] for r in base_rows if r["cutoff"] == origin],
                          "lead_days": _lead_days([r for r in base_rows if r["cutoff"] == origin])}
                 for origin in holdouts if origin in persistence}
        b0[name] = summarise(block, origins, holdouts)
    result["b0"] = b0

    # B1, B2 (== B3), G1 and the G3 ablations: identical learner, only features differ
    for spec, features in SPEC_DEFINITIONS.items():
        use_graph = any(name in G1_FEATURES for name in features)
        rows = rows_with_graph if use_graph else base_rows
        tick = time.time()
        predictions = run_spec(rows, features, "logistic", origins, horizon_months)
        summary = summarise(predictions, origins, holdouts)
        summary["n_features"] = len(features)
        summary["features"] = features
        summary["seconds"] = round(time.time() - tick, 1)
        result["specs"][spec] = {"predictions": predictions, "summary": summary}

    # stronger non-graph learner (robustness only)
    for spec, features in (("B2g_hgb_spec16", list(B3_FEATURES)),
                           ("G1g_hgb_graph", list(B3_FEATURES) + list(G1_FEATURES))):
        tick = time.time()
        rows = rows_with_graph if spec.startswith("G1") else base_rows
        predictions = run_spec(rows, features, "hgb", origins, horizon_months)
        summary = summarise(predictions, origins, holdouts)
        summary["n_features"] = len(features)
        summary["seconds"] = round(time.time() - tick, 1)
        result["specs"][spec] = {"predictions": predictions, "summary": summary}

    # G2: degree-preserving randomised graphs, R repetitions, same pipeline
    randomisation_records = []
    reference = result["specs"]["G1_graph"]["predictions"]
    for r in range(randomisations):
        seed = 20261104 + r
        rand_series = SnapshotSeries(events, origins, randomised=True, seed=seed)
        rand_rows = attach_graph(base_rows, rand_series)
        predictions = run_spec(rand_rows, list(B3_FEATURES) + list(G1_FEATURES), "logistic",
                               origins, horizon_months)
        summary = summarise(predictions, origins, holdouts)
        delta = _pooled_delta(predictions, reference, holdouts)
        randomisation_records.append({
            "seed": seed,
            "pooled_ap": summary["pooled"].get("pr_auc"),
            "per_window_ap": {origin: summary["per_window"][origin].get("pr_auc")
                              for origin in holdouts},
            "pooled_delta_vs_real": delta,
            "per_window_delta_vs_real": {
                origin: _window_delta(predictions, reference, origin) for origin in holdouts},
        })
        if r == 0:
            result["specs"]["G2_randomised_example"] = {"predictions": predictions,
                                                        "summary": summary, "seed": seed}
        print(f"  [{label}] randomisation {r + 1}/{randomisations} pooled AP="
              f"{summary['pooled'].get('pr_auc')} delta={delta}", flush=True)
    result["g2"] = {"randomisations": randomisation_records,
                    "real_pooled_ap": result["specs"]["G1_graph"]["summary"]["pooled"].get("pr_auc"),
                    "real_per_window_ap": {
                        origin: result["specs"]["G1_graph"]["summary"]["per_window"][origin].get("pr_auc")
                        for origin in holdouts}}

    # paired deltas vs B2 (H1) and vs randomised graphs (H2)
    comparisons = {}
    for spec in ("B1_history10", "G1_graph", "G3_no_peer_entry", "G3_no_similarity",
                 "G3_no_twohop", "G3_no_cooccurrence", "G3_no_centrality", "G3_no_decay",
                 "B2g_hgb_spec16", "G1g_hgb_graph"):
        comparisons[f"{spec}_minus_B2"] = cluster_bootstrap_delta(
            result["specs"][spec]["predictions"],
            result["specs"]["B2_frozen_spec16"]["predictions"], holdouts)
    result["comparisons"] = comparisons
    result["times"]["total_seconds"] = round(time.time() - started, 1)
    return result


def _window_delta(pred_a: dict[str, Any], pred_b: dict[str, Any], origin: str) -> float | None:
    a, b = pred_a.get(origin), pred_b.get(origin)
    if a is None or b is None:
        return None
    ap_a, ap_b = _ap(a["labels"], a["probs"]), _ap(b["labels"], b["probs"])
    return (ap_a - ap_b) if ap_a is not None and ap_b is not None else None


def _pooled_delta(pred_a: dict[str, Any], pred_b: dict[str, Any],
                  windows: list[str]) -> float | None:
    labels, a, b = [], [], []
    for origin in windows:
        if origin in pred_a and origin in pred_b:
            labels.extend(pred_a[origin]["labels"])
            a.extend(pred_a[origin]["probs"])
            b.extend(pred_b[origin]["probs"])
    if not labels:
        return None
    ap_a, ap_b = _ap(labels, a), _ap(labels, b)
    return (ap_a - ap_b) if ap_a is not None and ap_b is not None else None


def holdout_only(result: dict[str, Any]) -> dict[str, Any]:
    """Keep only holdout-origin predictions: enough to re-derive every reported number."""
    holdouts = set(result["panel"]["holdouts"])
    clone = json.loads(json.dumps(result, default=str))
    for spec in clone.get("specs", {}).values():
        predictions = spec.get("predictions")
        if predictions:
            spec["predictions"] = {origin: block for origin, block in predictions.items()
                                   if origin in holdouts}
    return clone


def strip_predictions(result: dict[str, Any]) -> dict[str, Any]:
    """Drop the large per-row prediction arrays before writing the JSON artifact."""
    clone = json.loads(json.dumps(result, default=str))
    for spec in clone.get("specs", {}).values():
        spec.pop("predictions", None)
    return clone


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="main", choices=["main", "validate"])
    parser.add_argument("--randomisations", type=int, default=20)
    parser.add_argument("--horizons", default="4,2")
    args = parser.parse_args(argv)
    if args.mode == "validate":
        validate_frozen()
        return 0
    verify_frozen_db(DB)
    events = load_events(DB)
    horizons = [int(part) for part in args.horizons.split(",") if part.strip()]
    summary: dict[str, Any] = {"study": "S-028", "db_sha256": None,
                               "horizons": {}, "protocol": {
                                   "dormancy_months": 36, "min_train_origins": MIN_TRAIN_ORIGINS,
                                   "holdouts": HOLDOUTS, "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
                                   "bootstrap_seed": BOOTSTRAP_SEED,
                                   "randomisations": args.randomisations,
                                   "learner": "FastLogisticRegression(epochs=180, lr=0.15, l2=1.0)"}}
    from s028_lib import FROZEN_DB_SHA256
    summary["db_sha256"] = FROZEN_DB_SHA256
    for quarters in horizons:
        label = f"H{quarters}q"
        result = run_horizon(events, quarters, randomisations=args.randomisations, label=label)
        write_json(ARTIFACTS / f"experiment_{label}.json", strip_predictions(result))
        write_json(ARTIFACTS / f"predictions_{label}.json", holdout_only(result))
        summary["horizons"][label] = {
            "panel": result["panel"],
            "b0": {name: value["pooled"] for name, value in result["b0"].items()},
            "specs": {name: {"pooled": value["summary"]["pooled"],
                             "per_window": value["summary"]["per_window"],
                             "n_features": value["summary"]["n_features"]}
                      for name, value in result["specs"].items() if name != "G2_randomised_example"},
            "comparisons": result["comparisons"],
            "g2": result["g2"],
            "times": result["times"],
        }
        print(f"[{label}] done in {result['times']['total_seconds']}s")
    write_json(ARTIFACTS / "experiment_summary.json", summary)
    print("wrote", ARTIFACTS / "experiment_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
