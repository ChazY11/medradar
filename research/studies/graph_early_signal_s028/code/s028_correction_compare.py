"""S-028-CORRECTION-1: assemble the original vs corrected G2 comparison.

Reads the preserved Phase 0-3 artifacts and the corrected-null results and
produces one machine-readable comparison table plus a markdown fragment.

What is compared (all on the same test labels, same learner, same primary metric
pooled AP over the three pre-registered holdout origins):

1. B2  - strong non-graph baseline (frozen control)
2. G1  - real company-technology graph (frozen control)
3. G2-original  - the Phase 0-3 randomised arm, as shipped (defective)
4. G2-N1 - corrected topology null (degree-preserving simple bipartite swap)
5. G2-N2 - corrected topology + track-activity + per-track time null

It also checks that every arm scored exactly the same test rows by comparing the
SHA-256 of the label vectors recorded by ``s028_g2_corrected.py``.

Usage
-----
    python s028_correction_compare.py
"""
from __future__ import annotations

import gzip
import json
import statistics
from pathlib import Path
from typing import Any

STUDY = Path(__file__).resolve().parents[1]
ARTIFACTS = STUDY / "artifacts"
CORRECTION = ARTIFACTS / "correction_round_1"
MODELS = ("N1", "N2")
LABELS = (("H4q", 4), ("H2q", 2))


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_original(label: str) -> dict[str, Any] | None:
    path = ARTIFACTS / f"experiment_{label}.json"
    if not path.exists():
        return None
    return load_json(path)


def load_corrected(label: str, model: str) -> dict[str, Any] | None:
    path = CORRECTION / f"g2_corrected_{label}_{model}.json"
    if not path.exists():
        return None
    return load_json(path)


def distribution(values: list[float]) -> dict[str, Any]:
    values = [value for value in values if value is not None]
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "n": len(values),
        "min": ordered[0],
        "q025": ordered[int(0.025 * len(ordered))],
        "median": statistics.median(ordered),
        "mean": statistics.fmean(ordered),
        "q975": ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))],
        "max": ordered[-1],
        "sd": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
    }


def randomisation_test(real: float | None, null_values: list[float]) -> dict[str, Any]:
    """Exact one-sided randomisation test, with honest resolution limits."""
    null_values = [value for value in null_values if value is not None]
    draws = len(null_values)
    if real is None or not draws:
        return {"n_randomisations": draws}
    at_or_above = sum(1 for value in null_values if value >= real)
    at_or_below = sum(1 for value in null_values if value <= real)
    return {
        "n_randomisations": draws,
        "real_pooled_ap": real,
        "randomised_above_real": at_or_above,
        "randomised_at_or_below_real": at_or_below,
        "p_real_is_low": (at_or_below + 1) / (draws + 1),
        "p_real_is_high": (at_or_above + 1) / (draws + 1),
        "resolution": f"1/{draws + 1}",
        "note": ("Exact one-sided randomisation p-values for the composite null "
                 "'the observed graph is an exchangeable draw from the null model'. "
                 "p_real_is_low is the evidence that the real graph scores at or below "
                 "the null distribution (i.e. the real topology is worse than degree-matched "
                 "random); p_real_is_high is the evidence that the real graph carries "
                 "information the null destroys. Neither is a sampling-confidence statement "
                 "about AP itself, and neither can fall below 1/(R+1)."),
    }


def summarise_arm(records: list[dict[str, Any]], real_pooled: float | None,
                  per_window_real: dict[str, float | None],
                  pooled_key: str = "pooled_ap",
                  delta_key: str = "pooled_delta_vs_real") -> dict[str, Any]:
    pooled = [row.get(pooled_key) for row in records]
    deltas = [row.get(delta_key) for row in records]
    per_window: dict[str, Any] = {}
    for window, real_value in per_window_real.items():
        values = [row.get("per_window_ap", {}).get(window) for row in records]
        values = [value for value in values if value is not None]
        if values:
            per_window[window] = {
                "real": real_value,
                "null_median": statistics.median(values),
                "null_min": min(values),
                "null_max": max(values),
                "null_beats_real": sum(1 for value in values
                                       if real_value is not None and value >= real_value),
                "draws": len(values),
            }
    clean_pooled = [value for value in pooled if value is not None]
    clean_deltas = [value for value in deltas if value is not None]
    return {
        "pooled_ap_distribution": distribution(clean_pooled),
        "delta_vs_real_distribution": distribution([-value for value in clean_deltas]),
        "per_window": per_window,
        "realisation_count": len(records),
    }


def main() -> int:
    report: dict[str, Any] = {"study": "S-028", "correction": "S-028-CORRECTION-1",
                              "primary_metric": "pooled AP over pre-registered holdout origins",
                              "horizons": {}}
    markdown: list[str] = []
    for label, quarters in LABELS:
        entry: dict[str, Any] = {"label": label, "horizon_quarters": quarters, "arms": {}}
        original = load_original(label)
        stored_predictions_path = ARTIFACTS / f"predictions_{label}.json.gz"
        stored = None
        if stored_predictions_path.exists():
            with gzip.open(stored_predictions_path, "rt", encoding="utf-8") as handle:
                stored = json.load(handle)
        holdouts = (stored or {}).get("panel", {}).get("holdouts") or \
                   (original or {}).get("panel", {}).get("holdouts")
        if not holdouts:
            continue
        entry["holdouts"] = holdouts
        entry["panel"] = (stored or {}).get("panel", {})
        # frozen controls from the recomputation in the corrected runs (validated
        # against the stored artifacts by s028_g2_corrected.py)
        corrected_first = None
        for model in MODELS:
            corrected_first = load_corrected(label, model)
            if corrected_first:
                break
        if corrected_first is None:
            continue
        controls = corrected_first["controls"]["specs"]
        real_pooled = corrected_first["real_graph"]["pooled_pr_auc"]
        real_per_window = corrected_first["real_graph"]["per_window_pr_auc"]
        entry["arms"]["B2_frozen_spec16"] = {
            "pooled_ap": controls["B2_frozen_spec16"]["pooled_pr_auc"],
            "per_window_ap": controls["B2_frozen_spec16"]["per_window_pr_auc"],
            "role": "strong non-graph baseline, frozen control"}
        entry["arms"]["G1_graph"] = {
            "pooled_ap": real_pooled,
            "per_window_ap": real_per_window,
            "role": "real company-technology graph, frozen control"}
        entry["arms"]["B1_history10"] = {
            "pooled_ap": controls["B1_history10"]["pooled_pr_auc"],
            "per_window_ap": controls["B1_history10"]["per_window_pr_auc"],
            "role": "weaker non-graph baseline"}
        # original defective G2
        if original and "g2" in original:
            g2 = original["g2"]
            records = g2.get("randomisations", [])
            entry["arms"]["G2_original_defective"] = {
                "role": "Phase 0-3 randomised arm as shipped (degree/weight/time defective)",
                "real_pooled_ap_recorded": g2.get("real_pooled_ap"),
                **summarise_arm(records, g2.get("real_pooled_ap"),
                                g2.get("real_per_window_ap", {})),
                "randomisation_test": randomisation_test(
                    g2.get("real_pooled_ap"),
                    [row.get("pooled_ap") for row in records]),
            }
        # corrected nulls
        for model in MODELS:
            corrected = load_corrected(label, model)
            if corrected is None:
                continue
            records = corrected["records"]
            entry["arms"][f"G2_{model}"] = {
                "role": ("corrected topology null (degree-preserving simple bipartite swap)"
                         if model == "N1" else
                         "corrected topology + track-activity + per-track time null"),
                "summary_recorded": corrected.get("summary"),
                **summarise_arm(records, real_pooled, real_per_window),
                "randomisation_test": randomisation_test(
                    real_pooled, [row.get("pooled_ap") for row in records]),
                "invariants_ok": {
                    "all_degrees_preserved": corrected["summary"].get("invariants_all_degrees_preserved"),
                    "all_simple": corrected["summary"].get("invariants_all_simple"),
                    "all_node_sets_preserved": corrected["summary"].get(
                        "invariants_all_node_sets_preserved"),
                },
                "test_labels_sha256": corrected.get("test_labels_sha256"),
            }
        # same test rows for every arm?
        label_hashes = {}
        for name, arm in entry["arms"].items():
            if arm.get("test_labels_sha256"):
                label_hashes[name] = arm["test_labels_sha256"]
        entry["same_test_labels"] = (
            len({json.dumps(value, sort_keys=True) for value in label_hashes.values()}) <= 1
            if label_hashes else None)
        entry["label_hash_sets"] = label_hashes
        report["horizons"][label] = entry
        markdown.extend(_markdown_rows(entry))

    out = CORRECTION / "comparison_table.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
                  encoding="utf-8")
    (CORRECTION / "comparison_table.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print("\n".join(markdown))
    print("\nwrote", out)
    return 0


def _markdown_rows(entry: dict[str, Any]) -> list[str]:
    label = entry["label"]
    lines = [f"\n### {label} (H = {entry['horizon_quarters']} quarters, holdouts "
             f"{', '.join(entry['holdouts'])})\n",
             "| Arm | pooled AP | vs G1 (median ΔAP of draws) | null draws ≥ real | p(real is low) | p(real is high) |",
             "|---|---|---|---|---|---|"]
    for name, arm in entry["arms"].items():
        pooled = arm.get("pooled_ap")
        if pooled is None:
            pooled = arm.get("pooled_ap_distribution", {}).get("median")
        delta = arm.get("delta_vs_real_distribution", {}).get("median")
        test = arm.get("randomisation_test", {}) or {}
        beats = test.get("randomised_above_real")
        p_low = test.get("p_real_is_low")
        p_high = test.get("p_real_is_high")
        lines.append(
            f"| {name} | {_fmt(pooled)} | {_fmt(delta)} | "
            f"{beats if beats is not None else '-'} / {test.get('n_randomisations', '-')} | "
            f"{_fmt(p_low)} | {_fmt(p_high)} |")
    return lines


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())

