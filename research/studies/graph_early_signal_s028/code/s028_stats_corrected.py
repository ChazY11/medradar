"""S-028 corrected statistical pipeline (independent audit re-implementation).

WHY THIS FILE EXISTS
--------------------
``s028_stats.py`` (frozen original) contains a several statistical defects that are
documented in ``STATISTICAL_REVIEW_CORRECTION.md`` and re-derived numerically by
``audit_21_statistics.py``.  This module is the *corrected* pipeline.  It never edits
the frozen originals, never refits a model, and only reads stored artifacts.

WHAT IT READS
-------------
(a) The original stored prediction artifacts (default, available now)::

        artifacts/predictions_H4q.json.gz
        artifacts/predictions_H2q.json.gz

    Schema used: ``{"panel": {"holdouts": [...]},
                    "specs": {spec: {"predictions": {origin: {
                        "labels": [...], "probs": [...],
                        "companies": [...], "pairs": [...], "tracks": [...]}}}}}}``

    The files may carry a UTF-8 BOM -> read with ``encoding="utf-8-sig"``.
    The original ``g2`` block (``{"randomisations": [{"pooled_ap": ...}], ...}``) is
    carried through and explicitly tagged ``provenance = original_buggy_g2`` because
    the randomised null model (``s028_lib.SnapshotSeries._build_randomised``) is known
    to be broken (see the parallel defect report).  Nothing in this module builds a
    conclusion on those numbers; they are used only to document what 40 draws can
    support and to recompute the resolution / tail arithmetic.

(b) A *future* corrected-G2 artifact set produced by the Lead:

        artifacts/correction_round_1/g2_corrected_H4q.json
        artifacts/correction_round_1/g2_corrected_H2q.json
        (``.json.gz`` is also accepted; a leading BOM is tolerated)

    Expected schema (the loader is deliberately defensive; every field is optional
    unless stated, and aliases are accepted)::

        {
          "label": "H4q",                      # optional; inferred from filename
          "horizon_quarters": 4,                # optional
          "holdouts": ["2025-04-01", ...],      # optional; default = original panel
          "real": {                             # optional: real-graph predictions
            "2025-04-01": {"labels": [...], "probs": [...],
                           "companies": [...], "pairs": [...], "tracks": [...]},
            ...                                 # OR under "predictions" / "specs"
          },
          "randomisations": [                   # required for an H2 re-test
            {"seed": 20261104,
             "predictions": {"2025-04-01": {"labels": [...], "probs": [...]}, ...},
             # summary-only entries are also accepted:
             # "pooled_ap": 0.0743, "per_window_ap": {"2025-04-01": 0.07, ...}
            },
            ...                                 # R entries
          ],
          "corrections": {"builder": "...", "notes": "..."}   # optional free-form
        }

    Rules applied by the loader:
      * per-origin arrays are validated (equal lengths, labels in {0,1}, labels must
        match the original artifact for the same origin if the original is present);
      * if a randomisation entry has per-row ``predictions`` the pooled AP is
        recomputed from rows (preferred); otherwise the stored ``pooled_ap`` is used;
      * if ``real`` is absent the original ``G1_graph`` predictions are used (and the
        label sets are cross-checked against the corrected randomisations).

    The current S-028-CORRECTION-1 artifacts are summary-only.  They carry::

        {"label": "H4q", "model": "N1",
         "panel": {"holdouts": [...]},
         "randomisations": 40,                       # int, number of draws
         "real_graph": {"pooled_pr_auc", "per_window_pr_auc", "test_labels_sha256"},
         "controls": {"specs": {B1/B2/G1: {"pooled_pr_auc", "per_window_pr_auc"}}},
         "records": [{"index", "seed", "null_model", "pooled_ap",
                      "per_window_ap", "per_window_delta_vs_real",
                      "test_labels_sha256", "invariants"}, ...],
         "summary": {...}}

    Two null models are supported via ``--g2-model``:
      * ``N1`` (default): strict degree-preserving simple bipartite double-edge swap;
      * ``N2``: N1 plus exact per-track activity volumes and exact per-track
        window-date / first-touch date multisets (company strength not exactly
        preserved; reported per record).

WHAT IT COMPUTES
----------------
1. Paired AP difference G1 - B2 with the two pre-registered clustering units
   (company, company-track pair), percentile cluster bootstrap, plus Monte-Carlo
   stability across seeds and a delete-one-cluster jackknife-t cross-check.
2. An equal-weight mean-over-windows statistic (avoids giving triplicated
   company-track rows ~3x weight in the pooled metric).
3. Two honest MDE definitions:
   * ``mde_normal``  = (z_0.975 + z_0.80) * SE_bootstrap  (the original formula, kept
     for comparability);
   * ``mde_quantile`` = -(q_0.025(E) + q_0.20(E)) where E are the *centred* bootstrap
     errors of the AP difference.  This is the same location-shift power logic but uses
     the empirical (skewed, bounded) bootstrap quantiles instead of normal z's.
   * ``mde_rule`` = smallest true pooled effect for which the *pre-registered compound
     decision rule* (>=2/3 windows, both clusterings, point >= MDE) reaches 80% power,
     from a multivariate-normal simulation whose covariance comes from the paired
     cluster bootstrap.
   Power at the originally reported MDE is reported for every definition.
4. Correct Benjamini-Hochberg step-up over the pre-registered family (and, for
   comparison, over the family the original script actually used), with one-sided
   bootstrap p-values; the original pointwise implementation is reproduced only to
   show it is conservative.
5. H2 randomisation test done correctly when corrected-G2 rows exist: empirical
   one-sided p = (1 + #{random >= real}) / (R + 1), two-sided p = 2(1 + ...)/(R+1),
   numpy-linear 97.5th percentile, attained resolution 1/(R+1).  With the original
   buggy-G2 summaries only the resolution / tail arithmetic is recomputed and the
   result is tagged INVALIDATED.
6. The PRE_REGISTRATION.md section 11 decision rule applied literally, plus an honest
   status label that does not use the unsupported phrase "well-powered".

OUTPUT
------
``artifacts/correction_round_1/stats_corrected_<tag>.json`` with ``tag="original"``
when only the original artifacts are available, or ``tag="g2_corrected"`` when the
corrected-G2 files were found (override with ``--tag``).

CLI
---
    python s028_stats_corrected.py [--tag auto|original|g2_corrected]
                                   [--resamples 2000] [--seed 7]
                                   [--horizons 4,2] [--no-power]

Run with cwd = this study's ``code/`` directory so that ``s028_lib`` (and the repo
root inserted by it) are importable.
"""
from __future__ import annotations

import argparse
import gzip
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
CORRECTION_DIR = ARTIFACTS / "correction_round_1"

sys.path.insert(0, str(CODE))
sys.path.insert(0, str(STUDY.parents[3] if len(STUDY.parents) >= 4 else STUDY))

from s028_lib import fast_ap  # noqa: E402

MDE_Z = 1.959964 + 0.841621  # z_{0.975} + z_{0.80} = 2.801585
Z975 = 1.959964
Z80 = 0.841621
Q_FDR = 0.10
RESAMPLES = 2000
SEED = 7
STABILITY_SEEDS = (1, 2, 3, 7, 11)
HORIZONS = {"4": ["2025-04-01", "2025-07-01", "2025-10-01"],
            "2": ["2025-10-01", "2026-01-01", "2026-04-01"]}


# --------------------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------------------
def _read_json(path: Path) -> Any:
    """Read JSON/JSON.GZ tolerating a UTF-8 BOM (the stored artifacts have one)."""
    if path.suffix == ".gz" or path.name.endswith(".json.gz"):
        with gzip.open(path, "rt", encoding="utf-8-sig") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def original_predictions_path(label: str) -> Path | None:
    for name in (f"predictions_{label}.json.gz", f"predictions_{label}.json"):
        path = ARTIFACTS / name
        if path.exists():
            return path
    return None


def load_original(label: str) -> dict[str, Any]:
    """Load a stored prediction artifact into plain numpy-free lists + windows."""
    path = original_predictions_path(label)
    if path is None:
        raise FileNotFoundError(f"no stored predictions for {label}")
    payload = _read_json(path)
    windows = list(payload["panel"]["holdouts"])
    specs: dict[str, dict[str, dict[str, Any]]] = {}
    for spec, block in payload["specs"].items():
        specs[spec] = {}
        for window, row in block.get("predictions", {}).items():
            specs[spec][window] = {
                "labels": list(row["labels"]),
                "probs": list(row["probs"]),
                "companies": list(row.get("companies", [])),
                "pairs": list(row.get("pairs", [])),
                "tracks": list(row.get("tracks", [])),
            }
    return {"label": label, "path": path, "sha256": sha256(path),
            "windows": windows, "panel": payload.get("panel", {}),
            "specs": specs, "g2": payload.get("g2", {}),
            "provenance": "original_stored_predictions"}


def _validate_rows(rows: dict[str, Any], where: str) -> dict[str, Any]:
    labels = list(rows.get("labels", []))
    probs = list(rows.get("probs", []))
    if len(labels) != len(probs):
        raise ValueError(f"{where}: labels/probs length mismatch")
    if not labels:
        raise ValueError(f"{where}: empty rows")
    if any(int(v) not in (0, 1) for v in labels):
        raise ValueError(f"{where}: labels not binary")
    for key in ("companies", "pairs", "tracks"):
        values = rows.get(key)
        if values is not None and len(values) != len(labels):
            raise ValueError(f"{where}: {key} length mismatch")
    return {"labels": [int(v) for v in labels], "probs": [float(v) for v in probs],
            "companies": list(rows.get("companies") or [""] * len(labels)),
            "pairs": list(rows.get("pairs") or [""] * len(labels)),
            "tracks": list(rows.get("tracks") or [""] * len(labels))}


def corrected_g2_paths(label: str, model: str | None = "N1") -> list[Path]:
    """Candidate paths for the corrected-G2 artifact of one null model.

    ``model`` is ``"N1"`` (strict degree-preserving simple bipartite double-edge
    swap) or ``"N2"`` (N1 + exact per-track activity volumes and exact per-track
    window-date / first-touch date multisets).  The legacy un-suffixed name
    ``g2_corrected_<label>.json`` is kept as a fallback so previously tested call
    sites do not break.
    """
    candidates: list[Path] = []
    for suffix in ([f"_{model}"] if model else []) + [""]:
        candidates += [CORRECTION_DIR / f"g2_corrected_{label}{suffix}.json",
                       CORRECTION_DIR / f"g2_corrected_{label}{suffix}.json.gz"]
    return candidates


def load_corrected_g2(label: str, original: dict[str, Any] | None = None,
                      model: str | None = "N1") -> dict[str, Any] | None:
    """Load a corrected-G2 artifact set for one null model; return None when absent.

    Supported schemas
    -----------------
    S-028-CORRECTION-1 (summary-only, the current artifact)::

        {"label": "H4q", "model": "N1", "panel": {"holdouts": [...]},
         "randomisations": 40,                     # int: the number of draws
         "real_graph": {"pooled_pr_auc": float,
                        "per_window_pr_auc": {origin: float},
                        "test_labels_sha256": {origin: sha}},
         "controls": {"specs": {"B1_history10"/"B2_frozen_spec16"/"G1_graph":
                                {"pooled_pr_auc": float,
                                 "per_window_pr_auc": {origin: float}}}},
         "records": [ {"index", "seed", "null_model", "pooled_ap",
                       "per_window_ap": {origin: ap},
                       "pooled_delta_vs_real", "per_window_delta_vs_real",
                       "test_labels_sha256": {origin: sha},
                       "invariants": {...}}, ... ]}

    Older / alternative schema (per-row predictions, optional ``real`` block)::

        {"holdouts": [...], "real": {origin: {"labels", "probs", ...}},
         "randomisations": [{"seed", "pooled_ap", "per_window_ap",
                             "predictions": {origin: {"labels", "probs", ...}}}]}

    Summary-only entries are enough for the H2 randomisation test; per-row entries
    (when present) are used to recompute the AP from rows and to cross-check that both
    arms are scored on the same labels.
    """
    path = next((p for p in corrected_g2_paths(label, model) if p.exists()), None)
    if path is None:
        return None
    payload = _read_json(path)
    real_graph = payload.get("real_graph") if isinstance(payload.get("real_graph"), dict) else {}
    windows = list(payload.get("holdouts") or [])
    if not windows and isinstance(real_graph.get("per_window_pr_auc"), dict):
        windows = list(real_graph["per_window_pr_auc"].keys())
    if not windows:
        windows = list((original or {}).get("windows") or HORIZONS.get(label[-2:-1], []))
    if original is not None:
        for window in original["windows"]:
            if window not in windows:
                windows.append(window)

    def _extract_rows(block: Any, origin: str, where: str) -> dict[str, Any] | None:
        if not isinstance(block, dict):
            return None
        if "labels" in block:
            return _validate_rows(block, f"{where}/{origin}")
        for alias in ("predictions", "specs"):
            nested = block.get(alias)
            if isinstance(nested, dict) and origin in nested:
                inner = nested[origin]
                if isinstance(inner, dict) and "labels" in inner:
                    return _validate_rows(inner, f"{where}/{origin}")
        return None

    # optional per-row real-graph predictions; fall back to the original G1 rows.
    real: dict[str, dict[str, Any]] = {}
    for window in windows:
        rows = _extract_rows(payload.get("real", {}), window, "real") \
            or _extract_rows(payload.get("real_predictions", {}), window, "real")
        if rows is None and original is not None:
            rows = original["specs"].get("G1_graph", {}).get(window)
            if rows is not None:
                rows = _validate_rows(rows, f"original G1/{window}")
        if rows is not None:
            real[window] = rows

    # summary-only real-graph block (current artifact).
    real_summary: dict[str, Any] = {}
    if real_graph.get("pooled_pr_auc") is not None:
        real_summary = {
            "pooled_ap": float(real_graph["pooled_pr_auc"]),
            "per_window_ap": dict(real_graph.get("per_window_pr_auc") or {}),
            "test_labels_sha256": (real_graph.get("test_labels_sha256")
                                   or payload.get("test_labels_sha256") or {}),
        }

    entries = payload.get("records")
    if not isinstance(entries, list) or not entries:
        entries = payload.get("randomisations")
    if not isinstance(entries, list):
        entries = []
    if not entries:
        raise ValueError(f"{path}: no usable randomisation records")

    records: list[dict[str, Any]] = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        record: dict[str, Any] = {
            "index": entry.get("index", position),
            "seed": entry.get("seed"),
            "pooled_ap": entry.get("pooled_ap"),
            "per_window_ap": entry.get("per_window_ap"),
            "per_window_delta_vs_real": entry.get("per_window_delta_vs_real"),
            "pooled_delta_vs_real": entry.get("pooled_delta_vs_real"),
            "null_model": entry.get("null_model", payload.get("model", model)),
            "invariants": entry.get("invariants", {}),
            "test_labels_sha256": entry.get("test_labels_sha256"),
            "predictions": {},
        }
        for window in windows:
            rows = (_extract_rows(entry.get("predictions", {}), window, "random")
                    or _extract_rows(entry.get("specs", {}), window, "random")
                    or _extract_rows(entry, window, "random"))
            if rows is not None:
                record["predictions"][window] = rows
        if record["pooled_ap"] is None and record["predictions"]:
            labels, probs = [], []
            for window in windows:
                row = record["predictions"].get(window)
                if row is None:
                    continue
                labels += row["labels"]
                probs += row["probs"]
            if labels:
                record["pooled_ap"] = fast_ap(labels, probs)
                record["_recomputed_from_rows"] = True
        records.append(record)

    top_hashes = payload.get("test_labels_sha256") or real_summary.get("test_labels_sha256")
    record_hashes = [record.get("test_labels_sha256") for record in records
                     if record.get("test_labels_sha256")]
    hash_consistent: bool | None = None
    if top_hashes and record_hashes:
        hash_consistent = all(value == top_hashes for value in record_hashes)
    invariants_all_preserved: bool | None = None
    flag_names = [name for name in ("all_degrees_preserved", "all_node_sets_preserved",
                                    "all_simple", "all_total_event_counts_preserved",
                                    "all_track_entry_multisets_preserved")
                  if any(name in (record.get("invariants") or {}) for record in records)]
    if flag_names:
        invariants_all_preserved = all(
            bool((record.get("invariants") or {}).get(name, True))
            for record in records for name in flag_names)
    return {"path": path, "sha256": sha256(path), "label": label,
            "model": model or payload.get("model"),
            "windows": windows, "real": real, "real_summary": real_summary,
            "randomisations": records,
            "controls": payload.get("controls", {}),
            "summary": payload.get("summary", {}),
            "test_labels_sha256": top_hashes,
            "test_labels_sha256_consistent": hash_consistent,
            "invariants_all_preserved": invariants_all_preserved,
            "corrections": payload.get("corrections", {}),
            "provenance": "corrected_g2_artifact"}


# --------------------------------------------------------------------------------------
# collection helpers
# --------------------------------------------------------------------------------------
def collect(spec_predictions: dict[str, Any], windows: list[str]) -> dict[str, Any]:
    """Concatenate per-origin row blocks into flat pooled arrays."""
    labels: list[int] = []
    probs: list[float] = []
    companies: list[str] = []
    pairs: list[str] = []
    tracks: list[str] = []
    origins: list[str] = []
    for window in windows:
        row = spec_predictions.get(window)
        if row is None:
            continue
        n = len(row["labels"])
        labels.extend(int(v) for v in row["labels"])
        probs.extend(float(v) for v in row["probs"])
        companies.extend(row.get("companies") or [""] * n)
        pairs.extend(row.get("pairs") or [""] * n)
        tracks.extend(row.get("tracks") or [""] * n)
        origins.extend([window] * n)
    if not labels:
        raise ValueError("empty collection")
    return {"labels": labels, "probs": probs, "companies": companies,
            "pairs": pairs, "tracks": tracks, "origins": origins}


def point_delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    if a["labels"] != b["labels"]:
        raise ValueError("paired rows are not the same label vector")
    ap_a = fast_ap(a["labels"], a["probs"])
    ap_b = fast_ap(b["labels"], b["probs"])
    return {"ap_a": ap_a, "ap_b": ap_b,
            "delta": (ap_a - ap_b) if ap_a is not None and ap_b is not None else None}


def _cluster_groups(keys: list[str]) -> tuple[list[str], list[np.ndarray]]:
    order = sorted(set(keys))
    buckets: dict[str, list[int]] = {key: [] for key in order}
    for index, key in enumerate(keys):
        buckets[key].append(index)
    return order, [np.asarray(buckets[key], dtype=int) for key in order]


def _draw_ap_diff(y: np.ndarray, pa: np.ndarray, pb: np.ndarray,
                  rows: np.ndarray) -> float | None:
    sample_y = y[rows]
    if sample_y.sum() in (0.0, float(sample_y.size)):
        return None
    value_a = fast_ap(sample_y, pa[rows])
    value_b = fast_ap(sample_y, pb[rows])
    if value_a is None or value_b is None:
        return None
    return value_a - value_b


def bootstrap_delta(a: dict[str, Any], b: dict[str, Any], unit: str = "company",
                    *, resamples: int = RESAMPLES, seed: int = SEED) -> dict[str, Any]:
    """Paired percentile cluster bootstrap of AP(a) - AP(b) (one clustering unit)."""
    y = np.asarray(a["labels"], dtype=float)
    pa = np.asarray(a["probs"], dtype=float)
    pb = np.asarray(b["probs"], dtype=float)
    keys = a["companies"] if unit == "company" else a["pairs"]
    order, groups = _cluster_groups(keys)
    rng = np.random.default_rng(seed)
    draws: list[float] = []
    for _ in range(resamples):
        picks = rng.integers(0, len(groups), size=len(groups))
        rows = np.concatenate([groups[i] for i in picks])
        value = _draw_ap_diff(y, pa, pb, rows)
        if value is not None:
            draws.append(value)
    base = point_delta(a, b)
    if not draws:
        return {**base, "ci_low": None, "ci_high": None, "se": None,
                "mde_80": None, "p_one_sided": None, "draws": [], "unit": unit,
                "clusters": len(order), "resamples_valid": 0, "seed": seed}
    values = np.asarray(draws, dtype=float)
    low, high = (float(v) for v in np.quantile(values, [0.025, 0.975]))
    se = float(values.std(ddof=1))
    return {**base, "unit": unit, "clusters": len(order), "rows": int(y.size),
            "positives": int(y.sum()), "seed": seed,
            "resamples": resamples, "resamples_valid": int(values.size),
            "ci_low": low, "ci_high": high, "se": se,
            "mde_80": MDE_Z * se,
            "p_one_sided": float((values <= 0).mean()),
            "excludes_zero": bool(low > 0 or high < 0),
            "draws": values}


def pooled_bootstrap(a: dict[str, Any], b: dict[str, Any], unit: str,
                     *, resamples: int = RESAMPLES, seed: int = SEED) -> dict[str, Any]:
    return bootstrap_delta(a, b, unit, resamples=resamples, seed=seed)


def seed_stability(a: dict[str, Any], b: dict[str, Any], unit: str,
                   seeds: tuple[int, ...] = STABILITY_SEEDS) -> dict[str, Any]:
    lows, highs, ses, draws = [], [], [], []
    for seed in seeds:
        result = bootstrap_delta(a, b, unit, seed=seed)
        if result["ci_low"] is None:
            continue
        lows.append(result["ci_low"])
        highs.append(result["ci_high"])
        ses.append(result["se"])
        draws.extend(result["draws"].tolist())
    if not lows:
        return {"seeds": list(seeds), "available": False}
    combined = np.asarray(draws, dtype=float)
    return {"seeds": list(seeds), "available": True,
            "ci_low_min": min(lows), "ci_low_max": max(lows),
            "ci_high_min": min(highs), "ci_high_max": max(highs),
            "se_min": min(ses), "se_max": max(ses),
            "combined_ci_low": float(np.quantile(combined, 0.025)),
            "combined_ci_high": float(np.quantile(combined, 0.975)),
            "combined_resamples": int(combined.size)}


def jackknife_delta(a: dict[str, Any], b: dict[str, Any], unit: str) -> dict[str, Any]:
    """Delete-one-cluster jackknife SE + t interval (independent variance cross-check)."""
    y = np.asarray(a["labels"], dtype=float)
    pa = np.asarray(a["probs"], dtype=float)
    pb = np.asarray(b["probs"], dtype=float)
    keys = a["companies"] if unit == "company" else a["pairs"]
    order, groups = _cluster_groups(keys)
    values = []
    for group in groups:
        mask = np.ones(y.size, dtype=bool)
        mask[group] = False
        if y[mask].sum() in (0.0, float(mask.sum())):
            continue
        value_a = fast_ap(y[mask], pa[mask])
        value_b = fast_ap(y[mask], pb[mask])
        values.append(value_a - value_b)
    values = np.asarray(values, dtype=float)
    g = values.size
    theta = float(values.mean())
    se = float(math.sqrt((g - 1) / g * float(((values - theta) ** 2).sum())))
    # t quantiles via a small Student-t CDF inversion (numpy-only, no scipy dependency)
    t975 = _t_quantile(0.975, g - 1)
    t80 = _t_quantile(0.80, g - 1)
    delta = point_delta(a, b)["delta"]
    return {"unit": unit, "clusters": g, "se": se, "theta": theta,
            "ci_low": delta - t975 * se, "ci_high": delta + t975 * se,
            "mde_80": (t975 + t80) * se, "t_975": t975, "t_80": t80,
            "delta": delta}


def _t_quantile(p: float, df: int) -> float:
    """Deterministic Student-t quantile by bisection on the regularised CDF."""
    if df <= 0:
        return float("nan")
    target = p
    lo, hi = -50.0, 50.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _t_cdf(mid, df) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _t_cdf(x: float, df: int) -> float:
    """Student-t CDF via incomplete beta (continued fraction)."""
    x2 = df / (df + x * x)
    ib = _incomplete_beta(0.5 * df, 0.5, x2)
    return 1.0 - 0.5 * ib if x > 0 else 0.5 * ib


def _incomplete_beta(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1.0 - x) * b - log_beta) / a
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x)
    return 1.0 - _incomplete_beta(b, a, 1.0 - x)


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Lentz's continued fraction for the incomplete beta function."""
    tiny = 1e-30
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    result = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((a + m2 - 1.0) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        result *= d * c
        aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1.0))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        step = d * c
        result *= step
        if abs(step - 1.0) < 1e-15:
            break
    return result


# --------------------------------------------------------------------------------------
# joint bootstrap (per-window + pooled), MDE / power
# --------------------------------------------------------------------------------------
def joint_bootstrap(a: dict[str, Any], b: dict[str, Any], windows: list[str],
                    *, resamples: int = RESAMPLES, seed: int = SEED) -> dict[str, Any]:
    """One bootstrap pass recording per-window and pooled company-clustered deltas.

    A single company resample set is applied to *all* windows, so the joint
    distribution (and thus the correlation between window-level statistics) is
    preserved.  Needed for rule-level power.
    """
    origins = np.asarray(a["origins"])
    companies = np.asarray(a["companies"])
    universal = sorted(set(companies.tolist()))
    universal_index = {key: i for i, key in enumerate(universal)}
    company_ids = np.asarray([universal_index[key] for key in companies])
    pooled_y = np.asarray(a["labels"], dtype=float)
    pooled_pa = np.asarray(a["probs"], dtype=float)
    pooled_pb = np.asarray(b["probs"], dtype=float)
    cluster_rows = [np.flatnonzero(company_ids == cid) for cid in range(len(universal))]
    # per-window local arrays; map pool row -> local position (-1 if absent)
    per_window: dict[str, dict[str, np.ndarray]] = {}
    for window in windows:
        mask = origins == window
        if not mask.any():
            continue
        idx = np.flatnonzero(mask)
        pos_map = np.full(pooled_y.size, -1, dtype=int)
        pos_map[idx] = np.arange(idx.size)
        per_window[window] = {
            "y": pooled_y[idx], "pa": pooled_pa[idx], "pb": pooled_pb[idx],
            "pos_map": pos_map}
    rng = np.random.default_rng(seed)
    draws = np.full((resamples, len(windows) + 1), np.nan)
    for draw in range(resamples):
        picks = rng.integers(0, len(cluster_rows), size=len(cluster_rows))
        rows = np.concatenate([cluster_rows[i] for i in picks])
        pooled_value = _draw_ap_diff(pooled_y, pooled_pa, pooled_pb, rows)
        if pooled_value is None:
            continue
        draws[draw, -1] = pooled_value
        ok = True
        for position, window in enumerate(windows):
            local = per_window.get(window)
            if local is None:
                ok = False
                break
            local_pos = local["pos_map"][rows]
            local_pos = local_pos[local_pos >= 0]
            if local_pos.size == 0 or local["y"][local_pos].sum() in (
                    0.0, float(local_pos.size)):
                ok = False
                break
            value = fast_ap(local["y"][local_pos], local["pa"][local_pos]) - \
                fast_ap(local["y"][local_pos], local["pb"][local_pos])
            if value is None:
                ok = False
                break
            draws[draw, position] = value
        if not ok:
            draws[draw, :] = np.nan
    valid = ~np.isnan(draws).any(axis=1)
    return {"draws": draws[valid], "windows": windows,
            "observed": np.asarray([point_delta(
                _slice_collect(a, window), _slice_collect(b, window))["delta"]
                for window in windows] + [point_delta(a, b)["delta"]]),
            "resamples_valid": int(valid.sum())}


def _slice_collect(collection: dict[str, Any], window: str) -> dict[str, Any]:
    origins = np.asarray(collection["origins"])
    mask = origins == window
    keys = ["labels", "probs", "companies", "pairs", "tracks"]
    out = {key: [collection[key][i] for i in np.flatnonzero(mask)] for key in keys}
    return out


def normal_mde(se: float) -> float:
    return MDE_Z * se


def quantile_mde(draws: np.ndarray, point: float) -> dict[str, float]:
    """Location-shift (bootstrap-power) MDE using empirical, skewed quantiles.

    The percentile CI is ``[q_0.025(draws), q_0.975(draws)]``; relative to the point
    estimate its lower half-width is ``q_0.025(draws) - point``.  A hypothetical
    experiment with true effect ``delta`` has (location-shift) rejection probability
    ``P(delta + E > -(q_0.025(draws) - point))`` with ``E = draws - point``; setting
    that to 0.8 gives ``delta = -(q_0.025(E) + q_0.20(E))`` because
    ``P(E > q_0.20) = 0.8``.
    """
    values = np.asarray(draws, dtype=float)
    errors = values - point
    q_low, q_20 = (float(v) for v in np.quantile(errors, [0.025, 0.20]))
    return {"mde": -(q_low + q_20), "q_025_centred": q_low, "q_20_centred": q_20,
            "bootstrap_bias": float(values.mean() - point),
            "skewness": _skew(values)}


def _skew(values: np.ndarray) -> float | None:
    if values.size < 3:
        return None
    mean = values.mean()
    sd = values.std(ddof=1)
    if sd == 0:
        return None
    return float(((values - mean) ** 3).mean() / sd ** 3)


def power_at(delta: float, draws: np.ndarray, point: float) -> float:
    values = np.asarray(draws, dtype=float)
    errors = values - point
    q_low = float(np.quantile(errors, 0.025))
    return float(np.mean((delta + errors) > -q_low))


def rule_power(delta: float, joint: dict[str, Any], se_pair: float,
               mde_company: float, *, n_sim: int = 200_000,
               seed: int = 20261104) -> dict[str, Any]:
    """Power of the PRE_REGISTRATION section 11 compound decision rule.

    Approximations (documented): statistics are multivariate normal with covariance
    from the paired company-cluster bootstrap; the pair-clustered pooled statistic is
    assumed perfectly correlated with the company-clustered pooled statistic and to
    use its own (larger) bootstrap SE; criterion (c) uses the observed-MDE threshold.
    """
    draws = np.asarray(joint["draws"], dtype=float)
    observed = np.asarray(joint["observed"], dtype=float)
    errors = draws - observed
    covariance = np.cov(errors.T)
    se_windows = errors[:, :-1].std(axis=0, ddof=1)
    se_pool = float(errors[:, -1].std(ddof=1))
    rng = np.random.default_rng(seed)
    sample = rng.multivariate_normal(np.zeros(covariance.shape[0]), covariance, size=n_sim)
    x = delta + sample
    a = np.sum(np.abs(x[:, :-1]) > Z975 * se_windows[None, :], axis=1) >= 2
    b = np.abs(x[:, -1]) > Z975 * se_pair
    c = x[:, -1] >= mde_company
    return {"delta": delta, "power": float(np.mean(a & b & c)),
            "power_2of3_windows": float(np.mean(a)),
            "power_both_clusterings": float(np.mean(b)),
            "power_point_above_mde": float(np.mean(c)),
            "se_windows": se_windows.tolist(), "se_pooled_company": se_pool,
            "se_pooled_pair": se_pair, "mde_company": mde_company}


def rule_mde(joint: dict[str, Any], se_pair: float, mde_company: float,
             target: float = 0.80, lo: float = 0.0, hi: float = 0.25,
             *, n_sim: int = 80_000) -> dict[str, Any]:
    for _ in range(40):
        mid = (lo + hi) / 2.0
        power = rule_power(mid, joint, se_pair, mde_company, n_sim=n_sim)["power"]
        if power < target:
            lo = mid
        else:
            hi = mid
    return {"mde_rule": (lo + hi) / 2.0, "target_power": target}


# --------------------------------------------------------------------------------------
# multiplicity
# --------------------------------------------------------------------------------------
def bh_stepup(p_values: list[float], q: float = Q_FDR) -> list[dict[str, Any]]:
    """Correct Benjamini-Hochberg step-up: reject every rank <= k_max."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: (p_values[i], i))
    k_max = 0
    thresholds_by_rank: dict[int, float] = {}
    for rank in range(1, m + 1):
        threshold = q * rank / m
        thresholds_by_rank[rank] = threshold
        if p_values[order[rank - 1]] <= threshold:
            k_max = rank
    rejected = set(order[:k_max])
    rank_of = {index: rank for rank, index in enumerate(order, start=1)}
    return [{"index": i, "p": p_values[i], "rank_ascending": rank_of[i],
             "bh_threshold": thresholds_by_rank[rank_of[i]],
             "reject": i in rejected} for i in range(m)]


def bh_pointwise_buggy(p_values: list[float], q: float = Q_FDR) -> list[dict[str, Any]]:
    """Faithful reproduction of s028_stats.py::bh (lines 117-129, buggy)."""
    indexed = sorted(enumerate(p_values), key=lambda pair: pair[1])
    m = len(p_values)
    result = [{"index": index, "p": value, "reject": False}
              for index, value in enumerate(p_values)]
    previous = 1.0
    for rank, (index, value) in enumerate(reversed(indexed), start=1):
        threshold = q * (m - rank + 1) / m
        if value <= threshold and previous >= 0:
            result[index]["reject"] = True
        previous = min(previous, value)
    for entry in result:
        entry["bh_threshold"] = q * (entry["index"] + 1) / m  # unsorted index: misassigned
    return result


# --------------------------------------------------------------------------------------
# H2 randomisation test
# --------------------------------------------------------------------------------------
def randomisation_test(real_ap: float, random_aps: list[float]) -> dict[str, Any]:
    values = np.asarray([v for v in random_aps if v is not None], dtype=float)
    r = int(values.size)
    if r == 0 or real_ap is None:
        return {"n_randomisations": r, "available": False}
    greater = int(np.sum(values >= real_ap))
    less = int(np.sum(values <= real_ap))
    return {
        "available": True, "n_randomisations": r, "real_pooled_ap": real_ap,
        "randomised_ap_min": float(values.min()),
        "randomised_ap_q025": float(np.quantile(values, 0.025)),
        "randomised_ap_median": float(np.median(values)),
        "randomised_ap_q975": float(np.quantile(values, 0.975)),
        "randomised_ap_max": float(values.max()),
        "n_random_at_or_above_real": greater,
        "n_random_at_or_below_real": less,
        "fraction_random_at_or_above_real": greater / r,
        "p_one_sided_real_gt_random": (1 + greater) / (r + 1),
        "p_one_sided_real_lt_random": (1 + less) / (r + 1),
        "p_two_sided": min(1.0, 2 * (1 + min(greater, less)) / (r + 1)),
        "resolution_one_sided": 1.0 / (r + 1),
        "real_above_q975": bool(real_ap > float(np.quantile(values, 0.975))),
        "real_above_max": bool(real_ap > float(values.max())),
        "real_below_min": bool(real_ap < float(values.min())),
        "original_code_effective_threshold": float(np.sort(values)[
            min(r - 1, int(0.975 * r))]),
        "note": ("R draws can only resolve tail statements to 1/(R+1); with R=40 the "
                 "97.5th percentile is essentially the maximum (linear-interpolated "
                 "quantile sits between the 39th and 40th order statistics)."),
    }


def h2_from_corrected_g2(label: str, corrected: dict[str, Any],
                         original: dict[str, Any] | None) -> dict[str, Any]:
    """Recompute the H2 randomisation test on a corrected-G2 artifact set.

    Works for summary-only corrected artifacts (``real_graph.pooled_pr_auc`` and
    ``records[i].pooled_ap``) as well as for per-row variants.  The test is the exact
    paired randomisation test: real and randomised arms are scored on the SAME holdout
    rows / the SAME pooled AP estimator, so the comparison is internally valid even
    though the pooled estimand triplicates company-track pairs (see the correction
    document, section 12).
    """
    windows = corrected["windows"]
    real_ap: float | None = None
    real_labels: dict[str, list[int]] = {}
    per_window_real: dict[str, float | None] = {}
    summary = corrected.get("real_summary") or {}
    if summary.get("pooled_ap") is not None:
        real_ap = float(summary["pooled_ap"])
        per_window_real = {window: (float(value) if value is not None else None)
                           for window, value in (summary.get("per_window_ap") or {}).items()}
    elif corrected["real"]:
        labels, probs = [], []
        for window in windows:
            row = corrected["real"].get(window)
            if row is None:
                continue
            real_labels[window] = row["labels"]
            labels += row["labels"]
            probs += row["probs"]
            per_window_real[window] = fast_ap(row["labels"], row["probs"])
        real_ap = fast_ap(labels, probs) if labels else None
    elif original is not None:
        block = collect(original["specs"]["G1_graph"], windows)
        real_ap = fast_ap(block["labels"], block["probs"])
        real_labels = {window: original["specs"]["G1_graph"][window]["labels"]
                       for window in windows if window in original["specs"]["G1_graph"]}
        per_window_real = {window: fast_ap(
            original["specs"]["G1_graph"][window]["labels"],
            original["specs"]["G1_graph"][window]["probs"])
            for window in windows if window in original["specs"]["G1_graph"]}
    random_aps: list[float] = []
    per_window_random: dict[str, list[float]] = {window: [] for window in windows}
    skipped = 0
    for record in corrected["randomisations"]:
        pooled_ap = record.get("pooled_ap")
        if record.get("predictions"):
            labels, probs = [], []
            consistent = True
            for window in windows:
                row = record["predictions"].get(window)
                if row is None:
                    continue
                if real_labels.get(window) is not None and row["labels"] != real_labels[window]:
                    consistent = False
                    break
                labels += row["labels"]
                probs += row["probs"]
                per_window_random[window].append(fast_ap(row["labels"], row["probs"]))
            if not consistent:
                skipped += 1
                continue
            pooled_ap = fast_ap(labels, probs) if labels else pooled_ap
        elif record.get("per_window_ap"):
            for window, value in record["per_window_ap"].items():
                if window in per_window_random and value is not None:
                    per_window_random[window].append(float(value))
        if pooled_ap is not None:
            random_aps.append(float(pooled_ap))
    if not per_window_real and original is not None:
        per_window_real = {window: fast_ap(
            original["specs"]["G1_graph"][window]["labels"],
            original["specs"]["G1_graph"][window]["probs"])
            for window in windows if window in original["specs"]["G1_graph"]}
    result = randomisation_test(real_ap, random_aps)
    result.update({"provenance": "corrected_g2_artifact",
                   "artifact": str(corrected["path"]),
                   "artifact_sha256": corrected["sha256"],
                   "null_model": corrected.get("model"),
                   "skipped_inconsistent_records": skipped,
                   "test_labels_sha256": corrected.get("test_labels_sha256"),
                   "test_labels_sha256_consistent":
                       corrected.get("test_labels_sha256_consistent"),
                   "invariants_all_preserved": corrected.get("invariants_all_preserved"),
                   "controls": {
                       "specs": {name: {"pooled_pr_auc": value.get("pooled_pr_auc"),
                                        "per_window_pr_auc":
                                            value.get("per_window_pr_auc")}
                                 for name, value in
                                 (corrected.get("controls", {}).get("specs", {}) or {}).items()
                                 if isinstance(value, dict)}},
                   "artifact_summary": corrected.get("summary", {}),
                   "per_window_real_ap": per_window_real,
                   "per_window_random_ap": {
                       window: (randomisation_test(per_window_real.get(window),
                                                   per_window_random[window])
                                if per_window_random[window] else None)
                       for window in windows}})
    result["criterion_d_real_above_q975"] = bool(
        result.get("real_above_q975") and result.get("real_pooled_ap") is not None)
    result["criterion_d_only_note"] = (
        "H2 SUPPORTED also requires H1 SUPPORTED (PRE_REGISTRATION.md section 11); "
        "this field covers criterion (d) only. The pre-registered direction is "
        "'real ABOVE random'; a real AP below the null distribution is the OPPOSITE "
        "direction and is not evidence that random relations predict.")
    return result


def h2_from_original_g2(original: dict[str, Any]) -> dict[str, Any]:
    g2 = original.get("g2", {})
    random_aps = [row.get("pooled_ap") for row in g2.get("randomisations", [])]
    result = randomisation_test(g2.get("real_pooled_ap"), random_aps)
    result.update({"provenance": "original_buggy_g2",
                   "status": "INVALIDATED",
                   "note": "Randomised null model loses edges / breaks degree sequences; "
                           "these 40 draws cannot support a method claim."})
    return result


# --------------------------------------------------------------------------------------
# decision rules
# --------------------------------------------------------------------------------------
def literal_decision(pooled: dict[str, Any], window_results: list[dict[str, Any]]) -> dict[str, Any]:
    """PRE_REGISTRATION.md section 11, transcribed literally (including (c))."""
    windows_excluding = sum(1 for row in window_results if row.get("excludes_zero"))
    total = len(window_results)
    a = total > 0 and windows_excluding >= math.ceil(2 * total / 3)
    company = pooled.get("company", {})
    pair = pooled.get("pair", {})
    b = bool(company.get("excludes_zero") and pair.get("excludes_zero"))
    point = company.get("delta")
    mde = company.get("mde_80")
    c = point is not None and mde is not None and point >= mde
    supported = bool(a and b and c)
    if supported:
        status = "SUPPORTED"
    elif any(row.get("ci_high") is not None and row["ci_high"] < 0 for row in window_results):
        status = "NULL (G1 significantly worse than baseline)"
    elif point is not None and mde is not None and abs(point) < mde:
        status = "NULL (well-powered: |delta| below MDE)"
    else:
        status = "UNDERPOWERED (cannot distinguish from zero)"
    return {"criteria": {"a_2of3_windows_ci_excludes_zero": a,
                         "b_pooled_both_clusterings_exclude_zero": b,
                         "c_point_at_or_above_mde": c,
                         "windows_excluding_zero": windows_excluding,
                         "total_windows": total},
            "literal_h1_status": status}


def corrected_decision(pooled: dict[str, Any], window_results: list[dict[str, Any]],
                       *, mde_quantile_company: float, mde_rule: float,
                       rule_power_at_reported: float, baseline_ap: float) -> dict[str, Any]:
    literal = literal_decision(pooled, window_results)
    company = pooled.get("company", {})
    point = company.get("delta")
    mde_normal = company.get("mde_80")
    if literal["literal_h1_status"] == "SUPPORTED":
        honest = "SUPPORTED"
    elif literal["criteria"]["a_2of3_windows_ci_excludes_zero"] or \
            literal["criteria"]["b_pooled_both_clusterings_exclude_zero"]:
        honest = "PARTIAL / UNDERPOWERED"
    else:
        honest = "NULL (no detected incremental signal; NOT well-powered)"
    return {**literal,
            "corrected_h1_status": honest,
            "why_not_well_powered": {
                "mde_normal_reported": mde_normal,
                "mde_quantile_local_alternative": mde_quantile_company,
                "mde_rule_pre_registered_compound_rule": mde_rule,
                "rule_power_at_reported_mde": rule_power_at_reported,
                "mde_relative_to_baseline_ap": (mde_normal / baseline_ap
                                                if baseline_ap and mde_normal else None),
                "mde_rule_relative_to_baseline_ap": (mde_rule / baseline_ap
                                                     if baseline_ap and mde_rule else None),
                "interpretation": ("The reported MDE is the pooled-test MDE only; the "
                                   "pre-registered verdict requires >=2/3 windows, both "
                                   "clusterings and point >= MDE, for which power at the "
                                   "reported MDE is far below 80%."),
            }}


# --------------------------------------------------------------------------------------
# the per-horizon analysis
# --------------------------------------------------------------------------------------
def analyse_horizon(label: str, tag: str, *, resamples: int = RESAMPLES,
                    seed: int = SEED, power: bool = True,
                    corrected: dict[str, Any] | None = None) -> dict[str, Any]:
    original = load_original(label)
    windows = original["windows"]
    b2 = collect(original["specs"]["B2_frozen_spec16"], windows)
    g1 = collect(original["specs"]["G1_graph"], windows)
    baseline_ap = fast_ap(b2["labels"], b2["probs"])

    results: dict[str, Any] = {"label": label, "windows": windows,
                               "tag": tag, "baseline_ap_b2": baseline_ap,
                               "rows": len(g1["labels"]),
                               "positives": int(sum(g1["labels"])),
                               "distinct_pairs": len(set(g1["pairs"])),
                               "distinct_positive_pairs": len(
                                   {pair for pair, y in zip(g1["pairs"], g1["labels"]) if y}),
                               "original_artifacts": {
                                   "predictions": str(original["path"]),
                                   "predictions_sha256": original["sha256"]},
                               "corrected_g2_artifact": (
                                   {"path": str(corrected["path"]),
                                    "sha256": corrected["sha256"],
                                    "corrections": corrected.get("corrections", {})}
                                   if corrected else None)}

    # pooled point estimates and both clusterings
    pooled: dict[str, Any] = {"company": pooled_bootstrap(g1, b2, "company",
                                                          resamples=resamples, seed=seed),
                              "pair": pooled_bootstrap(g1, b2, "pair",
                                                       resamples=resamples, seed=seed)}
    per_window: list[dict[str, Any]] = []
    window_collections: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for window in windows:
        a = _slice_collect(g1, window)
        b = _slice_collect(b2, window)
        window_collections[window] = (a, b)
        boot = pooled_bootstrap(a, b, "company", resamples=resamples, seed=seed)
        point = point_delta(a, b)
        per_window.append({"window": window, "rows": len(a["labels"]),
                           "positives": int(sum(a["labels"])),
                           "ap_g1": point["ap_a"], "ap_b2": point["ap_b"],
                           "delta": point["delta"],
                           "ci_low": boot["ci_low"], "ci_high": boot["ci_high"],
                           "se": boot["se"], "mde_80": boot["mde_80"],
                           "p_one_sided": boot["p_one_sided"],
                           "excludes_zero": boot["excludes_zero"]})

    # Monte-Carlo stability + independent variance estimator
    stability = {"company": seed_stability(g1, b2, "company", STABILITY_SEEDS),
                 "pair": seed_stability(g1, b2, "pair", STABILITY_SEEDS)}
    jackknife = {"company": jackknife_delta(g1, b2, "company"),
                 "pair": jackknife_delta(g1, b2, "pair")}

    # equal-weight mean-over-windows statistic: avoids triplicated-row weighting
    joint = joint_bootstrap(g1, b2, windows, resamples=resamples, seed=seed)
    joint_draws = np.asarray(joint["draws"], dtype=float)
    mean_window = {
        "observed_mean_delta": float(np.mean(joint["observed"][:-1])),
        "ci_low": float(np.quantile(joint_draws[:, :-1].mean(axis=1), 0.025)),
        "ci_high": float(np.quantile(joint_draws[:, :-1].mean(axis=1), 0.975)),
        "p_one_sided": float(np.mean(joint_draws[:, :-1].mean(axis=1) <= 0)),
        "draws": int(joint_draws.shape[0]),
        "note": "Equal weight per holdout window; avoids giving a company-track pair "
                "with 3 overlapping windows three times the row weight of a pair "
                "observed in one window."}

    # MDEs and power for the pooled company test
    company_draws = np.asarray(pooled["company"]["draws"], dtype=float)
    pair_draws = np.asarray(pooled["pair"]["draws"], dtype=float)
    mde_normal = pooled["company"]["mde_80"]
    quant = quantile_mde(company_draws, pooled["company"]["delta"])
    quant["mde"] = float(quant["mde"])
    quant["bootstrap_bias"] = float(company_draws.mean() - pooled["company"]["delta"])
    quant["skewness"] = _skew(company_draws)
    quant["power_at_reported_mde"] = power_at(mde_normal, company_draws,
                                              pooled["company"]["delta"])
    quant["power_at_quantile_mde"] = power_at(quant["mde"], company_draws,
                                              pooled["company"]["delta"])
    pair_quant = quantile_mde(pair_draws, pooled["pair"]["delta"])
    pair_quant["bootstrap_bias"] = float(pair_draws.mean() - pooled["pair"]["delta"])
    pair_quant["skewness"] = _skew(pair_draws)
    pair_quant["power_at_reported_mde"] = power_at(pooled["pair"]["mde_80"], pair_draws,
                                                   pooled["pair"]["delta"])

    mde: dict[str, Any] = {
        "reported_normal_formula": "mde_z * SE_bootstrap, mde_z = z_0.975 + z_0.80 = "
                                   f"{MDE_Z:.6f}",
        "company": {"se": pooled["company"]["se"], "mde_normal": mde_normal,
                    "relative_to_baseline_ap": mde_normal / baseline_ap if baseline_ap else None,
                    "mde_quantile": quant["mde"],
                    "power_at_reported_mde": quant["power_at_reported_mde"],
                    "bootstrap_bias": quant["bootstrap_bias"],
                    "skewness": quant["skewness"],
                    "q_025_centred": quant["q_025_centred"],
                    "q_20_centred": quant["q_20_centred"]},
        "pair": {"se": pooled["pair"]["se"], "mde_normal": pooled["pair"]["mde_80"],
                 "relative_to_baseline_ap": (pooled["pair"]["mde_80"] / baseline_ap
                                             if baseline_ap else None),
                 "mde_quantile": pair_quant["mde"],
                 "power_at_reported_mde": pair_quant["power_at_reported_mde"],
                 "bootstrap_bias": pair_quant["bootstrap_bias"],
                 "skewness": pair_quant["skewness"]},
    }

    rule_meta: dict[str, Any] = {}
    if power:
        rule_meta = rule_mde(joint, pooled["pair"]["se"], mde_normal, n_sim=80_000)
        rule_at_reported = rule_power(mde_normal, joint, pooled["pair"]["se"],
                                      mde_normal, n_sim=200_000)
        rule_meta["power_at_reported_mde"] = rule_at_reported
        mde["rule_level"] = {"mde_rule": rule_meta["mde_rule"],
                             "relative_to_baseline_ap": (rule_meta["mde_rule"] / baseline_ap
                                                         if baseline_ap else None),
                             "power_at_reported_mde": rule_at_reported["power"],
                             "power_components_at_reported_mde": rule_at_reported,
                             "note": "Power of the compound section-11 rule; covariance from "
                                     "the joint company-cluster bootstrap, pair-clustered "
                                     "pooled statistic assumed perfectly correlated. This "
                                     "is the power that matters for the pre-registered "
                                     "H1 verdict."}
    else:
        rule_meta = {"mde_rule": None, "power_at_reported_mde": {"power": None}}

    # multiplicity
    register = [(f"{label}:H1_G1_minus_B2_pooled_company",
                 pooled["company"]["p_one_sided"] or 1.0)]
    for row in per_window:
        register.append((f"{label}:H1_G1_minus_B2_{row['window']}",
                         row["p_one_sided"] if row["p_one_sided"] is not None else 1.0))
    p_values = [value for _, value in register]
    multiplicity = {
        "family_used_by_this_pipeline": [name for name, _ in register],
        "q": Q_FDR,
        "bh_stepup": bh_stepup(p_values, Q_FDR),
        "bh_pointwise_original_reproduction": bh_pointwise_buggy(p_values, Q_FDR),
        "n_rejections_stepup": sum(1 for row in bh_stepup(p_values, Q_FDR) if row["reject"]),
        "n_rejections_pointwise_original": sum(
            1 for row in bh_pointwise_buggy(p_values, Q_FDR) if row["reject"]),
        "note": "Pre-registration section 10.5 defines the family as H1 3 windows + "
                "pooled and H2 3 windows; the original script instead used 2 horizons x "
                "(pooled + 3 windows) = 8 H1 tests. Both families are reported here.",
    }

    # H2
    if corrected is not None:
        h2 = h2_from_corrected_g2(label, corrected, original)
    else:
        h2 = h2_from_original_g2(original)

    decision = corrected_decision(
        pooled, per_window,
        mde_quantile_company=quant["mde"], mde_rule=rule_meta.get("mde_rule"),
        rule_power_at_reported=rule_meta.get("power_at_reported_mde", {}).get("power"),
        baseline_ap=baseline_ap)

    results.update({"pooled": {unit: {key: value for key, value in block.items()
                                      if key != "draws"}
                               for unit, block in pooled.items()},
                    "per_window": per_window,
                    "mean_over_windows": mean_window,
                    "seed_stability": stability, "jackknife": jackknife,
                    "mde": mde, "rule_power": rule_meta,
                    "multiplicity": multiplicity, "h2": h2, "decision": decision})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizons", default="4,2")
    parser.add_argument("--tag", default="auto",
                        choices=("auto", "original", "g2", "g2_corrected"))
    parser.add_argument("--g2-model", default="N1",
                        choices=("N1", "N2", "both", "none"),
                        help="corrected-G2 null model to load; 'both' reports N1 and "
                             "N2, 'none' keeps the original invalidated-G2 behaviour")
    parser.add_argument("--out", default=None,
                        help="optional output path (relative paths resolve against the "
                             "study root); default artifacts/correction_round_1/"
                             "stats_corrected_<tag>.json")
    parser.add_argument("--resamples", type=int, default=RESAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--no-power", action="store_true",
                        help="skip the rule-level power simulation")
    args = parser.parse_args(argv)
    models = ([] if args.g2_model == "none"
              else (["N1", "N2"] if args.g2_model == "both" else [args.g2_model]))
    corrected_sets: dict[str, dict[str, dict[str, Any]]] = {}
    for quarters in [part.strip() for part in args.horizons.split(",") if part.strip()]:
        label = f"H{quarters}q"
        per_model: dict[str, dict[str, Any]] = {}
        for model in models:
            corrected = load_corrected_g2(label, model=model)
            if corrected is not None:
                per_model[model] = corrected
        if per_model:
            corrected_sets[label] = per_model
    tag = args.tag
    if tag == "auto":
        tag = "g2" if corrected_sets else "original"

    report: dict[str, Any] = {
        "study": "S-028", "pipeline": "s028_stats_corrected.py", "tag": tag,
        "g2_models_requested": models,
        "resamples": args.resamples, "seed": args.seed, "fdr_q": Q_FDR,
        "mde_z": MDE_Z, "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                         time.gmtime()),
        "provenance": {
            "original_g2": "original_buggy_g2" if not corrected_sets else "not used for H2",
            "corrected_g2_artifacts": {
                label: {model: {"path": str(corrected["path"]),
                                "sha256": corrected["sha256"]}
                        for model, corrected in per_model.items()}
                for label, per_model in corrected_sets.items()},
            "note": ("The original randomised null model is INVALIDATED as a method "
                     "claim (edge loss / broken bipartite degrees / collapsed weights). "
                     "H2 is re-derived here from the corrected-G2 artifacts only."),
        },
        "horizons": {},
    }
    for quarters in [part.strip() for part in args.horizons.split(",") if part.strip()]:
        label = f"H{quarters}q"
        print(f"[{tag}] analysing {label} ...", flush=True)
        started = time.time()
        per_model = corrected_sets.get(label, {})
        primary_model = next(iter(per_model), None)
        entry = analyse_horizon(label, tag, resamples=args.resamples, seed=args.seed,
                                power=not args.no_power,
                                corrected=per_model.get(primary_model))
        original = load_original(label)
        h2_by_model: dict[str, Any] = {}
        for model, corrected in per_model.items():
            h2_by_model[model] = h2_from_corrected_g2(label, corrected, original)
        if h2_by_model:
            entry["h2_by_model"] = h2_by_model
            entry["h2"] = h2_by_model[primary_model]
            entry["h2"]["primary_null_model"] = primary_model
        entry["seconds"] = round(time.time() - started, 1)
        report["horizons"][label] = entry
        company = entry["pooled"]["company"]
        print(f"  delta={company['delta']:.6f} company CI="
              f"[{company['ci_low']:.6f},{company['ci_high']:.6f}] "
              f"MDE_normal={company['mde_80']:.6f} "
              f"MDE_quantile={entry['mde']['company']['mde_quantile']:.6f} "
              f"MDE_rule={entry['mde']['rule_level'].get('mde_rule')} "
              f"literal={entry['decision']['literal_h1_status']}", flush=True)
        for model, h2 in h2_by_model.items():
            if h2.get("available"):
                print(f"  H2[{model}]: real={h2['real_pooled_ap']:.6f} "
                      f"null={h2['randomised_ap_min']:.6f}/"
                      f"{h2['randomised_ap_median']:.6f}/"
                      f"{h2['randomised_ap_max']:.6f} "
                      f"n_ge={h2['n_random_at_or_above_real']}/{h2['n_randomisations']} "
                      f"p_gt={h2['p_one_sided_real_gt_random']:.4f} "
                      f"q975={h2['randomised_ap_q975']:.6f} "
                      f"real_above_q975={h2['real_above_q975']}", flush=True)
        if not h2_by_model and entry["h2"].get("available"):
            print(f"  H2[original-buggy]: real={entry['h2']['real_pooled_ap']:.6f} "
                  f"p_gt={entry['h2']['p_one_sided_real_gt_random']:.4f} "
                  f"provenance={entry['h2'].get('provenance')}", flush=True)

    CORRECTION_DIR.mkdir(parents=True, exist_ok=True)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = STUDY / out
    else:
        out = CORRECTION_DIR / f"stats_corrected_{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True,
                              default=str) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
