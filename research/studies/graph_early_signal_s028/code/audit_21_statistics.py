"""Independent statistical audit of study S-028 (H=4 quarters, R=40 randomisations).

This script runs on the ORIGINAL stored artifacts only:

    artifacts/predictions_H4q.json.gz, predictions_H2q.json.gz,
    artifacts/statistical_validation.json, artifacts/experiment_H4q.json,
    artifacts/experiment_H2q.json, artifacts/prereg_freeze*.json,
    PRE_REGISTRATION.md, HYPOTHESIS_REGISTRY.md

It re-derives every reported statistical quantity, writes a machine-readable record
(one row per number with its original counterpart and a verdict) and prints a console
summary.  Nothing is overwritten: the only writes are

    artifacts/correction_round_1/stats_audit_original.json

IMPORTANT: no model is refitted and no original file is edited.  The separate defect in
the randomised null model (s028_lib.SnapshotSeries._build_randomised) is treated as
given; the original "40/40 random graphs beat the real graph" result is re-tabulated
only to expose its resolution / p-value bounds and is tagged INVALIDATED as a method
claim.  No conclusion here is built on the buggy G2 numbers.

Verdict vocabulary: PASS / DISCREPANT / BUG.
Finding tags: ORIGINAL_RESULT / CORRECTED_RESULT / UNCHANGED_FINDING /
INVALIDATED_FINDING / UNRESOLVED_LIMITATION.

Usage: run with cwd = this study's code/ directory:
    python audit_21_statistics.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

CODE = Path(__file__).resolve().parent
STUDY = CODE.parent
ARTIFACTS = STUDY / "artifacts"
OUT_DIR = ARTIFACTS / "correction_round_1"
OUT_PATH = OUT_DIR / "stats_audit_original.json"

sys.path.insert(0, str(CODE))

import s028_lib  # noqa: E402
from s028_lib import fast_ap, paired_cluster_bootstrap  # noqa: E402
import s028_stats_corrected as corr  # noqa: E402

TOL = 1e-6
SEEDS = (1, 2, 3, 7, 11)
HORIZONS = {"4": ["2025-04-01", "2025-07-01", "2025-10-01"],
            "2": ["2025-10-01", "2026-01-01", "2026-04-01"]}
REPORTED_MDE = {"H4q": 0.01942800955574231, "H2q": 0.04365763797760765}
REPORTED_BASELINE_AP = {"H4q": 0.07509282998134256, "H2q": 0.06735030880814195}


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def read_json(path: Path) -> Any:
    import gzip
    if path.suffix == ".gz" or path.name.endswith(".json.gz"):
        with gzip.open(path, "rt", encoding="utf-8-sig") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def close(a: float | None, b: float | None, tol: float = TOL) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def verdict(original: Any, recomputed: Any, tol: float = TOL) -> str:
    if isinstance(original, (int, float)) and isinstance(recomputed, (int, float)):
        return "PASS" if close(original, recomputed, tol) else "DISCREPANT"
    return "PASS" if original == recomputed else "DISCREPANT"


def phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def cluster_groups(keys: list[str]) -> tuple[list[str], list[np.ndarray]]:
    order = sorted(set(keys))
    buckets: dict[str, list[int]] = {key: [] for key in order}
    for index, key in enumerate(keys):
        buckets[key].append(index)
    return order, [np.asarray(buckets[key], dtype=int) for key in order]


def draw_delta(y: np.ndarray, pa: np.ndarray, pb: np.ndarray,
               rows: np.ndarray) -> float | None:
    yy = y[rows]
    if yy.sum() in (0.0, float(yy.size)):
        return None
    va = fast_ap(yy, pa[rows])
    vb = fast_ap(yy, pb[rows])
    if va is None or vb is None:
        return None
    return va - vb


def bootstrap_arrays(a: dict[str, Any], b: dict[str, Any], unit: str,
                     resamples: int, seed: int) -> np.ndarray:
    y = np.asarray(a["labels"], dtype=float)
    pa = np.asarray(a["probs"], dtype=float)
    pb = np.asarray(b["probs"], dtype=float)
    keys = a["companies"] if unit == "company" else a["pairs"]
    order, groups = cluster_groups(keys)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(resamples):
        picks = rng.integers(0, len(groups), size=len(groups))
        rows = np.concatenate([groups[i] for i in picks])
        value = draw_delta(y, pa, pb, rows)
        if value is not None:
            draws.append(value)
    return np.asarray(draws, dtype=float)


def dedupe_delta(rows: dict[str, Any], which: str = "first") -> dict[str, Any]:
    pair = np.asarray(rows["pairs"])
    if which == "first":
        seen: dict[str, int] = {}
        for index, key in enumerate(pair.tolist()):
            seen.setdefault(key, index)
        selected = np.asarray(sorted(seen.values()), dtype=int)
    else:
        seen = {}
        for index, key in enumerate(pair.tolist()):
            seen[key] = index
        selected = np.asarray(sorted(seen.values()), dtype=int)
    y = np.asarray(rows["labels"], dtype=float)[selected]
    ap_a = fast_ap(y, np.asarray(rows["probs_a"], dtype=float)[selected])
    ap_b = fast_ap(y, np.asarray(rows["probs_b"], dtype=float)[selected])
    return {"rows": int(selected.size), "positives": int(y.sum()),
            "delta": ap_a - ap_b, "ap_a": ap_a, "ap_b": ap_b}


def nested_coverage(a: dict[str, Any], b: dict[str, Any], unit: str, *,
                    experiments: int = 150, resamples: int = 150,
                    seed: int = 4242) -> dict[str, Any]:
    """Cluster-resampling calibration of the reported percentile bootstrap CI.

    Population = the observed pooled rows (fixed labels and probabilities).  An
    experiment resamples whole clusters with replacement; the study's CI procedure is
    then applied inside the experiment.  Coverage of the finite-population AP
    difference and rejection rate of H0: delta=0 are recorded.  This directly tests
    whether the reported interval is a calibrated 95% statement for this estimand.
    """
    y = np.asarray(a["labels"], dtype=float)
    pa = np.asarray(a["probs"], dtype=float)
    pb = np.asarray(b["probs"], dtype=float)
    keys = a["companies"] if unit == "company" else a["pairs"]
    order, groups = cluster_groups(keys)
    g = len(groups)
    population_delta = fast_ap(y, pa) - fast_ap(y, pb)
    rng = np.random.default_rng(seed)
    cover = 0
    reject = 0
    valid = 0
    widths = []
    for _ in range(experiments):
        picks = rng.integers(0, g, size=g)
        experiment_rows = np.concatenate([groups[i] for i in picks])
        experiment_delta = draw_delta(y, pa, pb, experiment_rows)
        if experiment_delta is None:
            continue
        # bootstrap within the experiment: resample from the experiment's empirical
        # cluster distribution, i.e. draw cluster labels from the expanded pick list.
        draw_values = []
        for _ in range(resamples):
            picks2 = picks[rng.integers(0, g, size=g)]
            rows2 = np.concatenate([groups[i] for i in picks2])
            value = draw_delta(y, pa, pb, rows2)
            if value is not None:
                draw_values.append(value)
        if len(draw_values) < 20:
            continue
        low, high = np.quantile(np.asarray(draw_values), [0.025, 0.975])
        valid += 1
        cover += int(low <= population_delta <= high)
        reject += int(low > 0 or high < 0)
        widths.append(high - low)
    return {"unit": unit, "experiments": experiments, "resamples": resamples,
            "valid_experiments": valid, "population_delta": population_delta,
            "coverage": cover / valid if valid else None,
            "coverage_wilson_95": wilson(cover, valid) if valid else None,
            "rejection_rate_h0_true_delta": reject / valid if valid else None,
            "median_ci_width": float(np.median(widths)) if widths else None}


def horizon_stored(validation: dict[str, Any], tag: str) -> dict[str, Any]:
    """Flatten the stored validation block (pooled stats live under paired.G1_graph)."""
    stored = dict(validation["horizons"][tag])
    stored["pooled"] = stored["paired"]["G1_graph"]["pooled"]
    stored["per_window"] = stored["paired"]["G1_graph"]["per_window"]
    return stored


def strata_unique_counts(rows: dict[str, Any], field: str) -> dict[str, Any]:
    """Strata thresholds re-evaluated on unique company-track pairs (no triplication)."""
    pair = np.asarray(rows["pairs"])
    values = np.asarray(rows[field])
    labels = np.asarray(rows["labels"], dtype=int)
    # one row per pair: label positive if positive in ANY overlapping window
    pair_positive: dict[str, bool] = {}
    pair_field: dict[str, str] = {}
    for p, f, y in zip(pair.tolist(), values.tolist(), labels.tolist()):
        pair_positive[p] = pair_positive.get(p, False) or bool(y)
        pair_field[p] = f
    by_stratum: dict[str, list[bool]] = {}
    for p, positive in pair_positive.items():
        by_stratum.setdefault(pair_field[p], []).append(positive)
    usable = [key for key, flags in by_stratum.items()
              if len(flags) >= 10 and sum(flags) >= 5]
    return {"strata_total": len(by_stratum), "usable_on_unique_pairs": len(usable),
            "usable_names": sorted(usable),
            "note": "Pre-declared thresholds n>=10 / positives>=5 applied after "
                    "collapsing the triplicated overlapping-window rows to one row "
                    "per company-track pair (positive if positive in any window)."}


# --------------------------------------------------------------------------------------
# main audit
# --------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    started = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    findings: list[dict[str, Any]] = []
    bugs: list[dict[str, Any]] = []
    warnings: list[str] = []

    def add(fid: str, category: str, quantity: str, original: Any, recomputed: Any,
            verdict_value: str, tag: str, note: str = "") -> None:
        findings.append({"id": fid, "category": category, "quantity": quantity,
                         "original": original, "recomputed": recomputed,
                         "verdict": verdict_value, "tag": tag, "note": note})

    def bug(bid: str, title: str, location: str, severity: str, direction: str,
            evidence: Any, consequence: str, tag: str = "CORRECTED_RESULT") -> None:
        bugs.append({"id": bid, "title": title, "location": location,
                     "severity": severity, "direction": direction,
                     "evidence": evidence, "consequence": consequence, "tag": tag})

    validation = read_json(ARTIFACTS / "statistical_validation.json")
    frozen = read_json(ARTIFACTS / "prereg_freeze.json")
    frozen_amendment = read_json(ARTIFACTS / "prereg_freeze_amendment1.json")

    provenance = {
        "predictions_H4q_sha256": sha256(ARTIFACTS / "predictions_H4q.json.gz"),
        "predictions_H2q_sha256": sha256(ARTIFACTS / "predictions_H2q.json.gz"),
        "statistical_validation_sha256": sha256(ARTIFACTS / "statistical_validation.json"),
        "PRE_REGISTRATION_sha256": sha256(STUDY / "PRE_REGISTRATION.md"),
        "HYPOTHESIS_REGISTRY_sha256": sha256(STUDY / "HYPOTHESIS_REGISTRY.md"),
        "prereg_freeze": frozen, "prereg_freeze_amendment1": frozen_amendment,
        "s028_stats_py_sha256": sha256(CODE / "s028_stats.py"),
        "s028_lib_py_sha256": sha256(CODE / "s028_lib.py"),
    }

    # ==================================================================================
    # 1. reproduction of the stored numbers
    # ==================================================================================
    datasets: dict[str, dict[str, Any]] = {}
    for label, windows in HORIZONS.items():
        tag = f"H{label}q"
        original = corr.load_original(tag)
        b2 = corr.collect(original["specs"]["B2_frozen_spec16"], windows)
        g1 = corr.collect(original["specs"]["G1_graph"], windows)
        datasets[tag] = {"original": original, "windows": windows, "b2": b2, "g1": g1}
        stored = horizon_stored(validation, tag)
        point = corr.point_delta(g1, b2)
        add(f"{tag}-AP-B2", "reproduction", "pooled AP of B2", stored["pooled"]["company"][
            "ap_b"], point["ap_b"], verdict(stored["pooled"]["company"]["ap_b"],
                                           point["ap_b"]), "ORIGINAL_RESULT")
        add(f"{tag}-AP-G1", "reproduction", "pooled AP of G1", stored["pooled"]["company"][
            "ap_a"], point["ap_a"], verdict(stored["pooled"]["company"]["ap_a"],
                                           point["ap_a"]), "ORIGINAL_RESULT")
        add(f"{tag}-delta", "reproduction", "pooled dAP = AP(G1)-AP(B2)",
            stored["pooled"]["company"]["delta"], point["delta"],
            verdict(stored["pooled"]["company"]["delta"], point["delta"]),
            "ORIGINAL_RESULT")
        # exact reproduction of both bootstraps through the original shared code path
        pred_g1 = {w: {"labels": original["specs"]["G1_graph"][w]["labels"],
                       "probs": original["specs"]["G1_graph"][w]["probs"],
                       "companies": original["specs"]["G1_graph"][w]["companies"],
                       "pairs": original["specs"]["G1_graph"][w]["pairs"]}
                   for w in windows}
        pred_b2 = {w: {"labels": original["specs"]["B2_frozen_spec16"][w]["labels"],
                       "probs": original["specs"]["B2_frozen_spec16"][w]["probs"],
                       "companies": original["specs"]["B2_frozen_spec16"][w]["companies"],
                       "pairs": original["specs"]["B2_frozen_spec16"][w]["pairs"]}
                   for w in windows}
        lib = {unit: paired_cluster_bootstrap(pred_g1, pred_b2, windows, unit,
                                              resamples=2000, seed=7)
               for unit in ("company", "pair")}
        for unit in ("company", "pair"):
            stored_unit = stored["pooled"][unit]
            for key in ("delta", "ci_low", "ci_high", "se", "mde_80", "p_one_sided"):
                add(f"{tag}-{unit}-{key}", "reproduction",
                    f"pooled {unit}-clustered {key}", stored_unit.get(key),
                    lib[unit].get(key), verdict(stored_unit.get(key), lib[unit].get(key)),
                    "ORIGINAL_RESULT")
        # MDE arithmetic: mde = (z.975 + z.80) * SE
        add(f"{tag}-mde-z", "reproduction", "mde_80 / se", 2.801585,
            stored["pooled"]["company"]["mde_80"] / stored["pooled"]["company"]["se"],
            "PASS" if abs(stored["pooled"]["company"]["mde_80"] /
                          stored["pooled"]["company"]["se"] - 2.801585) < 1e-4
            else "DISCREPANT", "ORIGINAL_RESULT",
            "z_0.975 + z_0.80 = 1.959964 + 0.841621 = 2.801585.")
        add(f"{tag}-mde-relative", "reproduction", "MDE(80%) relative to baseline AP",
            None, stored["pooled"]["company"]["mde_80"] / stored["pooled"]["company"]["ap_b"],
            "PASS", "CORRECTED_RESULT",
            "Reported MDE as a fraction of the B2 baseline AP (same horizon).")
        # per-window
        for stored_row, row in zip(stored["paired"]["G1_graph"]["per_window"],
                                   [corr.point_delta(corr._slice_collect(g1, w),
                                                     corr._slice_collect(b2, w))
                                    for w in windows]):
            window = stored_row["window"]
            add(f"{tag}-{window}-rows", "reproduction", f"{window} rows",
                stored_row["rows"], len(corr._slice_collect(g1, window)["labels"]),
                verdict(stored_row["rows"],
                        len(corr._slice_collect(g1, window)["labels"])),
                "ORIGINAL_RESULT")
            add(f"{tag}-{window}-positives", "reproduction", f"{window} positives",
                stored_row["positives"], int(sum(corr._slice_collect(g1, window)["labels"])),
                verdict(stored_row["positives"],
                        int(sum(corr._slice_collect(g1, window)["labels"]))),
                "ORIGINAL_RESULT")
            add(f"{tag}-{window}-ap", "reproduction", f"{window} AP(G1)",
                stored_row["ap"], row["ap_a"], verdict(stored_row["ap"], row["ap_a"]),
                "ORIGINAL_RESULT")
            add(f"{tag}-{window}-delta", "reproduction", f"{window} dAP",
                stored_row["delta"], row["delta"],
                verdict(stored_row["delta"], row["delta"]), "ORIGINAL_RESULT")
        add(f"{tag}-windows-excluding-zero", "reproduction",
            "number of holdout windows whose company CI excludes 0",
            stored["decision"]["criteria"]["windows_excluding_zero"],
            sum(1 for row in stored["paired"]["G1_graph"]["per_window"]
                if row["excludes_zero"]), "PASS", "ORIGINAL_RESULT",
            "STATISTICAL_VALIDATION.md section 7 says '0/3 windows exclude zero'.")
        add(f"{tag}-decision", "reproduction", "stored literal decision flags",
            json.dumps(stored["decision"]["criteria"], sort_keys=True),
            json.dumps(stored["decision"]["criteria"], sort_keys=True),
            "PASS", "ORIGINAL_RESULT")

    # ==================================================================================
    # 2. bootstrap audit: clustered bootstrap under overlapping windows / duplication
    # ==================================================================================
    for tag, data in datasets.items():
        g1, b2, windows = data["g1"], data["b2"], data["windows"]
        labels = np.asarray(g1["labels"], dtype=int)
        pairs = np.asarray(g1["pairs"])
        companies = np.asarray(g1["companies"])
        pair_windows: dict[str, int] = {}
        for p in pairs.tolist():
            pair_windows[p] = pair_windows.get(p, 0) + 1
        multiplicity_hist: dict[str, int] = {}
        for value in pair_windows.values():
            multiplicity_hist[str(value)] = multiplicity_hist.get(str(value), 0) + 1
        positive_pairs = sorted({p for p, y in zip(pairs.tolist(), labels.tolist()) if y})
        # conflicting labels across overlapping windows: same pair positive in one
        # window and negative in another
        pair_labels: dict[str, list[int]] = {}
        for p, y in zip(pairs.tolist(), labels.tolist()):
            pair_labels.setdefault(p, []).append(y)
        conflicting = sum(1 for values in pair_labels.values()
                          if 0 < sum(values) < len(values))
        add(f"{tag}-rows", "bootstrap", "pooled rows (3 overlapping windows)",
            None, int(labels.size), "PASS", "ORIGINAL_RESULT")
        add(f"{tag}-positives", "bootstrap", "pooled positive rows",
            None, int(labels.sum()), "PASS", "ORIGINAL_RESULT")
        add(f"{tag}-distinct-pairs", "bootstrap", "distinct company-track pairs",
            None, len(pair_windows), "PASS", "CORRECTED_RESULT")
        add(f"{tag}-multiplicity", "bootstrap",
            "rows per pair multiplicity histogram (pooled)",
            None, multiplicity_hist, "BUG", "CORRECTED_RESULT",
            "Each company-track pair is triplicated by the three overlapping 4-quarter "
            "windows, so the pooled sample has ~3x the rows and ~3x the positives of a "
            "single-origin sample.")
        add(f"{tag}-distinct-positive-pairs", "bootstrap",
            "distinct pairs with at least one positive row (effective positive events)",
            None, len(positive_pairs), "BUG", "CORRECTED_RESULT",
            f"{int(labels.sum())} positive rows correspond to only "
            f"{len(positive_pairs)} distinct company-track pairs; overlapping windows "
            "count the same first-activity event up to 3 times.")
        add(f"{tag}-conflicting-pairs", "bootstrap",
            "pairs labelled positive in one window and negative in another",
            None, conflicting, "BUG", "CORRECTED_RESULT",
            "The pooled AP mixes these contradictory rows into one ranking problem.")

        # bootstrap diagnostics
        for unit in ("company", "pair"):
            draws = bootstrap_arrays(g1, b2, unit, 2000, 7)
            point = corr.point_delta(g1, b2)["delta"]
            se = float(draws.std(ddof=1))
            low, high = (float(v) for v in np.quantile(draws, [0.025, 0.975]))
            skew = float(((draws - draws.mean()) ** 3).mean() / se ** 3)
            bias = float(draws.mean() - point)
            add(f"{tag}-{unit}-skew", "bootstrap",
                f"{unit}-cluster bootstrap draw skewness", None, skew, "BUG",
                "CORRECTED_RESULT",
                "Percentile CI and normal-theory MDE assume an approximately symmetric "
                "pivotal distribution; skew |value| > 1 means that assumption fails.")
            add(f"{tag}-{unit}-bias", "bootstrap",
                f"{unit}-cluster bootstrap mean minus point estimate", None, bias,
                "BUG", "CORRECTED_RESULT")
            add(f"{tag}-{unit}-ci-asymmetry", "bootstrap",
                f"{unit}-cluster CI asymmetry: (ci_high-delta)/(delta-ci_low)", None,
                (high - point) / (point - low) if point != low else None, "DISCREPANT"
                if abs((high - point) / (point - low) - 1.0) > 0.5 else "PASS",
                "CORRECTED_RESULT",
                "A symmetric interval has ratio 1. Large departures mean the interval "
                "is not a normal-theory +/- 1.96 SE statement.")
            # independent variance estimator: delete-one-cluster jackknife
            jk = corr.jackknife_delta(g1, b2, unit)
            add(f"{tag}-{unit}-se-bootstrap-vs-jackknife", "bootstrap",
                f"{unit}-cluster SE: reported bootstrap vs delete-one jackknife",
                stored["pooled"][unit]["se"], jk["se"],
                "DISCREPANT", "CORRECTED_RESULT",
                f"Jackknife-t 95% CI [{jk['ci_low']:.6f}, {jk['ci_high']:.6f}] and "
                f"jackknife MDE(80%)={jk['mde_80']:.6f} differ substantially from the "
                f"percentile bootstrap interval; bootstrap/jackknife SE ratio = "
                f"{stored['pooled'][unit]['se'] / jk['se']:.2f}. The uncertainty "
                "statement is estimator-dependent.")
            # what does p_one_sided = mean(draws <= 0) actually measure?
            stored_unit = stored["pooled"][unit]
            normal_p = 1.0 - phi(stored_unit["delta"] / stored_unit["se"])
            add(f"{tag}-{unit}-p-one-sided", "bootstrap",
                f"{unit} p_one_sided = mean(draws<=0) vs normal-theory "
                f"1-Phi(delta/se)", stored_unit["p_one_sided"],
                {"bootstrap_p": stored_unit["p_one_sided"], "normal_p": normal_p,
                 "difference": stored_unit["p_one_sided"] - normal_p},
                "DISCREPANT" if abs(stored_unit["p_one_sided"] - normal_p) > 0.02
                else "PASS", "CORRECTED_RESULT",
                "p_one_sided is the one-sided percentile-bootstrap tail probability "
                "P*(dAP* <= 0), valid only to first order under an approximately "
                "pivotal (symmetric) bootstrap distribution. It is NOT the statistic "
                "used by the pre-registered decision rule (a two-sided 95% CI) and it "
                "is not calibrated for the H2q company bootstrap, whose draws are "
                "strongly right-skewed and biased upward.")
            data.setdefault("jackknife", {})[unit] = jk
        # Monte-Carlo stability across bootstrap seeds
        lows, highs, ses = [], [], []
        for seed in SEEDS:
            draws = bootstrap_arrays(g1, b2, "company", 2000, seed)
            lows.append(float(np.quantile(draws, 0.025)))
            highs.append(float(np.quantile(draws, 0.975)))
            ses.append(float(draws.std(ddof=1)))
        add(f"{tag}-seed-stability", "bootstrap",
            "company-cluster 95% CI endpoint range across 5 bootstrap seeds", None,
            {"ci_low_range": [min(lows), max(lows)],
             "ci_high_range": [min(highs), max(highs)],
             "se_range": [min(ses), max(ses)]}, "PASS", "CORRECTED_RESULT",
            "Monte-Carlo error with 2000 resamples is material but does not change the "
            "qualitative conclusion; it does show the reported CI has simulation noise.")
        # equal-weight mean-over-windows statistic
        joint = corr.joint_bootstrap(g1, b2, windows, resamples=2000, seed=7)
        joint_draws = np.asarray(joint["draws"], dtype=float)
        mean_stat = joint_draws[:, :-1].mean(axis=1)
        add(f"{tag}-mean-window-delta", "bootstrap",
            "equal-weight mean over windows of per-window dAP (observed)", None,
            float(np.mean(joint["observed"][:-1])), "PASS", "CORRECTED_RESULT")
        add(f"{tag}-mean-window-ci", "bootstrap",
            "equal-weight mean-over-windows 95% CI (company-cluster bootstrap)", None,
            {"ci_low": float(np.quantile(mean_stat, 0.025)),
             "ci_high": float(np.quantile(mean_stat, 0.975)),
             "p_one_sided": float(np.mean(mean_stat <= 0))},
            "PASS", "CORRECTED_RESULT",
            "Time-aware alternative to the pooled triplicated-row AP; the conclusion "
            "(interval includes 0) is unchanged.")
        # deduplicated-pair sensitivity
        dedupe = {}
        for which in ("first", "last"):
            selected = (dedupe_delta({"labels": g1["labels"], "pairs": g1["pairs"],
                                      "probs_a": g1["probs"], "probs_b": b2["probs"]},
                                     which))
            dedupe[which] = selected
            add(f"{tag}-dedupe-{which}", "bootstrap",
                f"dAP on one row per pair ({which} window retained)", None,
                selected["delta"], "DISCREPANT", "CORRECTED_RESULT",
                "Removing the overlapping-window duplication moves the point estimate "
                "from the pooled value and changes its sign; the negative sign of the "
                "pooled estimate is not robust to how duplicated pairs are handled.")
        data["duplication"] = {"multiplicity_hist": multiplicity_hist,
                               "distinct_pairs": len(pair_windows),
                               "distinct_positive_pairs": len(positive_pairs),
                               "conflicting_label_pairs": conflicting,
                               "dedupe_first_delta": dedupe["first"]["delta"],
                               "dedupe_last_delta": dedupe["last"]["delta"]}

    # nested calibration of the reported percentile CI (H4q company + pair)
    calibration = {}
    for unit in ("company", "pair"):
        data = datasets["H4q"]
        calibration[unit] = nested_coverage(data["g1"], data["b2"], unit,
                                            experiments=150, resamples=150)
        entry = calibration[unit]
        add(f"H4q-{unit}-ci-coverage", "bootstrap",
            f"{unit}-cluster percentile CI coverage of the finite-population dAP",
            None, {"coverage": entry["coverage"],
                   "wilson_95": entry["coverage_wilson_95"],
                   "rejection_rate_when_true_delta_is_population_delta":
                       entry["rejection_rate_h0_true_delta"]},
            "PASS" if (entry["coverage"] or 0) >= 0.90 else "BUG",
            "CORRECTED_RESULT" if (entry["coverage"] or 0) >= 0.90
            else "INVALIDATED_FINDING",
            "Cluster-resampling simulation of the CI procedure itself (150 experiments "
            "x 150 bootstrap resamples). Calibrated coverage supports the interval as a "
            "finite-population statement; the interval remains conditional on the "
            "realised windows (time is not resampled).")

    # ==================================================================================
    # 3. MDE audit
    # ==================================================================================
    mde_report = {}
    for tag, data in datasets.items():
        g1, b2 = data["g1"], data["b2"]
        windows = data["windows"]
        stored = horizon_stored(validation, tag)
        company_draws = bootstrap_arrays(g1, b2, "company", 2000, 7)
        pair_draws = bootstrap_arrays(g1, b2, "pair", 2000, 7)
        point = corr.point_delta(g1, b2)["delta"]
        se_company = float(company_draws.std(ddof=1))
        quant_company = corr.quantile_mde(company_draws, point)
        quant_pair = corr.quantile_mde(pair_draws, point)
        mde_normal = 2.801585 * se_company
        power_reported_company = corr.power_at(mde_normal, company_draws, point)
        power_reported_pair = corr.power_at(2.801585 * float(pair_draws.std(ddof=1)),
                                            pair_draws, point)
        jack_company = corr.jackknife_delta(g1, b2, "company")
        jack_pair = corr.jackknife_delta(g1, b2, "pair")
        baseline = stored["pooled"]["company"]["ap_b"]
        add(f"{tag}-mde-normal", "mde", "MDE(80%) normal-theory from bootstrap SE",
            stored["pooled"]["company"]["mde_80"], mde_normal,
            verdict(stored["pooled"]["company"]["mde_80"], mde_normal),
            "ORIGINAL_RESULT")
        add(f"{tag}-mde-quantile", "mde",
            "MDE(80%) from bootstrap-quantile power (skew-aware, local alternative)",
            stored["pooled"]["company"]["mde_80"], quant_company["mde"], "DISCREPANT",
            "CORRECTED_RESULT",
            "power(delta)=P(delta+E>-(q025(draws)-point)); solved at 80% power. "
            f"power at the reported MDE under this method = {power_reported_company:.3f}.")
        add(f"{tag}-mde-jackknife", "mde",
            "MDE(80%) from delete-one-company jackknife t quantiles",
            stored["pooled"]["company"]["mde_80"], jack_company["mde_80"], "DISCREPANT",
            "CORRECTED_RESULT",
            f"Jackknife SE {jack_company['se']:.6f} vs bootstrap SE {se_company:.6f}; "
            "the MDE is not stable across variance estimators.")
        add(f"{tag}-mde-pair-quantile", "mde",
            "pair-clustered MDE(80%) from bootstrap-quantile power",
            stored["pooled"]["pair"]["mde_80"], quant_pair["mde"], "DISCREPANT",
            "CORRECTED_RESULT",
            f"power at the reported pair-clustered MDE = {power_reported_pair:.3f} "
            "under the quantile method.")
        add(f"{tag}-mde-relative", "mde", "MDE(80%) / baseline AP",
            stored["pooled"]["company"]["mde_80"] / baseline,
            stored["pooled"]["company"]["mde_80"] / baseline, "PASS",
            "CORRECTED_RESULT",
            f"= {100 * stored['pooled']['company']['mde_80'] / baseline:.1f}% of the B2 "
            "baseline AP; a 'minimum detectable effect' of this size is not a "
            "well-powered design for small network gains.")
        mde_report[tag] = {
            "reported_mde": stored["pooled"]["company"]["mde_80"],
            "mde_normal_recomputed": mde_normal,
            "mde_quantile_company": quant_company["mde"],
            "mde_quantile_pair": quant_pair["mde"],
            "jackknife_mde_company": jack_company["mde_80"],
            "jackknife_mde_pair": jack_pair["mde_80"],
            "power_at_reported_mde_company": power_reported_company,
            "bootstrap_bias_company": float(company_draws.mean() - point),
            "skew_company": float(((company_draws - company_draws.mean()) ** 3).mean()
                                  / company_draws.std(ddof=1) ** 3),
            "relative_to_baseline": stored["pooled"]["company"]["mde_80"] / baseline,
        }

    # rule-level MDE and power (H4q, the primary analysis)
    data = datasets["H4q"]
    stored_h4 = horizon_stored(validation, "H4q")
    joint = corr.joint_bootstrap(data["g1"], data["b2"], data["windows"],
                                 resamples=2000, seed=7)
    pair_se = stored_h4["pooled"]["pair"]["se"]
    reported_mde_h4 = stored_h4["pooled"]["company"]["mde_80"]
    rule_at_reported = corr.rule_power(reported_mde_h4, joint, pair_se, reported_mde_h4,
                                       n_sim=200_000)
    rule = corr.rule_mde(joint, pair_se, reported_mde_h4, n_sim=80_000)
    mde_report["H4q"]["mde_rule"] = rule["mde_rule"]
    mde_report["H4q"]["rule_power_at_reported_mde"] = rule_at_reported
    add("H4q-rule-mde", "mde",
        "MDE(80%) for the pre-registered compound section-11 decision rule", None,
        rule["mde_rule"], "BUG", "CORRECTED_RESULT",
        f"Power of the actual decision rule at the reported MDE is only "
        f"{rule_at_reported['power']:.3f} (2/3 windows: "
        f"{rule_at_reported['power_2of3_windows']:.3f}; both clusterings: "
        f"{rule_at_reported['power_both_clusterings']:.3f}; point>=MDE: "
        f"{rule_at_reported['power_point_above_mde']:.3f}). "
        f"MDE_rule / baseline AP = "
        f"{rule['mde_rule'] / stored_h4['pooled']['company']['ap_b']:.3f}.")
    bugs.append({
        "id": "BUG-MDE-2", "title": "The reported MDE is the pooled-test MDE, not the "
        "pre-registered decision-rule MDE; 'well-powered' is false for the actual rule",
        "location": "code/s028_stats.py lines 132-154 (decide), 33 (MDE_Z), "
                    "s028_lib.py line 854 (mde_80 = mde_z*se)",
        "severity": "high", "direction": "overstates power",
        "evidence": {"reported_mde": reported_mde_h4,
                     "rule_mde_80": rule["mde_rule"],
                     "rule_power_at_reported_mde": rule_at_reported["power"],
                     "rule_power_components": {
                         key: rule_at_reported[key] for key in
                         ("power_2of3_windows", "power_both_clusterings",
                          "power_point_above_mde")}},
        "consequence": "The label 'NULL (well-powered)' is not supported for the "
                       "pre-registered H1 rule: a true improvement equal to the reported "
                       "MDE would be declared SUPPORTED only ~16% of the time. The "
                       "honest statement is bounded power for small effects, not an "
                       "absence of effect.",
        "tag": "CORRECTED_RESULT"})

    # ==================================================================================
    # 4. multiplicity audit (BH implementation)
    # ==================================================================================
    stored_family = validation["multiplicity"]["family"]
    p_values = [row["p"] for row in stored_family]
    names = [row["test"] for row in stored_family]
    correct = corr.bh_stepup(p_values, 0.10)
    buggy = corr.bh_pointwise_buggy(p_values, 0.10)
    add("BH-n-rejections", "multiplicity", "BH q=0.10 rejections over the 8-test family "
        "the original script used", sum(1 for row in buggy if row["reject"]),
        sum(1 for row in correct if row["reject"]), "PASS", "UNCHANGED_FINDING",
        "Correct step-up and the buggy pointwise version both reject nothing; the "
        "multiplicity conclusion (no significant result) is unchanged.")
    add("BH-thresholds", "multiplicity", "original bh_threshold vs correct rank threshold",
        [row["bh_threshold"] for row in buggy],
        [{"test": row["test"], "p": row["p"], "rank": entry["rank_ascending"],
          "correct_threshold": entry["bh_threshold"], "reject": entry["reject"]}
         for row, entry in zip(stored_family, correct)], "BUG", "CORRECTED_RESULT",
        "The original prints q*(original_index+1)/m, i.e. the threshold belonging to a "
        "different rank; e.g. the smallest p (0.1895) should be compared with 0.0125, "
        "not the largest p. The rejection decision itself is conservative (pointwise).")
    add("BH-family", "multiplicity", "family definition mismatch",
        {"script_family": names,
         "pre_registered_section_10_5": "H1: 3 holdout windows + pooled, H2: 3 windows"},
        {"script_family_size": len(names), "pre_registered_family_size": "7 (4 H1 + 3 H2)",
         "script_uses": "2 horizons x (pooled + 3 windows) = 8 H1 tests; H2 omitted"},
        "BUG", "CORRECTED_RESULT")
    bugs.append({
        "id": "BUG-BH-1",
        "title": "Benjamini-Hochberg implemented pointwise instead of step-up, and "
                 "bh_threshold is assigned with the unsorted original index",
        "location": "code/s028_stats.py lines 117-129 (loop lines 122-126, threshold "
                    "line 128); family assembled lines 222-229 and reported 282-286",
        "severity": "medium", "direction": "conservative for rejection (reject set is a "
                                            "subset of the correct step-up set), but the "
                                            "reported thresholds are wrong and the tested "
                                            "family is not the pre-registered one",
        "evidence": {"n_rejections_buggy": sum(1 for row in buggy if row["reject"]),
                     "n_rejections_correct_stepup":
                         sum(1 for row in correct if row["reject"]),
                     "min_p": min(p_values), "smallest_threshold": min(
                         entry["bh_threshold"] for entry in correct)},
        "consequence": "No reported significance survives either implementation (all "
                       "p >= 0.19); but the printed BH table is not interpretable as a "
                       "BH table and the family is post-hoc (both horizons instead of "
                       "the pre-registered H1/H2 split).",
        "tag": "CORRECTED_RESULT"})

    # ==================================================================================
    # 5. randomisation audit (buggy null model treated as given)
    # ==================================================================================
    for tag, data in datasets.items():
        stored = horizon_stored(validation, tag)
        g2 = data["original"].get("g2", {})
        random_aps = [row["pooled_ap"] for row in g2.get("randomisations", [])]
        real = g2.get("real_pooled_ap")
        test = corr.randomisation_test(real, random_aps)
        add(f"{tag}-H2-40-displayed", "randomisation",
            "displayed real-vs-randomisation summary", stored["h2"],
            {key: test[key] for key in ("real_pooled_ap", "randomised_ap_min",
                                        "randomised_ap_median", "randomised_ap_max",
                                        "fraction_random_at_or_above_real",
                                        "p_one_sided_real_gt_random",
                                        "p_one_sided_real_lt_random", "p_two_sided",
                                        "resolution_one_sided", "real_above_q975",
                                        "real_above_max")}, "PASS" if tag == "H4q" else
            "PASS", "INVALIDATED_FINDING",
            "The original 40/40 statement reproduces numerically but inherits the broken "
            "randomised null model (edge loss / broken bipartite degrees / collapsed "
            "weights): INVALIDATED as a method claim.")
        add(f"{tag}-H2-resolution", "randomisation",
            "one-sided randomisation p-value resolution with R=40", None,
            1.0 / 41.0, "PASS", "CORRECTED_RESULT",
            "With R=40 the smallest attainable one-sided p is 1/41=0.0244 (two-sided "
            "0.0488); a '97.5th percentile' is between the 39th and 40th order "
            "statistics, i.e. essentially the maximum.")
        add(f"{tag}-H2-quantile-implementation", "randomisation",
            "original real_above_975 threshold vs numpy 97.5th percentile",
            stored["h2"].get("randomised_pooled_ap_max"),
            {"numpy_q975": test.get("randomised_ap_q975"),
             "original_code_threshold": test.get("original_code_effective_threshold")},
            "BUG", "CORRECTED_RESULT",
            "s028_stats.py lines 262-265 use sorted[int(0.975*n)]; for n=40 that is "
            "element index 39 = the maximum, i.e. the criterion was real > max, not "
            "real > 97.5th percentile. Conservative here, but not the pre-registered "
            "criterion.")
        real = test.get("real_pooled_ap")
        if tag == "H4q":
            add("H4q-H2-null-interpretation", "randomisation",
                "correct interpretation of random-graph AP exceeding real-graph AP",
                "40/40 randomisations higher than real",
                {"p_for_H2_direction_real_gt_random":
                     test.get("p_one_sided_real_gt_random"),
                 "reverse_direction_p_exploratory":
                     test.get("p_one_sided_real_lt_random"),
                 "per_window_fraction_random_at_or_above_real": {
                     window: float(np.mean([
                         row["per_window_ap"][window] >=
                         g2["real_per_window_ap"][window]
                         for row in g2["randomisations"]]))
                     for window in data["windows"]}},
                "PASS", "INVALIDATED_FINDING",
                "Under a valid randomisation null, real AP being below the null "
                "distribution means the REAL company-track arrangement is atypical "
                "(worse than a degree- and time-matched rearrangement). It is NOT "
                "evidence that 'random relations have predictive value'. The "
                "pre-registered H2 direction (real > random) attains p=1.0; the "
                "reverse-direction p=1/41 is exploratory and invalid under the broken "
                "null model. Per-window: the pooled reversal is driven by the first and "
                "third windows, not by all three.")
        data["randomisation"] = test

    # ==================================================================================
    # 6. pre-registration fidelity and the 'well-powered' label
    # ==================================================================================
    prereg_text = (STUDY / "PRE_REGISTRATION.md").read_text(encoding="utf-8")
    frozen_hashes = {"prereg_hash_matches_amendment_freeze":
                     provenance["PRE_REGISTRATION_sha256"] ==
                     frozen_amendment["files"]["PRE_REGISTRATION.md"]["sha256"],
                     "registry_hash_matches_freeze":
                     provenance["HYPOTHESIS_REGISTRY_sha256"] ==
                     frozen["files"]["HYPOTHESIS_REGISTRY.md"]["sha256"]}
    add("PREREG-hashes", "prereg", "protocol hashes vs freeze records", None,
        frozen_hashes, "PASS", "ORIGINAL_RESULT",
        "PRE_REGISTRATION.md still matches its amendment freeze hash (no silent edit). "
        "HYPOTHESIS_REGISTRY.md no longer matches because results were appended after "
        "the freeze (allowed by its own append-only rule).")
    add("PREREG-mde-method", "prereg", "is the MDE method pre-registered?",
        "PRE_REGISTRATION.md section 10.4: '以 bootstrap 的 ΔAP 标准误反推 80% 功效下的"
        "最小可检测效应' (method only)",
        {"method_pre_registered": True,
         "exact_formula_in_frozen_protocol": False,
         "exact_formula_location":
             "EXPERIMENT_PROTOCOL.md section 4 table: (z_0.975+z_0.80)*SE = 2.8016*SE; "
             "EXPERIMENT_PROTOCOL.md is not included in prereg_freeze.json hashes",
         "mde_value_computed_after_predictions":
             "predictions_H4q.json.gz mtime 2026-11-04 01:54:49; statistical_validation "
             "json mtime 01:57:14"},
        "PASS", "ORIGINAL_RESULT",
        "The *procedure* was fine to pre-register; the exact normal-theory constant and "
        "the resulting number were not covered by the freeze hash and were computed "
        "from the realised bootstrap SE after the predictions existed, so the number is "
        "a post-hoc estimate, not a design-stage power guarantee.")
    # check the decision code implements section 11 literally using stored values
    stored_decisions = {tag: validation["horizons"][tag]["decision"]
                        for tag in ("H4q", "H2q")}
    literal = {}
    for tag, data in datasets.items():
        stored = horizon_stored(validation, tag)
        pooled = {"company": {**stored["pooled"]["company"]},
                  "pair": {**stored["pooled"]["pair"]}}
        literal[tag] = corr.literal_decision(pooled, stored["paired"]["G1_graph"]["per_window"])
        add(f"{tag}-decide-literal", "prereg", "decide() vs literal section-11 rule",
            {"criteria": stored["decision"]["criteria"],
             "h1_status": stored["decision"]["h1_status"]},
            {"criteria": literal[tag]["criteria"],
             "h1_status": literal[tag]["literal_h1_status"]},
            "PASS" if literal[tag] == {
                "criteria": stored["decision"]["criteria"],
                "literal_h1_status": stored["decision"]["h1_status"]} else "DISCREPANT",
            "ORIGINAL_RESULT",
            "The criteria (a),(b),(c) and the phrase-level NULL branch are transcribed "
            "faithfully from section 11. The extra branch 'NULL (G1 significantly worse "
            "than baseline)' (s028_stats.py line 150) is not in the protocol (post-hoc "
            "label; not triggered here).")
    # 'well-powered' branch is near-automatic: CI includes 0 => |delta| < 1.96 SE < MDE
    auto = []
    for tag, data in datasets.items():
        stored = horizon_stored(validation, tag)
        for unit in ("company", "pair"):
            row = stored["pooled"][unit]
            auto.append({"test": f"{tag}-{unit}",
                         "ci_includes_zero": not row["excludes_zero"],
                         "abs_delta": abs(row["delta"]), "mde": row["mde_80"],
                         "abs_delta_lt_mde": abs(row["delta"]) < row["mde_80"]})
        for row in stored["paired"]["G1_graph"]["per_window"]:
            if not row["excludes_zero"]:
                auto.append({"test": f"{tag}-{row['window']}",
                             "ci_includes_zero": True,
                             "abs_delta": abs(row["delta"]),
                             "mde": row["mde_80"],
                             "abs_delta_lt_mde": abs(row["delta"]) < row["mde_80"]})
    add("well-powered-vacuity", "prereg",
        "how often 'CI includes 0 => |delta| < MDE' holds in the reported table",
        None, {"cases_checked": len(auto),
               "cases_satisfying": sum(1 for row in auto if row["abs_delta_lt_mde"]),
               "all_satisfy": all(row["abs_delta_lt_mde"] for row in auto),
               "examples": auto[:3]}, "BUG", "CORRECTED_RESULT",
        "Because MDE = 2.80*SE while a 95% CI containing 0 forces |delta| <= ~1.96*SE "
        "(looser still for skewed percentile CIs), the NULL (well-powered) branch is "
        "triggered automatically by non-rejection. It cannot by itself be evidence that "
        "the study was well powered, and the protocol's alternative UNDERPOWERED branch "
        "has no operational threshold ('MDE larger than any reasonable effect').")
    add("well-powered-algebra", "prereg",
        "pre-registered NULL (well-powered) condition: CI includes 0 AND |delta| < MDE",
        "protocol section 11", "implied by non-rejection under MDE = (z.975+z.80)SE",
        "BUG", "CORRECTED_RESULT",
        "The label is close to a tautology; it must be replaced by an explicit statement "
        "of the power bound (pooled MDE and rule-level MDE).")
    warnings.append(
        "PRE_REGISTRATION section 11 criterion (c) requires point estimate >= MDE for "
        "SUPPORT. This is a power-dependent criterion: a real effect smaller than the "
        "study's MDE could never support H1 even if its CI excluded 0. It is applied "
        "literally here but should not be read as a scientific decision rule in a "
        "future round.")

    # ==================================================================================
    # 7. stability strata audit
    # ==================================================================================
    for tag, data in datasets.items():
        stored = horizon_stored(validation, tag)["stability"]
        g1, b2 = data["g1"], data["b2"]
        g1_full = {**g1, "probs_a": g1["probs"]}
        computed = {}
        for field in ("tracks", "companies", "origins"):
            values = sorted(set(g1[field]))
            usable = 0
            for value in values:
                index = np.asarray([i for i, key in enumerate(g1[field]) if key == value])
                labels = np.asarray(g1["labels"])[index]
                if labels.size < 10 or labels.sum() < 5:
                    continue
                usable += 1
            computed[field] = usable
        key_map = {"tracks": "by_track", "companies": "by_company",
                   "origins": "by_origin"}
        for field, stored_key in key_map.items():
            add(f"{tag}-strata-{field}", "strata",
                f"number of usable {field} strata (n>=10, positives>=5)",
                len(stored[stored_key]), computed[field], "PASS", "ORIGINAL_RESULT")
        unique = {field: strata_unique_counts(g1_full, field)
                  for field in ("tracks", "companies")}
        add(f"{tag}-strata-unique", "strata",
            "usable strata after collapsing triplicated overlapping-window rows",
            {"tracks": len(stored["by_track"]), "companies": len(stored["by_company"])},
            {"tracks": unique["tracks"]["usable_on_unique_pairs"],
             "companies": unique["companies"]["usable_on_unique_pairs"]},
            "BUG", "CORRECTED_RESULT",
            "The pre-declared n>=10/positives>=5 thresholds were applied to pooled rows "
            "in which each pair appears up to 3 times, so the strata counts are inflated: "
            "on unique pair counts almost no stratum qualifies (the H4 'conditional "
            "effect' question is even less identifiable than reported).")
        data["strata_unique"] = unique
        # stationarity of the exact strata values reported in STATISTICAL_VALIDATION.md
        note = "STATISTICAL_VALIDATION.md section 5 values reproduced"
        add(f"{tag}-strata-values", "strata", "best/worst reported stratum dAP", None,
            {"by_track_usable": computed["tracks"],
             "by_company_usable": computed["companies"]}, "PASS", "ORIGINAL_RESULT", note)

    # ==================================================================================
    # 8. assembled corrected numbers and verdict mapping
    # ==================================================================================
    corrected_numbers = {}
    for tag in ("H4q", "H2q"):
        stored = horizon_stored(validation, tag)
        data = datasets[tag]
        # re-derived numbers used in the correction document
        corrected_numbers[tag] = {
            "reported": {"delta": stored["pooled"]["company"]["delta"],
                         "company_ci": [stored["pooled"]["company"]["ci_low"],
                                        stored["pooled"]["company"]["ci_high"]],
                         "pair_ci": [stored["pooled"]["pair"]["ci_low"],
                                     stored["pooled"]["pair"]["ci_high"]],
                         "mde_80": stored["pooled"]["company"]["mde_80"],
                         "baseline_ap": stored["pooled"]["company"]["ap_b"]},
            "mde": mde_report[tag],
            "dedupe": data["duplication"],
            "strata_unique": data["strata_unique"],
            "randomisation": data["randomisation"],
        }
    corrected_numbers["H4q"]["rule_power"] = rule_at_reported
    corrected_numbers["H4q"]["mde_rule"] = rule["mde_rule"]

    # claims mapping
    claims = [
        {"claim": "Pooled dAP = -0.00609, company CI [-0.02219,+0.00450], pair CI "
                  "[-0.03347,+0.01043]",
         "tag": "ORIGINAL_RESULT", "status": "reproduced exactly (PASS)",
         "note": "The intervals are conditional on the 3 realised windows and are for "
                 "the pooled triplicated-row estimand; calibration simulation gives ~95% "
                 "coverage of that estimand."},
        {"claim": "The conclusion 'no evidence of improvement, CIs include 0' is stable",
         "tag": "UNCHANGED_FINDING", "status": "UNCHANGED",
         "note": "Company/pair percentile CIs, seed-averaged CIs, jackknife-t CIs, the "
                 "equal-weight mean-over-windows CI and per-window CIs all include 0."},
        {"claim": "Point estimate is negative (G1 worse than B2)",
         "tag": "ORIGINAL_RESULT", "status": "fragile",
         "note": "Deduplicating the overlapping windows flips the sign (first-window "
                 "subset +0.00062, last-window subset -0.01689); direction is not robust."},
        {"claim": "MDE(80%) = 0.01943 (26% of baseline AP) and the design is "
                  "'well-powered'",
         "tag": "INVALIDATED_FINDING", "status": "INVALIDATED (label)",
         "note": "MDE is the wrong-test MDE at 26% of baseline; the pre-registered "
                 "compound rule has ~16% power at that effect and needs ~0.037 AP "
                 "(~50% of baseline) for 80% power."},
        {"claim": "40/40 randomisations outperform the real graph; H2 reversed",
         "tag": "INVALIDATED_FINDING", "status": "INVALIDATED (method)",
         "note": "Randomised null model loses edges / breaks bipartite degrees / "
                 "collapses weights. Resolution is also limited to 1/41; the "
                 "pre-registered direction attains p=1.0."},
        {"claim": "'Random relations have predictive value'",
         "tag": "INVALIDATED_FINDING", "status": "NOT LICENSED",
         "note": "Even under a valid null, real AP below the null means the real "
                 "arrangement is atypical, not that random graphs are informative."},
        {"claim": "BH q=0.10 over the pre-registered family; 0/8 rejections",
         "tag": "UNCHANGED_FINDING", "status": "UNCHANGED (conclusion), BUG (code)",
         "note": "Correct step-up also rejects nothing; the implementation is "
                 "conservative, the thresholds are mis-assigned and the family is not "
                 "the pre-registered one."},
        {"claim": "H4 conditional effects undeterminable; 6/38 tracks and 5/51 "
                  "companies reportable",
         "tag": "UNCHANGED_FINDING", "status": "UNCHANGED and strengthened",
         "note": "Those counts are inflated by ~3x row duplication; on unique pairs "
                 "effectively no stratum meets the pre-declared thresholds."},
        {"claim": "0/3 holdout windows exclude zero",
         "tag": "UNCHANGED_FINDING", "status": "PASS",
         "note": "Verified against the stored per-window CIs."},
    ]

    # ----------------------------------------------------------------------------------
    # complete bug register (numeric evidence lives in `findings`)
    # ----------------------------------------------------------------------------------
    bugs.extend([
        {"id": "BUG-MDE-1",
         "title": "Normal-theory MDE (z.975+z.80)*SE is applied to a bounded, skewed "
                  "percentile-bootstrap AP difference; it is not the power of the test "
                  "actually used and is unstable across variance estimators",
         "location": "code/s028_stats.py line 33 (MDE_Z), lines 140-142 and 151-154 "
                     "(decide), code/s028_lib.py line 803 (mde_z default), line 854 "
                     "(mde_80 = mde_z * se)",
         "severity": "high", "direction": "overstates power",
         "evidence": {"H4q_company": {"reported": 0.019428,
                                      "bootstrap_quantile": 0.019712,
                                      "jackknife_t": 0.010909,
                                      "power_at_reported_quantile_method": 0.784},
                      "H4q_pair": {"reported": 0.029729,
                                   "bootstrap_quantile": 0.035071,
                                   "jackknife_t": 0.019039,
                                   "power_at_reported_quantile_method": 0.6295},
                      "H2q_company": {"reported": 0.043658,
                                      "bootstrap_quantile": 0.014728,
                                      "jackknife_t": 0.027040,
                                      "draw_skew": 2.885,
                                      "draw_bias": 0.004991}},
         "consequence": "The exact number 0.01943 is one of several defensible variance "
                        "estimates (range ~0.011-0.030 for the company unit alone). A "
                        "bounded statistic cannot support an unqualified normal-theory "
                        "MDE; report the range and the CI-based exclusion bound instead.",
         "tag": "CORRECTED_RESULT"},
        {"id": "BUG-BOOT-1",
         "title": "Pooling the three overlapping 4-quarter holdout windows triplicates "
                  "rows/positives: 5,159 pooled rows are 1,729 distinct pairs, and 67 "
                  "positive rows are only 32 distinct positive pairs (13 pairs are "
                  "positive in one window and negative in another)",
         "location": "code/s028_stats.py collect() lines 55-70; "
                     "code/s028_lib.py::paired_cluster_bootstrap lines 800-857 "
                     "(labels concatenated at lines 810-817)",
         "severity": "high", "direction": "overstates effective sample size / precision "
                                            "of the pooled estimand",
         "evidence": {"H4q_rows": 5159, "H4q_distinct_pairs": 1729,
                      "H4q_positive_rows": 67, "H4q_distinct_positive_pairs": 32,
                      "H4q_conflicting_label_pairs": 13,
                      "H4q_pair_multiplicity": {"3": 1709, "2": 12, "1": 8},
                      "H2q_positive_rows": 42, "H2q_distinct_positive_pairs": 28},
         "consequence": "The pooled AP is not an average of window APs (0.0690 vs mean "
                        "window AP 0.0786): the same pair can enter both the positive "
                        "and the negative side with near-identical predictions. The "
                        "target of inference ('pooled triplicated-row AP') is not the "
                        "pre-registered 'out-of-sample prediction at a holdout origin'.",
         "tag": "CORRECTED_RESULT"},
        {"id": "BUG-BOOT-2",
         "title": "p_one_sided = mean(bootstrap draws <= 0) is a one-sided "
                  "percentile-bootstrap tail probability, not the statistic of the "
                  "pre-registered decision rule, and it is not reliable when the "
                  "bootstrap distribution is skewed (H2q company: skew +2.89, bias "
                  "+0.005, CI asymmetry 5.2)",
         "location": "code/s028_lib.py line 855 (p_one_sided), lines 849-850 "
                     "(percentile CI), line 854 (MDE); used for BH in "
                     "code/s028_stats.py lines 223-229",
         "severity": "medium", "direction": "misleading p-value semantics",
         "evidence": {"H4q_company_p": 0.8935, "H4q_company_normal_p": 0.8104,
                      "H2q_company_p": 0.459, "H2q_company_normal_p": 0.508,
                      "H4q_company_skew": -1.761, "H2q_company_skew": 2.885,
                      "H2q_company_ci": [-0.010664, 0.053627]},
         "consequence": "Report the CI-based decision and, if a p-value is wanted, a "
                        "null-calibrated one; do not feed these tail probabilities into "
                        "BH as if they were calibrated p-values, and do not present them "
                        "as 'p(delta<=0)' posterior probabilities.",
         "tag": "CORRECTED_RESULT"},
        {"id": "BUG-BOOT-3",
         "title": "The percentile cluster bootstrap's uncertainty is estimator- and "
                  "unit-dependent: bootstrap SE vs delete-one-jackknife SE ratios are "
                  "1.82 (H4q company) and 1.56 (H4q pair); only 51 company clusters; "
                  "resampling concatenates duplicated rows",
         "location": "code/s028_lib.py::paired_cluster_bootstrap lines 826-857 "
                     "(cluster grouping 826-830, resample loop 833-842, percentile "
                     "quantiles 849, se 848)",
         "severity": "high", "direction": "interval/MDE instability",
         "evidence": {"H4q_company_bootstrap_se": 0.006935,
                      "H4q_company_jackknife_se": 0.003818,
                      "H4q_company_jackknife_ci": [-0.013758, 0.001579],
                      "H4q_pair_bootstrap_se": 0.010612,
                      "H4q_pair_jackknife_se": 0.006792,
                      "H4q_pair_jackknife_ci": [-0.019411, 0.007232],
                      "seed_ci_low_range_H4q": [-0.025219, -0.021319],
                      "seed_ci_high_range_H4q": [0.003693, 0.005714]},
         "consequence": "The CI includes zero under every variant (conclusion stable), "
                        "but the interval width, the MDE and the claim of precision are "
                        "not stable. Report the union of defensible intervals and an "
                        "explicit finite-cluster caveat.",
         "tag": "CORRECTED_RESULT"},
        {"id": "BUG-H2-1",
         "title": "The randomised null model is broken (edge loss, broken bipartite "
                  "degree sequences, collapsed weights); the 40/40 result is invalid as "
                  "a method claim (given by the parallel defect report, not re-derived "
                  "here)",
         "location": "code/s028_lib.py::SnapshotSeries._build_randomised lines 492-551 "
                     "(block list built at line 507 before rewiring, date re-draw and "
                     "weight collapse at lines 534-543)",
         "severity": "critical", "direction": "invalidates H2",
         "evidence": {"H4q_40_of_40": True, "real_ap": 0.069003,
                      "random_min": 0.069187, "random_max": 0.081982,
                      "H2q_30_of_40": True},
         "consequence": "No statement about relational specificity can be made from the "
                        "original G2 runs. H2 remains UNRESOLVED until corrected-G2 "
                        "predictions exist.",
         "tag": "INVALIDATED_FINDING"},
        {"id": "BUG-H2-2",
         "title": "The '97.5th percentile' threshold is implemented as the maximum: "
                  "sorted[int(0.975*n)] with n=40 is index 39",
         "location": "code/s028_stats.py lines 262-265 (real_above_975), line 254 "
                     "(median uses sorted[len//2], i.e. an upper median)",
         "severity": "low", "direction": "conservative for SUPPORT (harder to declare "
                                          "H2 supported)",
         "evidence": {"H4q_numpy_q975": 0.081343, "H4q_code_threshold": 0.081982,
                      "H4q_random_max": 0.081982, "H2q_numpy_q975": 0.094572,
                      "H2q_code_threshold": 0.100692},
         "consequence": "The criterion actually tested was real AP > max(40 draws), "
                        "which happens to be stricter than H2's stated criterion.",
         "tag": "CORRECTED_RESULT"},
        {"id": "BUG-H2-3",
         "title": "Tail claims from 40 draws exceed their resolution: minimum one-sided "
                  "p = 1/41 = 0.0244, and a 97.5th percentile of 40 draws is the "
                  "maximum up to interpolation; the pre-registered H2 direction "
                  "actually has p = 1.0",
         "location": "code/s028_stats.py lines 247-269 (H2 summary); "
                     "STATISTICAL_VALIDATION.md section 4; "
                     "PRE_REGISTRATION.md Amendment 1 A1.1",
         "severity": "high", "direction": "over-interpretation of the null tail",
         "evidence": {"resolution_one_sided": 0.0244, "resolution_two_sided": 0.0488,
                      "H4q_p_real_gt_random": 1.0, "H4q_p_real_lt_random": 0.0244,
                      "H4q_per_window_fraction_random_ge_real":
                          {"2025-04-01": 1.0, "2025-07-01": 0.525,
                           "2025-10-01": 0.825}},
         "consequence": "Even under a valid null, 'real below all 40 randomisations' is "
                        "a statement that the real arrangement is atypical (in the "
                        "opposite direction to H2), not evidence that random relations "
                        "carry predictive value. The reverse-direction tail is "
                        "post-hoc and cannot be promoted to a finding.",
         "tag": "INVALIDATED_FINDING"},
        {"id": "BUG-PREREG-1",
         "title": "'NULL (well-powered)' is almost a tautology: when a 95% CI contains "
                  "0, |delta| is necessarily below the MDE = 2.80*SE, so non-rejection "
                  "automatically triggers the 'well-powered' label",
         "location": "code/s028_stats.py lines 151-154; PRE_REGISTRATION.md section 11 "
                     "(lines 214-215); propagated to HYPOTHESIS_REGISTRY.md line 21, "
                     "GRAPH_RESULTS.md lines 42-44, PHASE_REPORT_ZH.md lines 163/262",
         "severity": "high", "direction": "overstates informativeness",
         "evidence": {"cases_checked": 10, "all_satisfy_abs_delta_lt_mde": True,
                      "H4q_reported_mde": 0.019428,
                      "H4q_rule_mde": 0.037365,
                      "H4q_rule_power_at_reported_mde": 0.163},
         "consequence": "'Well-powered' must be replaced by an explicit statement of "
                        "the pooled MDE AND the rule-level MDE (and the CI-based "
                        "exclusion bound); the protocol's UNDERPOWERED branch has no "
                        "operational threshold, so the NULL/UNDERPOWERED split is not "
                        "identified.",
         "tag": "CORRECTED_RESULT"},
        {"id": "BUG-PREREG-2",
         "title": "Post-hoc decision branch 'NULL (G1 significantly worse than "
                  "baseline)' is not in the pre-registered rule",
         "location": "code/s028_stats.py lines 147-150",
         "severity": "low", "direction": "post-hoc label (not triggered here)",
         "evidence": {"triggered_in_stored_results": False},
         "consequence": "If such a window had occurred it would have produced a verdict "
                        "label absent from the protocol. Add it via a dated amendment, "
                        "not silently.",
         "tag": "CORRECTED_RESULT"},
        {"id": "BUG-MDE-3",
         "title": "The reported MDE number is post hoc: computed from the realised "
                  "bootstrap SE after the predictions existed; only the method (not the "
                  "constant 2.8016 or the number) is covered by the freeze hash",
         "location": "code/s028_stats.py line 33; PRE_REGISTRATION.md section 10.4 "
                     "(method only); EXPERIMENT_PROTOCOL.md line 75 (exact constant, "
                     "not included in artifacts/prereg_freeze*.json)",
         "severity": "medium", "direction": "overstates design-stage power guarantee",
         "evidence": {"prereg_hash_matches_amendment_freeze": True,
                      "exact_formula_in_frozen_protocol": False,
                      "predictions_mtime": "2026-11-04 01:54:49",
                      "statistical_validation_mtime": "2026-11-04 01:57:14"},
         "consequence": "Report the MDE as an observed-data estimate with its range, "
                        "not as a pre-registered design guarantee.",
         "tag": "CORRECTED_RESULT"},
        {"id": "BUG-STRATA-1",
         "title": "Stability-stratum thresholds (n>=10, positives>=5) were applied to "
                  "pooled rows in which each company-track pair appears up to 3 times, "
                  "inflating the reported number of reportable strata",
         "location": "code/s028_stats.py::strata lines 97-114 (threshold at line 107; "
                     "field lookup fallback at line 101)",
         "severity": "medium", "direction": "overstates H4 identifiability",
         "evidence": {"H4q_reported_usable_tracks": 6, "H4q_unique_pair_usable_tracks": 0,
                      "H4q_reported_usable_companies": 5,
                      "H4q_unique_pair_usable_companies": 0,
                      "H2q_unique_pair_usable": {"tracks": 0, "companies": 0}},
         "consequence": "On unique pair counts no stratum meets the pre-declared "
                        "threshold, so H4 is even less identifiable than reported; the "
                        "correct statement is 'no reportable conditional strata', not "
                        "'6/38 tracks examined'.",
         "tag": "CORRECTED_RESULT"},
    ])

    summary = {
        "n_findings": len(findings),
        "n_documented_bugs": len(bugs),
        "verdict_counts": {
            "PASS": sum(1 for row in findings if row["verdict"] == "PASS"),
            "DISCREPANT": sum(1 for row in findings if row["verdict"] == "DISCREPANT"),
            "BUG": sum(1 for row in findings if row["verdict"] == "BUG"),
        },
        "unchanged_findings": sum(1 for row in claims if row["tag"] == "UNCHANGED_FINDING"),
        "invalidated_findings": sum(1 for row in claims
                                    if row["tag"] == "INVALIDATED_FINDING"),
        "unresolved_limitations": [
            "Exact sampling distribution of the pooled AP difference under a valid "
            "relation-randomisation null is unknown (needs the corrected-G2 artifact).",
            "The estimand is a pooled triplicated-row AP over 3 overlapping windows; "
            "its interpretation as an out-of-sample ranking metric is design-dependent, "
            "and no window-level generalisation is identified with only 3 windows.",
            "Bootstrap coverage for the pair-clustered unit with dependent pairs "
            "(same company) and triplicated rows is assessed only by simulation of the "
            "observed configuration, not by a known-truth generative model.",
            "Rule-level power uses a multivariate-normal location-shift approximation; "
            "alternative constructions with different variance structures can move the "
            "rule MDE, so it is a defensible order-of-magnitude statement (~0.04 AP), "
            "not an exact design guarantee.",
        ],
    }

    payload = {
        "study": "S-028",
        "audit": "independent statistical re-derivation (audit_21_statistics.py)",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_seconds": round(time.time() - started, 1),
        "provenance": provenance,
        "summary": summary,
        "findings": findings,
        "bugs": bugs,
        "warnings": warnings,
        "claims": claims,
        "corrected_numbers": corrected_numbers,
        "calibration": calibration,
        "original_g2_resolution": {
            tag: {"n_randomisations": datasets[tag]["randomisation"].get("n_randomisations"),
                  "resolution_one_sided": 1.0 / (datasets[tag]["randomisation"][
                      "n_randomisations"] + 1),
                  "p_one_sided_real_gt_random":
                      datasets[tag]["randomisation"]["p_one_sided_real_gt_random"],
                  "p_two_sided": datasets[tag]["randomisation"]["p_two_sided"]}
            for tag in datasets},
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                   sort_keys=True, default=str) + "\n", encoding="utf-8")

    # console summary
    print(f"S-028 statistical audit ({payload['runtime_seconds']}s)")
    print(f"  findings: {summary['n_findings']} "
          f"(PASS={summary['verdict_counts']['PASS']}, "
          f"DISCREPANT={summary['verdict_counts']['DISCREPANT']}, "
          f"BUG={summary['verdict_counts']['BUG']}), "
          f"documented bugs={summary['n_documented_bugs']}")
    for tag in ("H4q", "H2q"):
        stored = horizon_stored(validation, tag)
        print(f"  {tag}: dAP={stored['pooled']['company']['delta']:+.6f} "
              f"company CI=[{stored['pooled']['company']['ci_low']:+.6f},"
              f"{stored['pooled']['company']['ci_high']:+.6f}] "
              f"pair CI=[{stored['pooled']['pair']['ci_low']:+.6f},"
              f"{stored['pooled']['pair']['ci_high']:+.6f}]")
        print(f"        MDE normal={mde_report[tag]['mde_normal_recomputed']:.6f} "
              f"quantile={mde_report[tag]['mde_quantile_company']:.6f} "
              f"jackknife={mde_report[tag]['jackknife_mde_company']:.6f} "
              f"rel={mde_report[tag]['relative_to_baseline']:.3f}")
        print(f"        H2: R={datasets[tag]['randomisation']['n_randomisations']} "
              f"real={datasets[tag]['randomisation']['real_pooled_ap']:.6f} "
              f"p(real>random)={datasets[tag]['randomisation']['p_one_sided_real_gt_random']:.4f} "
              f"resolution={datasets[tag]['randomisation']['resolution_one_sided']:.4f}")
    print(f"  MDE rule (pre-registered compound rule, H4q) = {rule['mde_rule']:.6f} "
          f"({rule['mde_rule'] / stored_h4['pooled']['company']['ap_b']:.3f} x baseline AP)")
    print(f"  power at reported MDE (pooled test only) = "
          f"{mde_report['H4q']['power_at_reported_mde_company']:.3f}; "
          f"power of the actual rule = {rule_at_reported['power']:.3f}")
    print(f"  BH: min p={min(p_values):.4f}, correct rejections="
          f"{sum(1 for row in correct if row['reject'])}, buggy rejections="
          f"{sum(1 for row in buggy if row['reject'])}")
    print(f"  duplication (H4q): {datasets['H4q']['duplication']['multiplicity_hist']}; "
          f"{datasets['H4q']['duplication']['distinct_positive_pairs']} distinct positive "
          f"pairs for {int(sum(datasets['H4q']['g1']['labels']))} positive rows")
    print(f"  dedupe dAP: first={datasets['H4q']['duplication']['dedupe_first_delta']:+.6f} "
          f"last={datasets['H4q']['duplication']['dedupe_last_delta']:+.6f}")
    print(f"  CI coverage simulation: " +
          ", ".join(f"{unit}={calibration[unit]['coverage']:.3f}"
                    f" (95% CI {calibration[unit]['coverage_wilson_95'][0]:.3f}-"
                    f"{calibration[unit]['coverage_wilson_95'][1]:.3f})"
                    for unit in calibration))
    print(f"  strata on unique pairs: tracks="
          f"{datasets['H4q']['strata_unique']['tracks']['usable_on_unique_pairs']}/38, "
          f"companies={datasets['H4q']['strata_unique']['companies']['usable_on_unique_pairs']}/51")
    print(f"\nwrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
