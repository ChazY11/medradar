"""S-028-CORRECTION-1: re-run the G2 randomisation comparison on corrected nulls.

The Phase 0-3 G2 comparison was driven by a defective rewiring implementation
(see ``s028_nullmodels`` docstring and ``audit_20_randomisation_invariants.py``).
This script re-runs the *same* pipeline - same panel, same learner, same feature
set, same three holdout windows, same primary metric (AP) - against the two
corrected null models, and re-derives the frozen controls B1 / B2 / G1 from
scratch so their independence from the randomisation bug is demonstrated, not
asserted.

Design decisions, fixed before any corrected result was inspected
---------------------------------------------------------------
* Primary metric: pooled AP over the three pre-registered holdout origins,
  identical to the original study.
* Randomisation count: 40, rising with seed ``20261104 + r``, identical to the
  original run so the comparison is paired by seed.
* Swaps per edge: 10 nominal attempts per edge, identical to the original
  nominal budget.
* No adaptive stopping: the count is fixed by ``--randomisations`` on the
  command line before the run and every draw is kept.
* Both null models are run.  Nothing about the result influences the number of
  draws, the null definition, or the metric.

The original artifacts are never written to.  Output goes to
``artifacts/correction_round_1/``.

Usage
-----
    python s028_g2_corrected.py --label H4q --quarters 4 --model N1
    python s028_g2_corrected.py --label H4q --quarters 4 --model N2
    python s028_g2_corrected.py --label H4q --quarters 4 --controls-only
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from s028_experiment import (  # noqa: E402
    HOLDOUTS, attach_graph, evaluable_origins, run_spec, summarise,
    _pooled_delta, _window_delta,
)
from s028_lib import (B3_FEATURES, BASE_FEATURES, G1_FEATURES,  # noqa: E402
                      SnapshotSeries, build_entry_panel, load_events,
                      verify_frozen_db, write_json)
from s028_nullmodels import N1, N2, NULL_MODELS, NullSnapshotSeries  # noqa: E402

STUDY = Path(__file__).resolve().parents[1]
ARTIFACTS = STUDY / "artifacts"
CORRECTION = ARTIFACTS / "correction_round_1"
DB = Path(r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite")
SPECS = (("B1_history10", list(BASE_FEATURES)),
         ("B2_frozen_spec16", list(B3_FEATURES)),
         ("G1_graph", list(B3_FEATURES) + list(G1_FEATURES)))


def _digest(values: list[Any]) -> str:
    raw = json.dumps(values, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_stored_predictions(label: str) -> dict[str, Any] | None:
    for name in (f"predictions_{label}.json.gz", f"predictions_{label}.json"):
        path = ARTIFACTS / name
        if not path.exists():
            continue
        if name.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return json.load(handle)
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return None


def _compare_to_stored(predictions: dict[str, Any], stored: dict[str, Any],
                       spec: str, holdouts: list[str]) -> dict[str, Any]:
    """Max absolute probability difference for one spec, per holdout window."""
    if not stored or spec not in stored.get("specs", {}):
        return {"stored_present": False}
    stored_predictions = stored["specs"][spec]["predictions"]
    out: dict[str, Any] = {"stored_present": True, "windows": {}}
    worst = 0.0
    for window in holdouts:
        ours, theirs = predictions.get(window), stored_predictions.get(window)
        if ours is None or theirs is None:
            out["windows"][window] = {"present": False}
            continue
        same_labels = ours["labels"] == theirs["labels"]
        same_order = ours["companies"] == theirs["companies"]
        deltas = [abs(a - b) for a, b in zip(ours["probs"], theirs["probs"])]
        maximum = max(deltas) if deltas else None
        worst = max(worst, maximum or 0.0)
        out["windows"][window] = {"present": True, "labels_identical": same_labels,
                                  "row_order_identical": same_order,
                                  "rows": len(ours["labels"]),
                                  "max_abs_probability_diff": maximum}
    out["max_abs_probability_diff"] = worst
    out["identical_tolerance"] = 1e-12
    out["identical"] = worst < 1e-12
    return out


def run_controls(events: list[dict[str, Any]], rows: list[dict[str, Any]],
                 origins: list[str], horizon_months: int,
                 holdouts: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Re-derive B1 / B2 / G1 from scratch and compare with the frozen artifacts."""
    started = time.time()
    series = SnapshotSeries(events, origins)
    rows_graph = attach_graph(rows, series)
    stored = load_stored_predictions(f"__none__")
    controls: dict[str, Any] = {"seconds": None, "specs": {}}
    predictions: dict[str, Any] = {}
    for spec, features in SPECS:
        use_graph = spec == "G1_graph"
        spec_rows = rows_graph if use_graph else rows
        tick = time.time()
        pred = run_spec(spec_rows, features, "logistic", origins, horizon_months)
        summary = summarise(pred, origins, holdouts)
        predictions[spec] = pred
        controls["specs"][spec] = {
            "pooled_pr_auc": summary["pooled"].get("pr_auc"),
            "per_window_pr_auc": {window: summary["per_window"].get(window, {}).get("pr_auc")
                                  for window in holdouts},
            "n_features": len(features),
            "seconds": round(time.time() - tick, 2),
            "test_labels_sha256": {window: _digest(pred[window]["labels"])
                                   for window in holdouts if window in pred},
        }
    controls["seconds"] = round(time.time() - started, 2)
    del stored
    return controls, predictions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="H4q")
    parser.add_argument("--quarters", type=int, default=4)
    parser.add_argument("--model", default=N1, choices=list(NULL_MODELS))
    parser.add_argument("--randomisations", type=int, default=40)
    parser.add_argument("--swaps-per-edge", type=float, default=10.0)
    parser.add_argument("--controls-only", action="store_true")
    parser.add_argument("--skip-controls", action="store_true")
    args = parser.parse_args(argv)

    CORRECTION.mkdir(parents=True, exist_ok=True)
    horizon_months = args.quarters * 3
    db_record = verify_frozen_db(DB)
    events = load_events(DB)
    panel = build_entry_panel(events, entity_field="company_key", horizon_months=horizon_months,
                              label_kind="qualifying",
                              dataset_version=f"s028_correction_{args.label}")
    rows = panel["examples"]
    origins = panel["cutoffs"]
    holdouts = evaluable_origins(rows, origins, horizon_months)[-HOLDOUTS:]
    print(f"[{args.label}] rows={len(rows)} positives={panel['n_positives']} "
          f"origins={len(origins)} holdouts={holdouts}", flush=True)
    manifest = {"label": args.label, "horizon_quarters": args.quarters,
                "horizon_months": horizon_months, "database": db_record,
                "panel": {"n_examples": len(rows), "n_positives": panel["n_positives"],
                          "origins": len(origins), "origins_list": origins,
                          "holdouts": holdouts},
                "randomisations": args.randomisations,
                "swaps_per_edge": args.swaps_per_edge,
                "test_labels_sha256": {},
                "controls": None}

    predictions_controls: dict[str, Any] = {}
    if not args.skip_controls:
        controls, predictions_controls = run_controls(events, rows, origins, horizon_months, holdouts)
        manifest["controls"] = controls
        print("[controls]", json.dumps({spec: data["pooled_pr_auc"]
                                        for spec, data in controls["specs"].items()}), flush=True)

    if args.controls_only:
        out = CORRECTION / f"frozen_controls_check_{args.label}.json"
        write_json(out, manifest)
        print("wrote", out)
        return 0

    series = SnapshotSeries(events, origins)
    real_rows = attach_graph(rows, series)
    if "G1_graph" in predictions_controls:
        real = predictions_controls["G1_graph"]
        stored = load_stored_predictions(args.label)
        if stored:
            manifest["G1_vs_stored"] = _compare_to_stored(real, stored, "G1_graph", holdouts)
            for spec in ("B1_history10", "B2_frozen_spec16"):
                manifest.setdefault("controls_vs_stored", {})[spec] = _compare_to_stored(
                    predictions_controls[spec], stored, spec, holdouts)
    else:
        tick = time.time()
        real = run_spec(real_rows, list(B3_FEATURES) + list(G1_FEATURES), "logistic",
                        origins, horizon_months)
        print(f"[G1 refit] {round(time.time() - tick, 1)}s", flush=True)
    real_summary = summarise(real, origins, holdouts)
    real_pooled = real_summary["pooled"].get("pr_auc")
    real_per_window = {window: real_summary["per_window"].get(window, {}).get("pr_auc")
                       for window in holdouts}
    manifest["real_graph"] = {"pooled_pr_auc": real_pooled,
                              "per_window_pr_auc": real_per_window,
                              "test_labels_sha256": {window: _digest(real[window]["labels"])
                                                     for window in holdouts if window in real}}
    manifest["test_labels_sha256"] = manifest["real_graph"]["test_labels_sha256"]
    print(f"[real G1] pooled AP={real_pooled}", flush=True)

    records: list[dict[str, Any]] = []
    started = time.time()
    for index in range(args.randomisations):
        seed = 20261104 + index
        tick = time.time()
        null_series = NullSnapshotSeries(events, origins, null_model=args.model, seed=seed,
                                         swaps_per_edge=args.swaps_per_edge)
        null_rows = attach_graph(rows, null_series)
        predictions = run_spec(null_rows, list(B3_FEATURES) + list(G1_FEATURES), "logistic",
                               origins, horizon_months)
        summary = summarise(predictions, origins, holdouts)
        invariants = _summarise_invariants(null_series.null_stats)
        record = {
            "seed": seed, "index": index, "null_model": args.model,
            "pooled_ap": summary["pooled"].get("pr_auc"),
            "per_window_ap": {window: summary["per_window"].get(window, {}).get("pr_auc")
                              for window in holdouts},
            "pooled_delta_vs_real": _pooled_delta(predictions, real, holdouts),
            "per_window_delta_vs_real": {window: _window_delta(predictions, real, window)
                                         for window in holdouts},
            "test_labels_sha256": {window: _digest(predictions[window]["labels"])
                                   for window in holdouts if window in predictions},
            "invariants": invariants,
            "seconds": round(time.time() - tick, 2),
        }
        records.append(record)
        print(f"  [{args.label}/{args.model}] r={index + 1}/{args.randomisations} "
              f"seed={seed} pooledAP={record['pooled_ap']:.6f} "
              f"dAP={record['pooled_delta_vs_real']:+.6f} "
              f"deg_ok={invariants['all_degrees_preserved']} "
              f"simple={invariants['all_simple']} "
              f"acc={invariants['swap_acceptance_rate_mean']:.3f} "
              f"chg={invariants['edges_changed_fraction_min']:.3f}", flush=True)

    deltas = [row["pooled_delta_vs_real"] for row in records
              if row["pooled_delta_vs_real"] is not None]
    pooled = sorted(row["pooled_ap"] for row in records if row["pooled_ap"] is not None)
    real_minus_null = sorted(-value for value in deltas)
    randomisation_summary = {
        "null_model": args.model, "n_randomisations": len(records),
        "randomised_pooled_ap_min": pooled[0] if pooled else None,
        "randomised_pooled_ap_median": pooled[len(pooled) // 2] if pooled else None,
        "randomised_pooled_ap_max": pooled[-1] if pooled else None,
        "real_pooled_ap": real_pooled,
        "real_minus_randomised_median": (real_minus_null[len(real_minus_null) // 2]
                                         if real_minus_null else None),
        "real_minus_randomised_q025": (real_minus_null[int(0.025 * len(real_minus_null))]
                                       if real_minus_null else None),
        "real_minus_randomised_q975": (real_minus_null[min(len(real_minus_null) - 1,
                                                           int(0.975 * len(real_minus_null)))]
                                       if real_minus_null else None),
        "fraction_randomisations_beating_real": (
            sum(1 for value in pooled if real_pooled is not None and value >= real_pooled) / len(pooled)
            if pooled else None),
        "real_above_all_randomisations": bool(pooled and real_pooled is not None
                                              and real_pooled > pooled[-1]),
        "exact_one_sided_randomisation_p": (1.0 / (len(records) + 1)) if records else None,
        "lowest_achievable_one_sided_p": (1.0 / (len(records) + 1)) if records else None,
        "interpretation_note": (
            "Under a valid null the randomised graph is expected to score at or below the real "
            "graph if the real relational structure carries information, and to score above it "
            "if the real graph is worse than chance-conditional-on-margins. A high randomised "
            "AP is a statement about the real graph, not evidence that random relations predict."),
        "invariants_all_degrees_preserved": all(row["invariants"]["all_degrees_preserved"]
                                               for row in records),
        "invariants_all_simple": all(row["invariants"]["all_simple"] for row in records),
        "invariants_all_node_sets_preserved": all(row["invariants"]["all_node_sets_preserved"]
                                                  for row in records),
        "runtime_seconds": round(time.time() - started, 1),
    }
    payload = {**manifest, "model": args.model, "records": records,
               "summary": randomisation_summary}
    out = CORRECTION / f"g2_corrected_{args.label}_{args.model}.json"
    write_json(out, payload)
    print("\nwrote", out)
    print(json.dumps(randomisation_summary, indent=2, default=str))
    return 0


def _summarise_invariants(null_stats: dict[str, Any]) -> dict[str, Any]:
    """Compact per-randomisation invariant digest over every origin snapshot."""
    rows = list(null_stats.values())
    weight_modes: dict[str, int] = {}
    for row in rows:
        mode = row.get("weight_mode")
        if mode:
            weight_modes[mode] = weight_modes.get(mode, 0) + 1
    acceptance = [row["acceptance_rate"] for row in rows if row.get("acceptance_rate") is not None]
    changed = [row["edges_changed_fraction"] for row in rows
               if row.get("edges_changed_fraction") is not None]
    return {
        "origins": len(rows),
        "all_degrees_preserved": all(row.get("degree_sequences_equal") for row in rows),
        "all_simple": all(row.get("simple") for row in rows),
        "all_node_sets_preserved": all(row.get("node_sets_equal") for row in rows),
        "all_total_event_counts_preserved": all(row.get("total_event_count_equal") for row in rows),
        "all_track_entry_multisets_preserved": all(row.get("track_entry_date_multisets_equal")
                                                  for row in rows),
        "swap_acceptance_rate_mean": (sum(acceptance) / len(acceptance)) if acceptance else None,
        "swap_acceptance_rate_min": min(acceptance) if acceptance else None,
        "edges_changed_fraction_mean": (sum(changed) / len(changed)) if changed else None,
        "edges_changed_fraction_min": min(changed) if changed else None,
        "max_company_strength_deviation": max(row.get("max_abs_company_strength_deviation", 0.0)
                                             for row in rows) if rows else None,
        "max_track_strength_deviation": max(row.get("max_abs_track_strength_deviation", 0.0)
                                           for row in rows) if rows else None,
        "temporal_total_variation_mean": (sum(row["temporal_total_variation_mean"] for row in rows
                                              if row.get("temporal_total_variation_mean") is not None)
                                         / max(1, sum(1 for row in rows
                                                      if row.get("temporal_total_variation_mean")
                                                      is not None))),
        "weight_modes": weight_modes,
    }


if __name__ == "__main__":
    raise SystemExit(main())
