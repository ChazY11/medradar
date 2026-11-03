#!/usr/bin/env python3
"""B-018 / b105: re-test the source-group nulls on the P2 entity panel with MDEs.

Reads the panel emitted by ``build_entity_panel_with_sources.py`` and evaluates
four specifications on identical rows, origins, purge rule and model:

    reference     16 features (``rd_plus_entry_history``)
    +financial    + 11 consolidated SEC features
    +market       +  8 point-in-time market features
    +publication  +  5 OpenAlex publication features

Headline inference is the committed cycle-2 convention: pooled average precision
over the three holdout windows, with a **company-clustered** paired bootstrap
(2,000 resamples, seed 20261103). Entities nest in companies, so the cluster is
the parent company where the exact entity -> company join exists, and the entity
itself otherwise (unmapped entities are their own cluster; reported).

Pre-declared acceptance rule (stated before looking at the results):

* a group is **EVALUABLE** only if it covers >= 20% of the pooled holdout rows
  *and* >= 20 holdout positives; otherwise **NOT_EVALUABLE** with the measured
  coverage, no proxy substituted;
* a null is **well-powered negative** only if its MDE is <= 0.02 ΔAP (2 AP
  points; the parent-level feature-group marginals were all |ΔAP| <= 0.0054, so
  0.02 is a conservative bound on an effect worth excluding), otherwise
  **underpowered**;
* a CI that excludes zero on the positive side is reported as a positive
  association, never as a null.

Usage:
    python experiments/b105_source_groups/run_analysis.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(ROOT))

from experiments.b105_source_groups.build_entity_panel_with_sources import (  # noqa: E402
    BASE_PANEL_FEATURES,
    SOURCE_GROUPS,
    read_panel,
)
from medradar.intelligence import evalstats  # noqa: E402
from medradar.intelligence.evaluation.backtesting import eligible_training_rows  # noqa: E402
from medradar.intelligence.evaluation.metrics import pr_auc  # noqa: E402
from medradar.intelligence.models.baseline import LogisticBaseline  # noqa: E402

DEFAULT_PANEL = SCRIPT_DIR / "panel_entity_sources.jsonl.gz"
DEFAULT_RESULTS = SCRIPT_DIR / "results.json"
DEFAULT_COMMITTED_P2 = ROOT / "experiments" / "cycle2_coverage" / "analysis.json"
DEFAULT_PARENT_ABLATION = ROOT / "experiments" / "reverse_rd_v2" / "ablation_metrics.json"
HOLDOUTS = 3
HORIZON_MONTHS = 12
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20261103
MODEL_SPEC = {"epochs": 180, "learning_rate": 0.15, "l2": 1.0}
COVERAGE_FLOOR_ROWS = 0.20
COVERAGE_FLOOR_POSITIVES = 20
MDE_WELL_POWERED_THRESHOLD = 0.02
REFERENCE_SPEC = "reference"

#: Parent-level ``reverse_rd_v2`` entry-target marginal ΔAP for each group. The
#: parent reference D already contains financial, so financial's parent marginal
#: is D - C; market is E - D and publication is F - D.
PARENT_MARGINALS = {
    "financial": {"reference_spec": "C", "group_spec": "D",
                  "note": "D (C + financial) minus C"},
    "market": {"reference_spec": "D", "group_spec": "E",
               "note": "E (D + market) minus D"},
    "publication": {"reference_spec": "D", "group_spec": "F",
                    "note": "F (D + publication) minus D"},
}


# ------------------------------------------------------------------- panel load
def feature_vectors(rows: list[dict[str, Any]], feature_names: list[str]) -> list[dict[str, float | None]]:
    return [{name: row["features"].get(name) for name in feature_names} for row in rows]


def spec_features(group: str | None) -> list[str]:
    features = list(BASE_PANEL_FEATURES)
    if group is not None:
        features += list(SOURCE_GROUPS[group])
    return features


def holdout_origins(rows: list[dict[str, Any]], holdouts: int = HOLDOUTS) -> tuple[list[str], list[str]]:
    origins = sorted({str(row["cutoff"]) for row in rows})
    evaluable = [
        cutoff for cutoff in origins
        if eligible_training_rows(rows, cutoff, purge=True, horizon_months=HORIZON_MONTHS)
    ]
    if holdouts > len(evaluable):
        raise ValueError(f"holdouts={holdouts} exceeds {len(evaluable)} evaluable origins")
    return origins, evaluable[-holdouts:]


def predict_windows(rows: list[dict[str, Any]], origins: list[str],
                    feature_names: list[str]) -> dict[str, Any]:
    """Fit the frozen model on each holdout origin and return per-row predictions."""
    windows = []
    for origin in origins:
        train = eligible_training_rows(rows, origin, purge=True, horizon_months=HORIZON_MONTHS)
        test = [row for row in rows if str(row["cutoff"]) == origin]
        model = LogisticBaseline(feature_names, **MODEL_SPEC).fit(
            feature_vectors(train, feature_names), [int(row["label"]) for row in train])
        probabilities = model.predict_proba(feature_vectors(test, feature_names))
        windows.append({
            "origin": origin,
            "training_rows": len(train),
            "rows": [
                {
                    "example_id": row["example_id"],
                    "label": int(row["label"]),
                    "probability": probability,
                    "entity": row["entity"],
                    "parent_company": row.get("parent_company") or "",
                    "track": row["track"],
                    "cutoff": row["cutoff"],
                    "source_available": row.get("source_available") or {},
                }
                for row, probability in zip(test, probabilities)
            ],
        })
    return {"feature_names": list(feature_names), "windows": windows}


def pooled_rows(predictions: dict[str, Any]) -> dict[str, list[Any]]:
    labels: list[int] = []
    probability: list[float] = []
    clusters: list[str] = []
    entities: list[str] = []
    availability: dict[str, list[bool]] = {group: [] for group in SOURCE_GROUPS}
    for window in predictions["windows"]:
        for row in window["rows"]:
            labels.append(int(row["label"]))
            probability.append(float(row["probability"]))
            parent = str(row.get("parent_company") or "")
            clusters.append(f"C:{parent}" if parent else f"E:{row['entity']}")
            entities.append(f"E:{row['entity']}")
            for group in SOURCE_GROUPS:
                availability[group].append(bool((row.get("source_available") or {}).get(group)))
    return {"labels": labels, "probability": probability, "clusters": clusters,
            "entities": entities, "availability": availability}


def window_metrics(predictions: dict[str, Any]) -> list[dict[str, Any]]:
    windows = []
    for window in predictions["windows"]:
        labels = [int(row["label"]) for row in window["rows"]]
        probabilities = [float(row["probability"]) for row in window["rows"]]
        windows.append({
            "origin": window["origin"],
            "rows": len(labels),
            "positives": sum(labels),
            "pr_auc": pr_auc(labels, probabilities),
        })
    return windows


def coverage_for(group: str, pooled: dict[str, list[Any]]) -> dict[str, Any]:
    flags = pooled["availability"][group]
    labels = pooled["labels"]
    rows = len(flags)
    positives = sum(labels)
    covered_rows = sum(1 for flag in flags if flag)
    covered_positives = sum(1 for flag, label in zip(flags, labels) if flag and label)
    return {
        "holdout_rows": rows,
        "holdout_rows_with_group": covered_rows,
        "holdout_row_coverage": covered_rows / rows if rows else None,
        "holdout_positives": positives,
        "holdout_positives_with_group": covered_positives,
        "holdout_positive_coverage": covered_positives / positives if positives else None,
    }


def classify(group: str, coverage: dict[str, Any], ci: dict[str, Any],
             mde: dict[str, Any], delta: float | None) -> dict[str, Any]:
    """Apply the pre-declared acceptance rule; never return an unqualified null."""
    covered = (coverage["holdout_row_coverage"] or 0.0) >= COVERAGE_FLOOR_ROWS and (
        coverage["holdout_positives_with_group"] >= COVERAGE_FLOOR_POSITIVES)
    if not covered:
        return {
            "evaluable": False,
            "verdict": "NOT_EVALUABLE",
            "statement": (
                f"group data covers {coverage['holdout_rows_with_group']}/{coverage['holdout_rows']} "
                f"holdout rows and {coverage['holdout_positives_with_group']}/"
                f"{coverage['holdout_positives']} holdout positives, below the pre-declared "
                f"floor ({COVERAGE_FLOOR_ROWS:.0%} of rows and {COVERAGE_FLOOR_POSITIVES} "
                f"positives); no proxy substituted"),
        }
    ci_low = ci.get("ci_low")
    ci_high = ci.get("ci_high")
    mde_value = mde.get("mde_delta_ap")
    if ci_low is not None and ci_low > 0:
        return {
            "evaluable": True,
            "verdict": "positive_association",
            "statement": (
                f"ΔAP {delta:+.6f} with company-clustered 95% CI excluding zero on the "
                f"positive side (low {ci_low:+.6f}); not a null"),
        }
    if ci_high is not None and ci_high < 0:
        return {
            "evaluable": True,
            "verdict": "negative_association",
            "statement": (
                f"ΔAP {delta:+.6f} with company-clustered 95% CI excluding zero on the "
                f"negative side (high {ci_high:+.6f}): adding the group is associated with "
                f"worse ranking than the reference; this is not a null"),
        }
    if mde_value is None:
        return {"evaluable": True, "verdict": "underpowered",
                "statement": "bootstrap SE unavailable; MDE not computable"}
    if float(mde_value) <= MDE_WELL_POWERED_THRESHOLD:
        return {
            "evaluable": True,
            "verdict": "well-powered negative",
            "statement": (
                f"no detectable ΔAP (point {delta:+.6f}, CI crosses zero) and the MDE "
                f"{mde_value:.6f} <= {MDE_WELL_POWERED_THRESHOLD:.2f} ΔAP: an effect worth "
                f"0.02 AP is excluded"),
        }
    return {
        "evaluable": True,
        "verdict": "underpowered",
        "statement": (
            f"no detectable ΔAP (point {delta:+.6f}, CI crosses zero), but the MDE "
            f"{mde_value:.6f} > {MDE_WELL_POWERED_THRESHOLD:.2f} ΔAP: effects up to "
            f"{mde_value:.3f} AP cannot be excluded; this is not evidence of no effect"),
    }


# ------------------------------------------------------------ committed compare
def load_committed_reference(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path)}
    analysis = json.loads(path.read_text(encoding="utf-8"))
    p2 = (analysis.get("panels") or {}).get("p2") or {}
    return {
        "available": True,
        "path": str(path),
        "windows": [
            {"origin": str(window["origin"]), "rows": window["rows"],
             "positives": window["positives"], "pr_auc": window["model_pr_auc"]}
            for window in p2.get("windows") or []
        ],
        "pooled_model_pr_auc": (p2.get("inference") or {}).get("pooled", {}).get("model_pr_auc"),
        "holdout_origins": (p2.get("holdout_origins") or []),
    }


def parent_marginals(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path)}
    document = json.loads(path.read_text(encoding="utf-8"))
    entry = ((document.get("targets") or {}).get("entry") or {})
    marginal_deltas = entry.get("marginal_deltas") or {}
    specs = entry.get("specs") or {}

    def spec_pr_auc(name: str) -> float | None:
        block = specs.get(name) or {}
        return (block.get("holdout_metrics") or {}).get("pr_auc")

    values: dict[str, Any] = {}
    for group, plan in PARENT_MARGINALS.items():
        reference_ap = spec_pr_auc(plan["reference_spec"])
        group_ap = spec_pr_auc(plan["group_spec"])
        values[group] = {
            "reference_spec": plan["reference_spec"],
            "group_spec": plan["group_spec"],
            "reference_pr_auc": reference_ap,
            "group_pr_auc": group_ap,
            "delta_ap": (group_ap - reference_ap
                         if group_ap is not None and reference_ap is not None else None),
            "note": plan["note"],
        }
    # Cross-check the difference against the committed marginal-delta block.
    for group, committed in {
        "financial": -(marginal_deltas.get("C", {}).get("delta", {}).get("pr_auc") or 0.0),
        "market": (marginal_deltas.get("E", {}).get("delta", {}).get("pr_auc")),
        "publication": (marginal_deltas.get("F", {}).get("delta", {}).get("pr_auc")),
    }.items():
        if committed is not None and values.get(group, {}).get("delta_ap") is not None:
            values[group]["committed_marginal_delta"] = committed
    return {
        "available": True,
        "path": str(path),
        "reference_spec": entry.get("reference_spec"),
        "protocol": document.get("protocol") or {},
        "marginals": values,
    }


def compare_with_parent(entity_deltas: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    if not parent.get("available"):
        return {"available": False}
    table = {}
    for group, entity in entity_deltas.items():
        parents = parent["marginals"].get(group) or {}
        entity_delta = entity.get("delta_ap")
        parent_delta = parents.get("delta_ap")
        table[group] = {
            "entity_delta_ap": entity_delta,
            "parent_delta_ap": parent_delta,
            "delta_of_deltas": (entity_delta - parent_delta
                                if entity_delta is not None and parent_delta is not None else None),
            "same_sign": (None if entity_delta is None or parent_delta is None
                          else (entity_delta > 0) == (parent_delta > 0)),
        }
    return {
        "available": True,
        "table": table,
        "note": ("parent reference D already contains financial, so the parent financial "
                 "marginal is D - C; the entity reference is the 16-feature panel, so each "
                 "entity ΔAP is that group added to the 16 features"),
    }


# ------------------------------------------------------------------------ run
def run(panel_path: Path, *, results_path: Path, committed_path: Path,
        parent_path: Path, holdouts: int = HOLDOUTS,
        write_predictions: bool = False) -> dict[str, Any]:
    rows = read_panel(panel_path)
    mature = [row for row in rows if row["label"] is not None]
    origins, holds = holdout_origins(mature, holdouts)
    specs = {REFERENCE_SPEC: spec_features(None)}
    for group in SOURCE_GROUPS:
        specs[group] = spec_features(group)

    predictions = {name: predict_windows(mature, holds, features)
                   for name, features in specs.items()}
    pooled = {name: pooled_rows(value) for name, value in predictions.items()}
    windows = {name: window_metrics(value) for name, value in predictions.items()}
    reference = pooled[REFERENCE_SPEC]
    reference_ap = pr_auc(reference["labels"], reference["probability"])

    committed = load_committed_reference(committed_path)
    reference_matches = None
    if committed.get("available"):
        expected = {str(row["origin"]): row for row in committed["windows"]}
        matches = []
        for window in windows[REFERENCE_SPEC]:
            row = expected.get(str(window["origin"]))
            matches.append(row is not None and window["pr_auc"] is not None
                           and abs(window["pr_auc"] - row["pr_auc"]) <= 1e-9)
        reference_matches = bool(
            all(matches) and committed.get("pooled_model_pr_auc") is not None
            and abs(reference_ap - committed["pooled_model_pr_auc"]) <= 1e-9)

    groups: dict[str, Any] = {}
    entity_deltas: dict[str, Any] = {}
    for group in SOURCE_GROUPS:
        candidate = pooled[group]
        candidate_ap = pr_auc(candidate["labels"], candidate["probability"])
        delta = candidate_ap - reference_ap
        coverage = coverage_for(group, candidate)
        ci = evalstats.clustered_bootstrap_delta_ap(
            reference["labels"], candidate["probability"], reference["probability"],
            candidate["clusters"], resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED)
        mde = {}
        if ci.get("se_delta"):
            try:
                mde = evalstats.mde_from_se(ci["se_delta"])
            except (TypeError, ValueError) as error:  # pragma: no cover - defensive
                mde = {"error": f"{type(error).__name__}: {error}"}
        verdict = classify(group, coverage, ci, mde, delta)
        per_window = []
        for reference_window, group_window in zip(windows[REFERENCE_SPEC], windows[group]):
            per_window.append({
                "origin": group_window["origin"],
                "rows": group_window["rows"],
                "positives": group_window["positives"],
                "reference_pr_auc": reference_window["pr_auc"],
                "group_pr_auc": group_window["pr_auc"],
                "delta_ap": (group_window["pr_auc"] - reference_window["pr_auc"])
                if group_window["pr_auc"] is not None
                and reference_window["pr_auc"] is not None else None,
            })
        groups[group] = {
            "features_added": list(SOURCE_GROUPS[group]),
            "n_features_added": len(SOURCE_GROUPS[group]),
            "pooled_pr_auc_reference": reference_ap,
            "pooled_pr_auc_group": candidate_ap,
            "delta_ap": delta,
            "per_window": per_window,
            "coverage": coverage,
            "company_clustered_bootstrap": {
                key: ci.get(key) for key in (
                    "delta", "ci_low", "ci_high", "se_delta", "p_delta_le_zero",
                    "n_clusters", "n_rows", "n_positives", "resamples", "seed",
                    "cluster_method", "skipped_resamples", "valid_resamples")
            },
            "mde": mde,
            "verdict": verdict,
            "clusters": {
                "parent_company": sum(1 for cluster in candidate["clusters"] if cluster.startswith("C:")),
                "unmapped_entity": sum(1 for cluster in candidate["clusters"] if cluster.startswith("E:")),
                "distinct_clusters": len(set(candidate["clusters"])),
            },
        }
        entity_deltas[group] = {
            "delta_ap": delta,
            "ci_low": ci.get("ci_low"),
            "ci_high": ci.get("ci_high"),
            "mde_delta_ap": mde.get("mde_delta_ap"),
            "verdict": verdict["verdict"],
        }

    parent = parent_marginals(parent_path)
    comparison = compare_with_parent(entity_deltas, parent)
    spec_table = {}
    for name, feature_names in specs.items():
        window_rows = windows[name]
        ap_values = [row["pr_auc"] for row in window_rows if row["pr_auc"] is not None]
        spec_table[name] = {
            "n_features": len(feature_names),
            "features": feature_names,
            "per_window": window_rows,
            "mean_window_pr_auc": (sum(ap_values) / len(ap_values) if ap_values else None),
            "pooled_pr_auc": pr_auc(pooled[name]["labels"], pooled[name]["probability"]),
        }

    results = {
        "schema": "b105.source_group_retest.v1",
        "backlog_item": "B-018",
        "question": ("Do consolidated financial, market and publication features add ranking "
                     "value on the P2 entity panel, and is each null well-powered or underpowered?"),
        "design": {
            "panel": str(panel_path),
            "reference_features": list(BASE_PANEL_FEATURES),
            "n_reference_features": len(BASE_PANEL_FEATURES),
            "source_groups": {group: list(names) for group, names in SOURCE_GROUPS.items()},
            "holdout_origins": holds,
            "all_origins": origins,
            "horizon_months": HORIZON_MONTHS,
            "purge_rule": "cutoff + 12 months <= origin",
            "holdouts": holdouts,
            "model": "LogisticBaseline(epochs=180, learning_rate=0.15, l2=1.0)",
            "rows": len(pooled[REFERENCE_SPEC]["labels"]),
            "positives": sum(pooled[REFERENCE_SPEC]["labels"]),
            "clusters": "parent company (entity -> company exact join); unmapped entities as "
                        "their own cluster",
            "bootstrap": {"resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED,
                          "confidence_level": 0.95,
                          "implementation": "medradar.intelligence.evalstats."
                                            "clustered_bootstrap_delta_ap (percentile CI)"},
            "mde": "evalstats.mde_from_se(clustered_bootstrap se_delta)",
            "predeclared_rule": {
                "coverage_floor_rows": COVERAGE_FLOOR_ROWS,
                "coverage_floor_positives": COVERAGE_FLOOR_POSITIVES,
                "well_powered_mde_threshold": MDE_WELL_POWERED_THRESHOLD,
                "verdicts": ["NOT_EVALUABLE", "positive_association",
                             "negative_association", "well-powered negative",
                             "underpowered"],
                "no_unqualified_null": True,
            },
            "entity_join": ("entity -> company_key only when the store's 510(k)/PMA rows for "
                            "that exact entity key carry one distinct company_key"),
        },
        "reference_validation": {
            "committed_analysis": committed,
            "reference_matches_committed_windows_and_pooled": reference_matches,
            "note": ("the 16-feature reference is re-fitted on the frozen P2 panel; it should "
                     "reproduce the committed P2 window and pooled AP exactly if the harness "
                     "is faithful"),
        },
        "specifications": spec_table,
        "groups": groups,
        "comparison_with_parent_level_ablation": comparison,
        "parent_level": parent,
    }
    if write_predictions:
        results["predictions"] = {
            name: {"feature_names": value["feature_names"],
                   "windows": value["windows"]}
            for name, value in predictions.items()
        }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    return results


def summarise(results: dict[str, Any]) -> str:
    lines = []
    for name, spec in results["specifications"].items():
        lines.append(
            f"  {name:<12} features={spec['n_features']:<3} pooled AP="
            f"{spec['pooled_pr_auc']:.6f} mean window AP={spec['mean_window_pr_auc']:.6f}")
    for group, payload in results["groups"].items():
        verdict = payload["verdict"]["verdict"]
        delta = payload["delta_ap"]
        ci = payload["company_clustered_bootstrap"]
        mde = (payload.get("mde") or {}).get("mde_delta_ap")
        lines.append(
            f"  {group:<12} ΔAP={delta:+.6f} CI[{ci.get('ci_low')}, {ci.get('ci_high')}] "
            f"MDE={mde} -> {verdict}")
    return "\n".join(lines)


def reclassify(results_path: Path) -> dict[str, Any]:
    """Re-apply the current verdict rule to a stored results.json (no refitting).

    The verdict is a pure function of the stored coverage, bootstrap CI and MDE;
    this mode lets a wording/threshold fix be applied without refitting the four
    specifications. It never changes a metric.
    """
    results = json.loads(results_path.read_text(encoding="utf-8"))
    for group, payload in (results.get("groups") or {}).items():
        payload["verdict"] = classify(
            group, payload["coverage"], payload["company_clustered_bootstrap"],
            payload.get("mde") or {}, payload.get("delta_ap"))
    results.setdefault("design", {}).setdefault("predeclared_rule", {})["verdicts"] = [
        "NOT_EVALUABLE", "positive_association", "negative_association",
        "well-powered negative", "underpowered"]
    results_path.write_text(
        json.dumps(results, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="B-018 source-group re-test on the P2 panel")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--committed-p2", default=str(DEFAULT_COMMITTED_P2))
    parser.add_argument("--parent-ablation", default=str(DEFAULT_PARENT_ABLATION))
    parser.add_argument("--holdouts", type=int, default=HOLDOUTS)
    parser.add_argument("--write-predictions", action="store_true",
                        help="embed per-row predictions in results.json (large; audit only)")
    parser.add_argument("--reclassify", action="store_true",
                        help="re-apply the verdict rule to an existing results.json; no refit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.reclassify:
        results = reclassify(Path(args.results))
        print(summarise(results))
        print(f"[b105] reclassified {args.results} (no metric changed)")
        return 0
    try:
        results = run(
            Path(args.panel), results_path=Path(args.results),
            committed_path=Path(args.committed_p2), parent_path=Path(args.parent_ablation),
            holdouts=args.holdouts, write_predictions=args.write_predictions,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"[b105] FAIL: {error}", file=sys.stderr)
        return 2
    print("[b105] reference validation against committed P2: "
          f"{results['reference_validation']['reference_matches_committed_windows_and_pooled']}")
    print(summarise(results))
    print(f"[b105] wrote {args.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
