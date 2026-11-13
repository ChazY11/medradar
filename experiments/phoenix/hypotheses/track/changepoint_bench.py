"""Stage 4 — H7 semi-synthetic change-point benchmark (protocol §6 H7).

One command:
    python experiments/phoenix/hypotheses/track/changepoint_bench.py [--reps 200]

Design, exactly as pre-registered:
  * 30 tracks with the most device events; real quarterly series 2004Q1..2025Q2 (86Q),
    taken from the frozen T-TRACK panel (label clock, company x track event set).
  * Step change injected at a uniformly random quarter tau ~ U[12, 74], multiplier
    m in {1.5, 2.0, 3.0} applied to a 4-quarter moving-average baseline of the real
    series. NOISE: negative binomial with a per-track size parameter estimated from
    the residuals to that 4Q moving average; Poisson fallback when that estimate is
    unstable (> 200 or non-positive excess variance). 200 replications per
    (track, m), plus matched no-change null series with the same tau draws.
  * Detectors: (a) fixed threshold, (b) standardised CUSUM k=0.5, (c) self-written
    PELT with a BIC-style penalty, (d) SciTrends-style 4Q growth threshold.
  * Every detector's threshold is TUNED ON THE NULL SERIES to the largest detection
    sensitivity subject to a false-alarm rate <= 5% per quarter, and then all
    detectors are compared at that matched budget. The protocol-literal operating
    points (k=2, growth>50%, CUSUM h=5, PELT lam=1.0) are also reported.
  * Detection = at least one alarm within +/-2 quarters of the true tau; delay =
    first such alarm minus tau.

HONEST LABEL: this is a controlled simulation. It proves detector properties under a
known ground truth. It is NOT evidence that the real medical-device series contain
detectable change points.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

import cp_methods as cp
import track_common as tc
import phoenix_common as pc

N_QUARTERS = 86
N_TRACKS = 30
MULTS = (1.5, 2.0, 3.0)
TAU_LO, TAU_HI = 12, 74
WIN = 2
FA_BUDGET = 0.05

FIXED_GRID = np.round(np.arange(1.20, 4.001, 0.05), 2)
CUSUM_H_GRID = np.round(np.arange(1.0, 12.01, 0.5), 2)
PELT_LAM_GRID = (0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3, 0.5, 0.8, 1.0, 1.2, 2.0)
GROWTH_GRID = np.round(np.arange(0.15, 3.001, 0.05), 2)

PROTOCOL_LITERAL = {"fixed": 2.0, "growth": 0.5, "cusum_h": 5.0, "pelt_lam": 1.0}


# ---------------------------------------------------------------- real series
def real_series(log: tc.RunLog) -> dict:
    panel = tc.ensure_panel(tc.HEADLINE_LAG, log)
    quarters = pc.quarter_range(pc.ORIGIN_START, pc.ORIGIN_END)
    qidx = {q: i for i, q in enumerate(quarters)}
    tot = panel.groupby("track_id", observed=True)["n_device"].sum().sort_values(ascending=False)
    top = list(tot.index[:N_TRACKS])
    mat = np.zeros((len(top), len(quarters)))
    for (tid, q), v in panel.groupby(["track_id", "quarter"], observed=True)["n_device"].sum().items():
        if tid in top:
            i = qidx.get(q)
            if i is not None:
                mat[top.index(tid), i] = float(v)
    per_track = {}
    for k, tid in enumerate(top):
        y = mat[k]
        per_track[tid] = {
            "total_device_events": int(y.sum()),
            "mean_per_quarter": float(y.mean()),
            "n_zero_quarters": int((y == 0).sum()),
            "first_nonzero_quarter": str(quarters[int(np.argmax(y > 0))]) if (y > 0).any() else None,
            "series": y,
        }
    return {"tracks": top, "quarters": quarters, "matrix": mat, "per_track": per_track}


# ------------------------------------------------------- overdispersion estimate
def estimate_nb_size(y: np.ndarray) -> dict:
    """Method of moments on residuals to a 4-quarter centred moving average.

    Var(y|mu) = mu + mu^2/r  =>  mean((y-mu)^2 - mu) = mean(mu^2)/r.
    A 4Q moving average absorbs part of the variance, so this r is biased UPWARD
    (i.e. towards less overdispersion) — a conservative choice for the benchmark.
    """
    mu = pd.Series(y).rolling(4, center=True, min_periods=1).mean().to_numpy()
    resid = y - mu
    excess = float(np.mean(resid**2 - mu))
    denom = float(np.mean(mu**2))
    if not np.isfinite(excess) or excess <= 1e-6 or denom <= 0:
        return {"r": float("inf"), "noise": "poisson", "excess": excess,
                "mu2_mean": denom, "reason": "non-positive or unstable excess variance"}
    r = denom / excess
    if not np.isfinite(r) or r > 200:
        return {"r": float("inf"), "noise": "poisson", "excess": excess,
                "mu2_mean": denom, "reason": f"estimated r={r:.1f} > 200 (near-Poisson)"}
    return {"r": float(r), "noise": "negbin", "excess": excess, "mu2_mean": denom,
            "reason": "method of moments"}


# ------------------------------------------------------------------- simulation
def simulate_track(y: np.ndarray, r: float, taus: np.ndarray, mult: float | None,
                   rng: np.random.Generator) -> np.ndarray:
    """Return an (86, n_reps) matrix of simulated series."""
    mu = pd.Series(y).rolling(4, center=True, min_periods=1).mean().to_numpy()
    n = len(mu)
    reps = len(taus)
    factor = np.ones((n, reps))
    if mult is not None:
        grid = np.arange(n)[:, None]
        factor = 1.0 + (mult - 1.0) * (grid >= taus[None, :])
    mean = mu[:, None] * factor
    if np.isfinite(r):
        p = r / (r + mean)
        return rng.negative_binomial(r, p)
    return rng.poisson(mean)


# -------------------------------------------------------------------- detectors
def run_fixed(series_list, k: float) -> list[list[int]]:
    out = []
    for y in series_list:
        ratio = cp.fixed_threshold_ratio(y)
        out.append(np.flatnonzero(ratio > k).tolist())
    return out


def run_growth(series_list, thr: float) -> list[list[int]]:
    out = []
    for y in series_list:
        g = cp.growth_rate(y)
        out.append(np.flatnonzero(g > thr).tolist())
    return out


def run_cusum(series_list, h: float, r: float, k: float = 0.5) -> list[list[int]]:
    return [cp.cusum_alarms(y, k=k, h=h, r=r) for y, r in zip(series_list, r)]


def run_pelt(series_list, lam: float, n: int = N_QUARTERS) -> list[list[int]]:
    pen = cp.pelt_penalty(lam, n)
    return [cp.pelt_cps(y, pen) for y in series_list]


def fa_rate(alarms_list, n_series: int) -> float:
    n_eval = N_QUARTERS - cp.EVAL_MIN
    total = sum(sum(1 for a in al if cp.EVAL_MIN <= a < N_QUARTERS) for al in alarms_list)
    return float(total / (n_series * n_eval))


def det_flags(alarms_list, taus) -> np.ndarray:
    flags = np.empty(len(alarms_list))
    for i, (al, tau) in enumerate(zip(alarms_list, taus)):
        d, _ = cp.detection_from_alarms(al, int(tau), win=WIN)
        flags[i] = 1.0 if d else 0.0
    return flags


def delays(alarms_list, taus) -> np.ndarray:
    out = np.full(len(alarms_list), np.nan)
    for i, (al, tau) in enumerate(zip(alarms_list, taus)):
        d, delay = cp.detection_from_alarms(al, int(tau), win=WIN)
        if d:
            out[i] = delay
    return out


def cluster_boot_diff(track_ids, d_a, d_b, B: int = tc.B_BOOT, seed: int = tc.SEED) -> dict:
    """Cluster (track) bootstrap for mean(d_a) - mean(d_b) on paired series."""
    track_ids = np.asarray(track_ids)
    d_a = np.asarray(d_a, float)
    d_b = np.asarray(d_b, float)
    uniq = np.unique(track_ids)
    idx_by = {g: np.flatnonzero(track_ids == g) for g in uniq}
    point = float(d_a.mean() - d_b.mean())
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[g] for g in pick])
        vals.append(float(d_a[idx].mean() - d_b[idx].mean()))
    vals = np.asarray(vals)
    lo, hi = np.quantile(vals, [0.025, 0.975])
    p = 2 * min((vals <= 0).mean(), (vals >= 0).mean())
    return {"diff": point, "lo": float(lo), "hi": float(hi), "p": float(min(1.0, p)),
            "B": B, "n_series": int(len(d_a)), "n_clusters": int(len(uniq))}


# ------------------------------------------------------------------------- main
def main(log: tc.RunLog, reps: int) -> int:
    t0 = time.time()
    db = tc.db_meta()
    if not db["db_sha256_matches_frozen"]:
        log.write("ABORT: db sha256 mismatch")
        return 2
    rng = np.random.default_rng(tc.SEED)

    rs = real_series(log)
    tracks, mat = rs["tracks"], rs["matrix"]
    log.step(f"top-{len(tracks)} tracks by device events: "
             f"{[int(rs['per_track'][t]['total_device_events']) for t in tracks[:8]]} ...")

    # ---- per-track noise model -------------------------------------------
    noise = {}
    r_vec = np.empty(len(tracks))
    for k, tid in enumerate(tracks):
        est = estimate_nb_size(mat[k])
        noise[tid] = {**est, "mean_per_quarter": float(mat[k].mean()),
                      "total_device_events": int(mat[k].sum())}
        r_vec[k] = est["r"]
    n_nb = int(np.isfinite(r_vec).sum())
    log.step(f"noise model: negbin for {n_nb}/{len(tracks)} tracks, "
             f"poisson fallback for {len(tracks) - n_nb}; "
             f"r median={'%.2f' % np.median(r_vec[np.isfinite(r_vec)]) if n_nb else 'n/a'}")

    # ---- simulate ---------------------------------------------------------
    taus_all = {tid: rng.integers(TAU_LO, TAU_HI + 1, size=reps) for tid in tracks}
    series_by_m: dict = {None: []}
    taus_by_m: dict = {None: []}
    track_by_m: dict = {None: []}
    for m in MULTS:
        series_by_m[m] = []
        taus_by_m[m] = []
        track_by_m[m] = []
    t1 = time.time()
    for k, tid in enumerate(tracks):
        r = r_vec[k]
        taus = taus_all[tid]
        for m in (None,) + MULTS:
            Y = simulate_track(mat[k], r, taus, m, rng)
            for j in range(reps):
                series_by_m[m].append(Y[:, j])
                taus_by_m[m].append(int(taus[j]))
                track_by_m[m].append(tid)
    n_null = len(series_by_m[None])
    n_change = sum(len(series_by_m[m]) for m in MULTS)
    log.step(f"simulated {n_null} null + {n_change} change series in {time.time()-t1:.1f}s")

    null_series = series_by_m[None]
    null_taus = np.asarray(taus_by_m[None])
    null_tracks = np.asarray(track_by_m[None])

    # ---- tune every detector on the null series --------------------------
    tuning: dict = {}

    # (a) fixed threshold
    ratios = [cp.fixed_threshold_ratio(y) for y in null_series]
    rows = []
    for k in FIXED_GRID:
        alarms = [np.flatnonzero(r > k).tolist() for r in ratios]
        fa = fa_rate(alarms, n_null)
        det = float(det_flags(alarms, null_taus).mean())
        rows.append({"k": float(k), "fa_rate_per_quarter": fa, "null_detection_within_2q": det})
    ok = [r for r in rows if r["fa_rate_per_quarter"] <= FA_BUDGET]
    chosen_fixed = ok[0] if ok else min(rows, key=lambda r: r["fa_rate_per_quarter"])
    tuning["fixed_threshold"] = {"grid": rows, "chosen": chosen_fixed}
    log.step(f"fixed tuned: k={chosen_fixed['k']} FA={chosen_fixed['fa_rate_per_quarter']:.4f} "
             f"null-det={chosen_fixed['null_detection_within_2q']:.3f}")

    # (b) growth
    grows = [cp.growth_rate(y) for y in null_series]
    rows = []
    for thr in GROWTH_GRID:
        alarms = [np.flatnonzero(g > thr).tolist() for g in grows]
        fa = fa_rate(alarms, n_null)
        det = float(det_flags(alarms, null_taus).mean())
        rows.append({"threshold": float(thr), "fa_rate_per_quarter": fa,
                     "null_detection_within_2q": det})
    ok = [r for r in rows if r["fa_rate_per_quarter"] <= FA_BUDGET]
    chosen_growth = ok[0] if ok else min(rows, key=lambda r: r["fa_rate_per_quarter"])
    tuning["growth_threshold"] = {"grid": rows, "chosen": chosen_growth}
    log.step(f"growth tuned: thr={chosen_growth['threshold']} "
             f"FA={chosen_growth['fa_rate_per_quarter']:.4f}")

    # (c) CUSUM
    rows = []
    r_null = [r_vec[tracks.index(t)] for t in null_tracks]
    cache_cusum = {}
    t1 = time.time()
    for h in CUSUM_H_GRID:
        alarms = run_cusum(null_series, float(h), r_null)
        cache_cusum[float(h)] = alarms
        rows.append({"h": float(h), "fa_rate_per_quarter": fa_rate(alarms, n_null),
                     "null_detection_within_2q": float(det_flags(alarms, null_taus).mean())})
    ok = [r for r in rows if r["fa_rate_per_quarter"] <= FA_BUDGET]
    chosen_cusum = ok[0] if ok else min(rows, key=lambda r: r["fa_rate_per_quarter"])
    tuning["cusum"] = {"grid": rows, "chosen": chosen_cusum, "k": 0.5}
    log.step(f"cusum tuned: h={chosen_cusum['h']} "
             f"FA={chosen_cusum['fa_rate_per_quarter']:.4f} ({time.time()-t1:.1f}s, "
             f"{len(CUSUM_H_GRID)} h values)")

    # (d) PELT
    rows = []
    pelt_cache = {}
    t1 = time.time()
    for lam in PELT_LAM_GRID:
        alarms = run_pelt(null_series, float(lam))
        pelt_cache[float(lam)] = alarms
        rows.append({"lam": float(lam), "penalty": cp.pelt_penalty(float(lam), N_QUARTERS),
                     "fa_rate_per_quarter": fa_rate(alarms, n_null),
                     "null_detection_within_2q": float(det_flags(alarms, null_taus).mean())})
    ok = [r for r in rows if r["fa_rate_per_quarter"] <= FA_BUDGET]
    chosen_pelt = ok[0] if ok else min(rows, key=lambda r: r["fa_rate_per_quarter"])
    tuning["pelt"] = {"grid": rows, "chosen": chosen_pelt}
    log.step(f"pelt tuned: lam={chosen_pelt['lam']} "
             f"FA={chosen_pelt['fa_rate_per_quarter']:.4f} ({time.time()-t1:.1f}s, "
             f"{len(PELT_LAM_GRID)} penalties)")

    # ---- evaluate on the injected-change series --------------------------
    results: dict = {}
    det_map: dict = {}
    tuned = {
        "fixed": float(chosen_fixed["k"]),
        "growth": float(chosen_growth["threshold"]),
        "cusum": float(chosen_cusum["h"]),
        "pelt": float(chosen_pelt["lam"]),
    }
    literal = {
        "fixed": float(PROTOCOL_LITERAL["fixed"]),
        "growth": float(PROTOCOL_LITERAL["growth"]),
        "cusum": float(PROTOCOL_LITERAL["cusum_h"]),
        "pelt": float(PROTOCOL_LITERAL["pelt_lam"]),
    }

    for label, params in (("matched_false_alarm_budget", tuned),
                          ("protocol_literal", literal)):
        results[label] = {}
        det_map[label] = {}
        for m in MULTS:
            sl = series_by_m[m]
            taus = np.asarray(taus_by_m[m])
            trk = np.asarray(track_by_m[m])
            r_s = [r_vec[tracks.index(t)] for t in trk]
            alarms = {
                "fixed": run_fixed(sl, params["fixed"]),
                "growth": run_growth(sl, params["growth"]),
                "cusum": run_cusum(sl, params["cusum"], r_s),
                "pelt": run_pelt(sl, params["pelt"]),
            }
            block = {}
            for name, al in alarms.items():
                fl = det_flags(al, taus)
                dl = delays(al, taus)
                block[name] = {
                    "detection_rate": float(fl.mean()),
                    "n_detected": int(fl.sum()),
                    "median_delay_q": float(np.nanmedian(dl)) if np.isfinite(dl).any() else None,
                    "iqr_delay_q": [float(np.nanquantile(dl, 0.25)), float(np.nanquantile(dl, 0.75))]
                    if np.isfinite(dl).any() else None,
                    "mean_alarms_per_series": float(np.mean([len(a) for a in al])),
                }
            results[label][f"m={m}"] = block
            det_map[label][f"m={m}"] = {name: det_flags(al, taus)
                                        for name, al in alarms.items()}
            log.step(f"{label} m={m}: " + " ".join(
                f"{n}={block[n]['detection_rate']:.3f}" for n in block))
        # pooled over the three multipliers (the pre-registered 18,000-repetition test)
        pooled_flags = {}
        pooled_tracks, pooled_taus = [], []
        for m in MULTS:
            pooled_tracks.append(np.asarray(track_by_m[m]))
            pooled_taus.append(np.asarray(taus_by_m[m]))
        pooled_tracks = np.concatenate(pooled_tracks)
        for name in ("fixed", "growth", "cusum", "pelt"):
            pooled_flags[name] = np.concatenate([det_map[label][f"m={m}"][name] for m in MULTS])
        results[label]["pooled"] = {
            name: {"detection_rate": float(pooled_flags[name].mean()),
                   "n_series": int(len(pooled_flags[name])),
                   "n_detected": int(pooled_flags[name].sum())}
            for name in pooled_flags
        }
        # bootstrap contrasts vs the fixed threshold
        contrasts = {}
        for name in ("cusum", "pelt", "growth"):
            contrasts[name] = cluster_boot_diff(
                pooled_tracks, pooled_flags[name], pooled_flags["fixed"], B=tc.B_BOOT,
                seed=tc.SEED)
        results[label]["pooled"]["contrasts_vs_fixed"] = contrasts
        log.step(f"{label} pooled: " + ", ".join(
            f"{n}={results[label]['pooled'][n]['detection_rate']:.3f}"
            for n in ("fixed", "growth", "cusum", "pelt")))
        log.step(f"{label} contrasts vs fixed: " + "; ".join(
            f"{n} {c['diff']:+.3f} [{c['lo']:+.3f},{c['hi']:+.3f}] p={c['p']:.4f}"
            for n, c in contrasts.items()))

    # ---- explicit table for the protocol-literal operating points ----------
    lit_key = {"fixed": "k", "growth": "threshold", "cusum": "h", "pelt": "lam"}
    lit_grid = {"fixed": tuning["fixed_threshold"], "growth": tuning["growth_threshold"],
                "cusum": tuning["cusum"], "pelt": tuning["pelt"]}
    literal_points = {}
    for name in ("fixed", "growth", "cusum", "pelt"):
        row = [r for r in lit_grid[name]["grid"]
               if abs(r[lit_key[name]] - literal[name]) < 1e-9]
        det = results["protocol_literal"]["pooled"][name]
        literal_points[name] = {
            "parameter": literal[name],
            "fa_rate_per_quarter": row[0]["fa_rate_per_quarter"] if row else None,
            "null_detection_within_2q": row[0]["null_detection_within_2q"] if row else None,
            "detection_rate_pooled": det["detection_rate"],
            "over_budget": bool(row and row[0]["fa_rate_per_quarter"] > FA_BUDGET),
        }

    # ---- detector quality by track size tercile (matched budget) ----------
    totals = np.array([rs["per_track"][t]["total_device_events"] for t in tracks])
    order = np.argsort(totals)
    terc = {}
    for name, sel in (("small", order[:10]), ("medium", order[10:20]), ("large", order[20:])):
        tset = {tracks[i] for i in sel}
        mask = np.array([t in tset for t in pool_track_of(MULTS, track_by_m)])
        terc[name] = {}
        for det_name in ("fixed", "growth", "cusum", "pelt"):
            flags = np.concatenate([det_map["matched_false_alarm_budget"][f"m={m}"][det_name]
                                    for m in MULTS])
            terc[name][det_name] = float(flags[mask].mean())

    # ---- verdict (protocol §6 H7, mechanical) ----------------------------
    matched = results["matched_false_alarm_budget"]
    pooled = matched["pooled"]
    cp_detectors = {n: pooled[n]["detection_rate"] for n in ("cusum", "pelt")}
    best_cp = max(cp_detectors, key=cp_detectors.get)
    cp_contrast = pooled["contrasts_vs_fixed"][best_cp]
    gain = cp_contrast["diff"]
    p = cp_contrast["p"]
    supported = bool(gain >= 0.10 and p < 0.05)
    verdict = "SUPPORTED" if supported else "NOT SUPPORTED"
    if gain >= 0.10 and not (p < 0.05):
        verdict = "INCONCLUSIVE"

    elapsed = round(log.elapsed(), 2)
    bench = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, n_null + n_change, n_change,
                         n_change / (n_null + n_change)),
        "hypothesis": "H7",
        "design": {
            "n_tracks": len(tracks),
            "tracks": tracks,
            "quarters": [str(rs["quarters"][0]), str(rs["quarters"][-1])],
            "n_quarters": N_QUARTERS,
            "multipliers": list(MULTS),
            "reps_per_track_per_multiplier": reps,
            "tau_range": [TAU_LO, TAU_HI],
            "detection_window_q": WIN,
            "eval_quarters": [cp.EVAL_MIN, N_QUARTERS - 1],
            "n_eval_quarters_per_series": N_QUARTERS - cp.EVAL_MIN,
            "noise_model": "negative binomial with per-track MLE-ish size r from 4Q-MA "
                           "residuals; Poisson fallback when unstable",
            "n_negbin_tracks": n_nb,
            "n_poisson_tracks": len(tracks) - n_nb,
            "baseline": "4-quarter centred moving average of the real series; the step "
                        "multiplier multiplies that baseline",
            "seeded": True,
        },
        "per_track_inputs": {t: {k: v for k, v in noise[t].items()} for t in tracks},
        "false_alarm_budget": FA_BUDGET,
        "tuning": tuning,
        "tuned_parameters": tuned,
        "protocol_literal_parameters": literal,
        "literal_operating_points": literal_points,
        "results": results,
        "detection_by_track_size_tercile_matched": terc,
        "null_floor_note": (
            "At a 5%/quarter false-alarm budget, a detector fires somewhere inside a "
            "5-quarter window by chance about 1-(1-0.05)^5 = 22.6% of the time. The "
            "measured 'null_detection_within_2q' of every tuned detector is therefore "
            "the correct floor against which detection rates must be read."
        ),
        "verdict_rule": "at least one change-point detector beats the fixed threshold by "
                        ">= 10 percentage points at the matched false-alarm budget, with a "
                        "cluster-bootstrap (by track) 95% CI excluding 0",
        "verdict": verdict,
        "best_cp_detector": best_cp,
        "best_cp_gain_vs_fixed": gain,
        "best_cp_contrast": cp_contrast,
        "honest_label": (
            "CONTROLLED SIMULATION. This proves detector properties under a known "
            "ground truth. It is NOT evidence that real medical-technology history "
            "contains detectable change points."
        ),
        "elapsed_sec": elapsed,
    }
    tc.save(bench, tc.RESULTS_DIR / "changepoint_bench.json")
    log.step("wrote changepoint_bench.json")

    card = {
        **tc.base_record(log, db, tc.HEADLINE_LAG, n_null + n_change, n_change,
                         n_change / (n_null + n_change)),
        "hypothesis": "H7",
        "title": "Is change-point detection better than a fixed threshold?",
        "pre_registered_definition": (
            "Semi-synthetic benchmark: 30 largest tracks, 86 quarters, step change "
            "m in {1.5,2,3} at a random quarter, 200 reps, matched false-alarm budget "
            "<= 5%/quarter, detection within +/-2 quarters. Supported iff at least one "
            "change-point detector beats the fixed threshold by >= 10pp with a "
            "bootstrap CI excluding 0."
        ),
        "n_series": n_null + n_change,
        "n_null_series": n_null,
        "n_change_series": n_change,
        "tuning_table": {
            name: {
                "chosen": v["chosen"],
                "n_grid_points": len(v["grid"]),
                "protocol_literal": (
                    {"k": PROTOCOL_LITERAL["fixed"]} if name == "fixed_threshold"
                    else {"threshold": PROTOCOL_LITERAL["growth"]} if name == "growth_threshold"
                    else {"h": PROTOCOL_LITERAL["cusum_h"]} if name == "cusum"
                    else {"lam": PROTOCOL_LITERAL["pelt_lam"]}
                ),
            } for name, v in tuning.items()
        },
        "matched_budget_detection": results["matched_false_alarm_budget"],
        "protocol_literal_detection": results["protocol_literal"],
        "null_floor_note": bench["null_floor_note"],
        "verdict": verdict,
        "evidence_class": "method research (controlled simulation) — NOT D/R/S evidence "
                          "about real historical change points",
        "elapsed_sec": elapsed,
    }
    tc.save(card, tc.RESULTS_DIR / "h7_changepoint.json")
    log.step(f"wrote h7_changepoint.json; H7 verdict={verdict} "
             f"(best {best_cp} gain={gain:+.3f} p={p:.4f}) total={elapsed}s")
    return 0


def pool_track_of(mults, track_by_m):
    return np.concatenate([np.asarray(track_by_m[m]) for m in mults])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    a = ap.parse_args()
    raise SystemExit(tc.run_script("04_changepoint_bench", lambda log: main(log, a.reps)))
