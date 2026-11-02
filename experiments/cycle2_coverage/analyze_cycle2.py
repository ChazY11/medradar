"""Cycle-2 analysis: original-panel vs expanded-entity-panel, with honest inference.

Reads the frozen backtest artifacts and the per-row prediction dumps, then reports:
  * panel comparison (rows, positives, observed pairs, base rate);
  * per-window and pooled average precision for model and persistence baseline;
  * cluster-aware bootstrap CIs on the paired AP difference (entity and pair clusters);
  * minimum detectable effect at the observed positive count;
  * lead time at a matched false-alarm rate, with censored units counted;
  * heterogeneity by technology track and entity activity scale.

If ``medradar.intelligence.evalstats`` is unavailable, the affected blocks are
reported as ``unavailable`` rather than silently approximated.

Usage:
    python experiments/cycle2_coverage/analyze_cycle2.py
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence.evaluation.metrics import pr_auc  # noqa: E402
from experiments.cycle2_coverage.panel import write_json  # noqa: E402

try:  # optional dependency on a sibling deliverable
    from medradar.intelligence import evalstats  # type: ignore
    EVALSTATS_ERROR = None
except Exception as exc:  # noqa: BLE001 - report, do not hide
    evalstats = None  # type: ignore
    EVALSTATS_ERROR = f"{type(exc).__name__}: {exc}"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def window_summary(backtest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for window in backtest["holdout_windows"]:
        model = (window["model_metrics"].get("rd_plus_entry_history")
                 or next(iter(window["model_metrics"].values()), {}))
        baseline = window["baseline_predictors"].get("pair_base_rate", {})
        rows.append({
            "origin": window["origin"],
            "rows": window["rows"],
            "positives": window["positives"],
            "prevalence": window["prevalence"],
            "training_rows": window["training_rows"],
            "model_pr_auc": model.get("pr_auc"),
            "baseline_pr_auc": baseline.get("pr_auc"),
            "delta_ap": ((model.get("pr_auc") - baseline.get("pr_auc"))
                         if model.get("pr_auc") is not None
                         and baseline.get("pr_auc") is not None else None),
            "model_brier": model.get("brier"),
            "baseline_brier": baseline.get("brier"),
            "precision_at_k": model.get("precision_at_k"),
            "baseline_precision_at_k": baseline.get("precision_at_k"),
            "lead_time_days": model.get("mean_lead_time_days"),
        })
    return rows


def pool_rows(predictions: dict[str, Any]) -> tuple[list[int], list[float], list[float],
                                                    list[str], list[str], list[str]]:
    labels: list[int] = []
    model: list[float] = []
    baseline: list[float] = []
    entities: list[str] = []
    pairs: list[str] = []
    origins: list[str] = []
    for window in predictions["windows"]:
        for row in window["rows"]:
            if row.get("baseline_probability") is None:
                continue  # keep the pairing exact
            labels.append(int(row["label"]))
            model.append(float(row["probability"]))
            baseline.append(float(row["baseline_probability"]))
            entities.append(f"E:{row['entity']}")
            pairs.append(f"P:{row['entity']}|{row['track']}")
            origins.append(f"O:{window['origin']}")
    return labels, model, baseline, entities, pairs, origins


def analyze_inference(labels: list[int], model: list[float], baseline: list[float],
                      entities: list[str], pairs: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"evalstats_available": evalstats is not None,
                              "evalstats_error": EVALSTATS_ERROR}
    result["pooled"] = {
        "rows": len(labels),
        "positives": sum(labels),
        "prevalence": sum(labels) / len(labels) if labels else None,
        "model_pr_auc": pr_auc(labels, model),
        "baseline_pr_auc": pr_auc(labels, baseline),
        "entity_clusters": len(set(entities)),
        "pair_clusters": len(set(pairs)),
    }
    if evalstats is None:
        result["clustered_bootstrap"] = "unavailable"
        result["mde"] = "unavailable"
        return result

    clustered = {}
    for name, clusters in (("entity", entities), ("pair", pairs)):
        try:
            clustered[name] = evalstats.clustered_bootstrap_delta_ap(
                labels, model, baseline, clusters, resamples=2000, seed=7)
        except Exception as exc:  # noqa: BLE001
            clustered[name] = {"error": f"{type(exc).__name__}: {exc}"}
    result["clustered_bootstrap"] = clustered

    # Preferred MDE route: the observed bootstrap SE includes the real score
    # distribution's design effect, so it is not the optimistic design-stage value.
    mde: dict[str, Any] = {}
    entity_ci = clustered.get("entity", {})
    if isinstance(entity_ci, dict) and entity_ci.get("se_delta"):
        try:
            mde["observed_from_entity_cluster_se"] = evalstats.mde_from_se(entity_ci["se_delta"])
        except Exception as exc:  # noqa: BLE001
            mde["observed_from_entity_cluster_se"] = {"error": f"{type(exc).__name__}: {exc}"}
    for name, n_pos in (("design_stage_pooled", sum(labels)),
                        ("design_stage_cycle1_26_positives", 26),
                        ("design_stage_cycle2_46_positives", 46)):
        try:
            mde[name] = evalstats.average_precision_mde(len(labels), n_pos)
        except Exception as exc:  # noqa: BLE001
            mde[name] = {"error": f"{type(exc).__name__}: {exc}"}
    result["mde"] = mde
    return result


def analyze_lead_time(predictions: dict[str, Any], censor_date: str | None) -> dict[str, Any]:
    windows = []
    for window in predictions["windows"]:
        rows = [row for row in window["rows"] if row.get("baseline_probability") is not None]
        labels = [int(row["label"]) for row in rows]
        model = [float(row["probability"]) for row in rows]
        baseline = [float(row["baseline_probability"]) for row in rows]
        lead = [row.get("lead_days") for row in rows]
        positives = sum(labels)
        # View 1 (transparent, weak): both scorers select the same k units.
        k = max(1, math.ceil(len(rows) * 0.10))
        entry: dict[str, Any] = {"origin": window["origin"], "rows": len(rows),
                                 "positives": positives, "k": k}
        for name, scores in (("model", model), ("baseline", baseline)):
            order = sorted(range(len(rows)), key=lambda index: scores[index], reverse=True)[:k]
            detected = [index for index in order if labels[index]]
            entry[name] = {
                "selected": len(order),
                "true_positives": len(detected),
                "precision": len(detected) / len(order) if order else None,
                "mean_lead_days": (sum(lead[index] for index in detected) / len(detected)
                                   if detected else None),
                "censored_positives": positives - len(detected),
            }
        # View 2 (the one to cite): matched false-alarm budget for both scorers.
        if evalstats is not None:
            units = [
                {
                    "unit_id": f"{row['entity']}|{row['track']}",
                    "label": int(row["label"]),
                    "score_a": float(row["probability"]),
                    "score_b": float(row["baseline_probability"]),
                    "origin_date": window["origin"],
                    "event_date": row.get("target_date"),
                    "censor_date": censor_date,
                }
                for row in rows
            ]
            try:
                entry["matched_far"] = evalstats.matched_far_lead_time(
                    units, scores=("score_a", "score_b"), label_key="label",
                    event_date_key="event_date", origin_date_key="origin_date",
                    censor_date_key="censor_date", unit_id_key="unit_id", far=0.10)
            except Exception as exc:  # noqa: BLE001
                entry["matched_far"] = {"error": f"{type(exc).__name__}: {exc}"}
        windows.append(entry)
    return {"definition": (
        "Two lead-time views. (1) naive: both scorers select the same k units (10% of rows), "
        "so top-k precision is comparable but the false-alarm count is not controlled. "
        "(2) matched FAR (cite this one): identical false-positive budget "
        "m = floor(far * n_negatives) for both scorers, censored positives counted, "
        "positives without observable lead excluded and reported."),
        "censor_date": censor_date,
        "windows": windows}


def analyze_heterogeneity(predictions: dict[str, Any], universe: dict[str, Any] | None,
                          min_rows: int = 60, min_positives: int = 5) -> dict[str, Any]:
    scale: dict[str, int] = {}
    if universe:
        for record in universe.get("entities", []):
            scale[str(record["entity_key"])] = int(record.get("n_material") or 0)
    by_track: dict[str, dict[str, Any]] = {}
    by_scale: dict[str, dict[str, Any]] = {"high_activity": {"labels": [], "model": [], "baseline": []},
                                          "lower_activity": {"labels": [], "model": [], "baseline": []}}
    for window in predictions["windows"]:
        for row in window["rows"]:
            if row.get("baseline_probability") is None:
                continue
            bucket = by_track.setdefault(str(row["track"]), {"labels": [], "model": [], "baseline": []})
            for target in (bucket,):
                target["labels"].append(int(row["label"]))
                target["model"].append(float(row["probability"]))
                target["baseline"].append(float(row["baseline_probability"]))
            material = scale.get(str(row["entity"]), 0)
            group = "high_activity" if material >= 20 else "lower_activity"
            by_scale[group]["labels"].append(int(row["label"]))
            by_scale[group]["model"].append(float(row["probability"]))
            by_scale[group]["baseline"].append(float(row["baseline_probability"]))

    def summarize(buckets: dict[str, dict[str, list[Any]]]) -> dict[str, Any]:
        out = {}
        for name, bucket in sorted(buckets.items()):
            n, positives = len(bucket["labels"]), sum(bucket["labels"])
            if n < min_rows or positives < min_positives:
                out[name] = {"n": n, "positives": positives, "status": "insufficient"}
                continue
            model_ap = pr_auc(bucket["labels"], bucket["model"])
            base_ap = pr_auc(bucket["labels"], bucket["baseline"])
            out[name] = {"n": n, "positives": positives, "prevalence": positives / n,
                         "model_pr_auc": model_ap, "baseline_pr_auc": base_ap,
                         "delta_ap": (model_ap - base_ap)
                         if model_ap is not None and base_ap is not None else None}
        return out

    return {
        "strata": {"min_rows": min_rows, "min_positives": min_positives,
                   "scale_split": "entity n_material >= 20 (high_activity) vs below",
                   "note": "pre-declared strata; no post-hoc subgroup selection; "
                           "multiplicity not corrected in this descriptive table"},
        "by_track": summarize(by_track),
        "by_entity_activity": summarize(by_scale),
    }


def analyze_per_window(predictions: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-window cluster-aware ΔAP, needed by the pre-registered decision rule."""
    results: list[dict[str, Any]] = []
    for window in predictions["windows"]:
        rows = [row for row in window["rows"] if row.get("baseline_probability") is not None]
        labels = [int(row["label"]) for row in rows]
        model = [float(row["probability"]) for row in rows]
        baseline = [float(row["baseline_probability"]) for row in rows]
        entities = [f"E:{row['entity']}" for row in rows]
        pairs = [f"P:{row['entity']}|{row['track']}" for row in rows]
        entry: dict[str, Any] = {
            "origin": window["origin"], "rows": len(rows), "positives": sum(labels),
            "model_pr_auc": pr_auc(labels, model),
            "baseline_pr_auc": pr_auc(labels, baseline),
            "delta_ap": (pr_auc(labels, model) - pr_auc(labels, baseline)),
        }
        if evalstats is not None:
            for name, clusters in (("entity", entities), ("pair", pairs)):
                try:
                    ci = evalstats.clustered_bootstrap_delta_ap(
                        labels, model, baseline, clusters, resamples=2000, seed=7)
                    entry[f"ci_{name}"] = {key: ci.get(key) for key in
                                           ("delta", "ci_low", "ci_high", "se_delta",
                                            "p_delta_le_zero", "n_clusters")}
                    entry[f"excludes_zero_{name}"] = (
                        ci.get("ci_low") is not None and ci.get("ci_low") > 0)
                except Exception as exc:  # noqa: BLE001
                    entry[f"ci_{name}"] = {"error": f"{type(exc).__name__}: {exc}"}
        results.append(entry)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="experiments/cycle2_coverage")
    parser.add_argument("--universe", default="config/universe_v1.json")
    args = parser.parse_args(argv)
    base = Path(args.dir)

    out: dict[str, Any] = {"evalstats": {"available": evalstats is not None,
                                        "error": EVALSTATS_ERROR},
                           "panels": {}}
    for panel in ("p1", "p2"):
        backtest_path = base / f"backtest_{panel if panel == 'p2' else 'p1_same_spec'}.json"
        pred_path = base / f"pred_{panel}.json"
        panel_out: dict[str, Any] = {}
        if backtest_path.exists():
            backtest = load(backtest_path)
            panel_out["windows"] = window_summary(backtest)
            panel_out["holdout_origins"] = backtest.get("holdout_origins")
            panel_out["experiment"] = backtest.get("experiment")
        if pred_path.exists():
            predictions = load(pred_path)
            labels, model, baseline, entities, pairs, origins = pool_rows(predictions)
            panel_out["prediction_rows"] = len(labels)
            panel_out["inference"] = analyze_inference(labels, model, baseline, entities, pairs)
            per_window = analyze_per_window(predictions)
            panel_out["per_window_inference"] = per_window
            majority = {}
            for clustering in ("entity", "pair"):
                flags = [row.get(f"excludes_zero_{clustering}") for row in per_window]
                majority[clustering] = {
                    "windows_total": len(flags),
                    "windows_excluding_zero": sum(1 for flag in flags if flag),
                    "majority": sum(1 for flag in flags if flag) > len(flags) / 2,
                    "deltas": [round(row["delta_ap"], 6) for row in per_window],
                    "sign_stable_positive": all(row["delta_ap"] > 0 for row in per_window),
                }
            pooled = panel_out["inference"].get("pooled", {})
            bootstrap = panel_out["inference"].get("clustered_bootstrap") or {}

            def excludes_zero(clustering: str) -> bool:
                entry = bootstrap.get(clustering) or {}
                low = entry.get("ci_low")
                return low is not None and low > 0

            panel_out["decision_inputs"] = {
                "pre_registered_rule": (
                    "H2.2: signal is SUPPORTED if the cluster CI on delta-AP excludes zero in "
                    "the majority of pre-declared windows AND pooled CIs exclude zero under BOTH "
                    "clustering choices; it is a WELL-POWERED NEGATIVE if the pooled point "
                    "estimate is inside the MDE but no CI excludes zero; otherwise still "
                    "underpowered."),
                "per_window_majority": majority,
                "pooled_entity_ci_excludes_zero": excludes_zero("entity"),
                "pooled_pair_ci_excludes_zero": excludes_zero("pair"),
                "pooled_delta": (pooled.get("model_pr_auc") - pooled.get("baseline_pr_auc")
                                 if pooled.get("model_pr_auc") is not None else None),
                "rule_satisfied": (
                    all(block.get("majority") for block in majority.values())
                    and excludes_zero("entity") and excludes_zero("pair")),
            }
            panel_meta_path = base / f"panel_{panel}.json"
            censor_date = None
            if panel_meta_path.exists():
                censor_date = load(panel_meta_path).get("panel", {}).get("coverage_end")
            panel_out["lead_time"] = analyze_lead_time(predictions, censor_date)
            universe = load(Path(args.universe)) if Path(args.universe).exists() else None
            panel_out["heterogeneity"] = analyze_heterogeneity(predictions, universe)
        out["panels"][panel] = panel_out

    write_json(base / "analysis.json", out)

    # Console summary
    for panel, payload in out["panels"].items():
        print(f"\n=== {panel} ===")
        for window in payload.get("windows", []):
            print(f"  {window['origin']}: n={window['rows']} pos={window['positives']} "
                  f"AP={window['model_pr_auc']} base={window['baseline_pr_auc']} "
                  f"d={window['delta_ap']}")
        inference = payload.get("inference", {})
        if inference:
            pooled = inference.get("pooled", {})
            print(f"  pooled: n={pooled.get('rows')} pos={pooled.get('positives')} "
                  f"AP={pooled.get('model_pr_auc')} base={pooled.get('baseline_pr_auc')} "
                  f"clusters={pooled.get('entity_clusters')}E/{pooled.get('pair_clusters')}P")
            print("  clustered:", json.dumps(inference.get("clustered_bootstrap"))[:400])
            print("  mde:", json.dumps(inference.get("mde"))[:400])
    print(f"\nwrote {base / 'analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
