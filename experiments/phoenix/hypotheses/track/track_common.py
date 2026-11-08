"""Shared plumbing for the PHOENIX-001 TRACK-level experiments (H3/H6/H7/H8/H9).

This module does NOT modify `experiments/phoenix/common/phoenix_common.py`. It only
adds track-level feature builders (H8 growth features, B2 trend score), panel
caching, logging and small metric helpers on top of the frozen harness.

Everything here writes inside `experiments/phoenix/hypotheses/track/` only.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
import time
import traceback
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TRACK_DIR = HERE
COMMON_DIR = HERE.parents[1] / "common"
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

import phoenix_common as pc  # noqa: E402

REPO = pc.REPO
CACHE_DIR = HERE / "cache"
RESULTS_DIR = HERE / "results"
EVIDENCE_DIR = HERE / "evidence"
for _d in (CACHE_DIR, RESULTS_DIR, EVIDENCE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SEED = 20261108
B_BOOT = 1000
LAG_SCENARIOS = (0, 90, 180)
HEADLINE_LAG = 90
LAG_TAG = {0: "L000", 90: "L090", 180: "L180"}
ENTITY = ["track_id"]
REL_PREFIX = "experiments/phoenix/hypotheses/track"

# event kinds that carry a track_id at all (verified 2026-11-08 on the frozen DB):
# 510k, pma, device_recall, trial. 8k_catalyst and drug_approval have ZERO
# track_id, so no track-level feature can be built from them. See
# results/entrants_hhi_summary.json -> source_coverage.
TRACK_KINDS = ("510k", "pma", "device_recall", "trial")

# Feature-clock source columns that exist in the joint track panel.
SOURCE_COLS = {
    "dev": ["f_n_510k", "f_n_pma"],
    "trial": ["f_n_trial"],
    "recall": ["f_n_device_recall"],
    "8k": ["f_n_8k_catalyst"],
    "drug": ["f_n_drug_approval"],
}


# --------------------------------------------------------------------- logging
def command_line() -> str:
    return "python " + " ".join([Path(sys.argv[0]).name] + sys.argv[1:])


def _rel(p: Path | str) -> str:
    p = Path(p).resolve()
    try:
        return str(p.relative_to(REPO.resolve())).replace("\\", "/")
    except ValueError:
        return str(p)


class RunLog:
    """Tee stdout to evidence/<name>.log with wall-clock timestamps."""

    def __init__(self, name: str, extra_argv: str = ""):
        self.t0 = time.time()
        self.name = name
        self.path = EVIDENCE_DIR / f"{name}.log"
        self._fh = self.path.open("w", encoding="utf-8")
        self.write(f"# PHOENIX-001 track experiment log: {name}")
        self.write(f"# start: {datetime.now().astimezone().isoformat(timespec='seconds')}")
        self.write(f"# command: {command_line()}{(' ' + extra_argv) if extra_argv else ''}")
        self.write(f"# protocol: {pc.PROTOCOL_VERSION}  harness: {pc.HARNESS_VERSION}  seed: {SEED}")
        if extra_argv:
            self.extra_argv = extra_argv
        else:
            self.extra_argv = ""

    def write(self, msg: object = "") -> None:
        line = str(msg)
        print(line, flush=True)
        self._fh.write(line + "\n")
        self._fh.flush()

    def step(self, msg: object) -> None:
        self.write(f"[{time.time() - self.t0:8.2f}s] {msg}")

    def warn(self, msg: object) -> None:
        self.write(f"[{time.time() - self.t0:8.2f}s] WARNING: {msg}")

    def close(self, rc: int = 0) -> None:
        el = time.time() - self.t0
        self.write(f"# end: {datetime.now().astimezone().isoformat(timespec='seconds')}")
        self.write(f"# elapsed_sec: {el:.2f}  exit_code: {rc}")
        self._fh.close()

    def elapsed(self) -> float:
        return time.time() - self.t0


def run_script(name: str, fn):
    """Run fn(log) with a log file that captures warnings and tracebacks."""
    log = RunLog(name)
    _prev = warnings.showwarning

    def _show(message, category, filename, lineno, file=None, line=None):
        log.warn(f"{category.__name__}: {message} ({Path(filename).name}:{lineno})")

    warnings.showwarning = _show
    rc = 0
    try:
        rc = int(fn(log) or 0)
    except Exception:
        log.write("EXCEPTION:\n" + traceback.format_exc())
        log.close(rc=1)
        warnings.showwarning = _prev
        raise
    finally:
        warnings.showwarning = _prev
    log.close(rc=rc)
    return rc


# ------------------------------------------------------------------ provenance
def db_meta() -> dict:
    """Re-verify the frozen DB SHA-256 (protocol §1)."""
    v = pc.verify_db(check_hash=True)
    return {
        "db_path": _rel(v["path"]),
        "db_sha256": v.get("sha256", ""),
        "db_sha256_matches_frozen": bool(v.get("sha256_matches_frozen", False)),
        "db_size_bytes": v.get("size_bytes"),
        "db_integrity_check": v.get("integrity_check"),
    }


def base_record(log: RunLog, db: dict, lag: int, n: int, n_pos: int, prevalence: float) -> dict:
    return {
        "protocol_version": pc.PROTOCOL_VERSION,
        "harness_version": pc.HARNESS_VERSION,
        "db_sha256": db["db_sha256"],
        "db_sha256_matches_frozen": db["db_sha256_matches_frozen"],
        "lag_scenario": LAG_TAG.get(lag, f"L{lag:03d}"),
        "lag_days": int(lag),
        "command": command_line(),
        "elapsed_sec": round(log.elapsed(), 2),
        "seed": SEED,
        "n": int(n),
        "n_pos": int(n_pos),
        "prevalence": float(prevalence),
    }


# ------------------------------------------------------------------- H8 features
def add_growth_features(panel: pd.DataFrame, entity_cols: list[str]) -> pd.DataFrame:
    """SciTrends-style growth features (protocol §6 H8), independently implemented.

    All of them use only quarter q and earlier on the FEATURE clock:
      sct_growth{1,2,4,8}  (trailing w-quarter sum - previous w-quarter sum) / (previous + 1)
      sct_slope12          OLS slope of log1p(count) over the trailing 12 quarters
      sct_pma_share4       trailing-4Q PMA share of device events (high-barrier proxy)
      sct_volatility8      trailing-8Q std / (trailing-8Q mean + 1)
    """
    panel = panel.sort_values(entity_cols + ["quarter"]).copy()
    g = panel.groupby(entity_cols, observed=True)
    for w in (1, 2, 4, 8):
        cur = g["f_n_device"].transform(lambda s: s.rolling(w, min_periods=1).sum())
        prev = g["f_n_device"].transform(lambda s: s.shift(w).rolling(w, min_periods=1).sum())
        panel[f"sct_growth{w}"] = (cur - prev) / (prev + 1.0)
    # log-linear slope over trailing 12 quarters, per entity
    slope = np.full(len(panel), np.nan)
    x = np.arange(12.0)
    xc = x - x.mean()
    denom = float((xc**2).sum())
    for _, idx in panel.groupby(entity_cols, observed=True).indices.items():
        idx = np.sort(np.asarray(idx))
        v = panel["f_n_device"].to_numpy(dtype=float)[idx]
        for i in range(11, len(v)):
            seg = np.log1p(v[i - 11:i + 1])
            slope[idx[i]] = float((xc * seg).sum() / denom)
    panel["sct_slope12"] = slope
    pma4 = panel["f_n_pma_sum4"] if "f_n_pma_sum4" in panel else 0.0
    dev4 = panel.get("f_n_device_sum4", pd.Series(np.zeros(len(panel)), index=panel.index))
    panel["sct_pma_share4"] = np.asarray(pma4, dtype=float) / (np.asarray(dev4, dtype=float) + 1.0)
    panel["sct_volatility8"] = panel["f_n_device_std8"] / (panel["f_n_device_mean4"] + 1.0)
    return panel


def add_b2_trend_score(panel: pd.DataFrame, entity_cols: list[str]) -> pd.DataFrame:
    """B2 baseline score (protocol §4): 8Q mean + linear-trend extrapolation.

    score = max(0, forecast mean over the next 4 quarters) / (trailing 8Q mean + 1)
    where the forecast is an OLS line fitted on the trailing 8 quarters (incl. q)
    and evaluated at t+1..t+4 on the FEATURE clock.
    """
    panel = panel.sort_values(entity_cols + ["quarter"]).copy()
    out = np.full(len(panel), np.nan)
    for _, idx in panel.groupby(entity_cols, observed=True).indices.items():
        idx = np.sort(np.asarray(idx))
        v = panel["f_n_device"].to_numpy(dtype=float)[idx]
        for i in range(len(v)):
            w = v[max(0, i - 7):i + 1]
            if len(w) < 4:
                out[idx[i]] = v[i]
                continue
            x = np.arange(len(w), dtype=float)
            xc = x - x.mean()
            b = float((xc * (w - w.mean())).sum() / max((xc**2).sum(), 1e-9))
            a = w.mean()
            fwd = a + b * np.mean(np.arange(len(w), len(w) + 4, dtype=float))
            out[idx[i]] = max(fwd, 0.0) / (w.mean() + 1.0)
    panel["b2_trend_score"] = out
    return panel


# ----------------------------------------------------------------- panel build
GROWTH_HISTORY_COLS = ["f_n_510k", "f_n_pma", "f_n_trial", "f_n_device_recall",
                       "f_n_device", "f_n_total"]


def build_track_panel(events: pd.DataFrame, lag: int) -> pd.DataFrame:
    """Frozen T-TRACK panel at one lag scenario, with all track-level features."""
    panel = pc.build_joint_panel(events, ENTITY, lag_days=lag)
    panel = pc.add_forward_target(panel, ENTITY, value_col="n_device", target="growth")
    panel = pc.add_history_features(panel, ENTITY, GROWTH_HISTORY_COLS)
    panel = add_growth_features(panel, ENTITY)
    panel = add_b2_trend_score(panel, ENTITY)
    panel["lag_days"] = int(lag)
    return panel.sort_values(ENTITY + ["quarter"]).reset_index(drop=True)


def panel_path(lag: int) -> Path:
    return CACHE_DIR / f"track_panel_{LAG_TAG[lag]}.pkl"


def ensure_panel(lag: int, log: RunLog | None = None, force: bool = False) -> pd.DataFrame:
    p = panel_path(lag)
    if p.exists() and not force:
        if log:
            log.step(f"panel {LAG_TAG[lag]} <- cache {_rel(p)}")
        return pd.read_pickle(p)
    if log:
        log.step(f"panel {LAG_TAG[lag]} missing -> building from DB (slow path)")
    con = pc.connect_ro()
    try:
        ev = pc.load_events(con)
    finally:
        con.close()
    panel = build_track_panel(ev, lag)
    panel.to_pickle(p)
    return panel


# ------------------------------------------------------------ metric helpers
def alert_precision_topk(d: pd.DataFrame, score_col: str, k: int = 10) -> dict:
    """Protocol §5: precision at a fixed per-quarter alert budget of top-10 units."""
    d = d.dropna(subset=["y", score_col]).copy()
    if d.empty:
        return {"k": k, "mean_precision": float("nan"), "n_quarters": 0}
    precs = []
    for _, g in d.groupby("quarter", observed=True):
        s = g[score_col].to_numpy(dtype=float)
        y = g["y"].to_numpy(dtype=float)
        idx = np.argsort(-s)[: min(k, len(s))]
        if len(idx):
            precs.append(float(y[idx].mean()))
    precs = np.asarray(precs, dtype=float)
    return {
        "k": int(k),
        "mean_precision": float(precs.mean()) if len(precs) else float("nan"),
        "n_quarters": int(len(precs)),
        "base_rate_in_alerts": float(d["y"].mean()),
    }


BLOCKS = [(2014, 2016), (2017, 2019), (2020, 2022), (2023, 2025)]


def ap_by_block(d: pd.DataFrame, score_col: str) -> dict:
    out = {}
    yr = d["quarter"].astype(str).str.slice(0, 4).astype(int)
    for a, b in BLOCKS:
        sub = d[(yr >= a) & (yr <= b)]
        out[f"{a}-{b}"] = {
            "n": int(sub["y"].notna().sum()),
            "n_pos": int(np.nansum(sub["y"])),
            "ap": pc.average_precision(sub["y"].to_numpy(), sub[score_col].to_numpy()),
        }
    return out


def ap_by_track(d: pd.DataFrame, score_col: str, min_pos: int = 1) -> dict:
    out = {}
    for tid, g in d.groupby("track_id", observed=True):
        y = g["y"].to_numpy(dtype=float)
        if np.nansum(y) < min_pos:
            continue
        out[str(tid)] = {
            "n": int(np.isfinite(y).sum()),
            "n_pos": int(np.nansum(y)),
            "ap": pc.average_precision(y, g[score_col].to_numpy(dtype=float)),
        }
    return out


def summarize_track_ap(dist: dict) -> dict:
    vals = np.asarray([v["ap"] for v in dist.values() if np.isfinite(v["ap"])], dtype=float)
    if len(vals) == 0:
        return {"n_tracks": 0}
    return {
        "n_tracks": int(len(vals)),
        "mean": float(vals.mean()),
        "median": float(np.median(vals)),
        "p25": float(np.quantile(vals, 0.25)),
        "p75": float(np.quantile(vals, 0.75)),
        "min": float(vals.min()),
        "max": float(vals.max()),
        "share_tracks_ap_above_prevalence": float(
            np.mean(vals > 0.0)
        ),
    }


def metric_bundle(d: pd.DataFrame, score_col: str, name: str, groups="track_id") -> dict:
    """pc.evaluate + block CI + stability + alert budget for one arm."""
    y = d["y"].to_numpy(dtype=float)
    s = d[score_col].to_numpy(dtype=float)
    ev = pc.evaluate(y, s, name=name)
    point, lo, hi = pc.block_bootstrap_ci(y, s, d[groups].to_numpy(), B=B_BOOT, seed=SEED)
    ev["ap_ci95"] = [float(lo), float(hi)]
    ev["ap_boot_point"] = float(point)
    ev["ap_by_block"] = ap_by_block(d, score_col)
    dist = ap_by_track(d, score_col)
    ev["ap_by_track"] = dist
    ev["ap_by_track_summary"] = summarize_track_ap(dist)
    ev["alert_top10_per_quarter"] = alert_precision_topk(d, score_col, k=10)
    return ev


def q1_only(d: pd.DataFrame) -> pd.DataFrame:
    """Non-overlapping origin subset (L5 sensitivity): origins in Q1 only."""
    q = d["quarter"].astype(str)
    return d[q.str.endswith("Q1")]


# ------------------------------------------------- event-clock descriptive series
def event_clock_series(events: pd.DataFrame) -> dict:
    """Dense (track x quarter) series on the EVENT clock.

    DESCRIPTIVE ONLY — the T-ENTRANT / T-HHI association tests of protocol §6
    H3/H6 are retrospective temporal associations (evidence class R), so they use
    the actual event quarter, not the lagged feature clock. Never feed these back
    into a predictive model.
    """
    quarters = pc.quarter_range(pc.ORIGIN_START, pc.ORIGIN_END)
    qidx = {q: i for i, q in enumerate(quarters)}
    n = len(quarters)
    tracks = sorted(events["track_id"].dropna().unique())
    tix = {t: k for k, t in enumerate(tracks)}
    dev = np.zeros((len(tracks), n))
    ent = np.zeros((len(tracks), n))
    hhi = np.full((len(tracks), n), np.nan)
    first_i = np.full(len(tracks), n, dtype=int)
    dev_only = events[events["kind"].isin(pc.DEVICE_KINDS)]
    for (tid, q), k in dev_only.groupby(["track_id", "quarter"], observed=True).size().items():
        i = qidx.get(q)
        if i is not None and tid in tix:
            dev[tix[tid], i] = float(k)
    for (tid, q), k in events.groupby(["track_id", "quarter"], observed=True).size().items():
        i = qidx.get(q)
        if i is not None and tid in tix and i < first_i[tix[tid]]:
            first_i[tix[tid]] = i
    first = events.groupby(["track_id", "company_key"], observed=True)["quarter"].min()
    for (tid, c), q in first.items():
        i = qidx.get(q)
        if i is not None and tid in tix:
            ent[tix[tid], i] += 1.0
    g = events.groupby(["track_id", "quarter", "company_key"], observed=True).size()
    for (tid, q), ser in g.groupby(level=[0, 1]):
        i = qidx.get(q)
        if i is None or tid not in tix:
            continue
        cnt = ser.to_numpy(dtype=float)
        tot = cnt.sum()
        if tot > 0:
            hhi[tix[tid], i] = float(((cnt / tot) ** 2).sum())
    return {"tracks": tracks, "quarters": quarters, "dev": dev, "ent": ent,
            "hhi": hhi, "first_i": first_i, "qidx": qidx}


def _highpass_series(ent, dev, first_i, w=8):
    """Remove each track's own trailing-8Q mean from both series (within-track
    high-pass). This is the control for the calendar confound: company entry is
    front-loaded in the 89-company registry snapshot (1.38 entrants per track-quarter
    in 2004 vs 0.08-0.13 from 2015 on) while device volume rises over calendar time,
    so a raw pooled correlation mixes a genuine lead relation with that shared trend."""
    e = np.full_like(ent, np.nan, dtype=float)
    d = np.full_like(dev, np.nan, dtype=float)
    for t_i in range(ent.shape[0]):
        for a, out in ((ent, e), (dev, d)):
            x = a[t_i]
            c = np.concatenate(([0.0], np.cumsum(x)))
            m = np.empty_like(x)
            for t in range(len(x)):
                lo = max(0, t - w + 1)
                m[t] = (c[t + 1] - c[lo]) / (t + 1 - lo)
            out[t_i] = x - m
    return e, d


def h3_lead_correlations(series: dict, ks=(0, 1, 2, 3, 4), B: int = B_BOOT,
                         seed: int = SEED) -> dict:
    """corr(entrants_t, rate_{t+k}) with a circular-shift permutation null.

    Rate definitions, both from protocol §6 H3's "corr(entrants_t, rate_{t+1..t+4})":
      single : rate in quarter t+k (k = 0 .. 4)
      fwd4   : mean rate over t+k .. t+k+3 (k = 0 .. 4; k=0 is the contemporaneous check)

    Rows start one quarter AFTER the track's first observed quarter: every company
    present in that first quarter is by definition an "entrant", which would otherwise
    inject a large artificial entrant spike at the start of every track.

    Sensitivities (bootstrap CI only, no permutation):
      * including the first observed quarter
      * within-track high-passed series (calendar-confound control)
    """
    ent, dev, first_i, tracks = series["ent"], series["dev"], series["first_i"], series["tracks"]
    n = ent.shape[1]
    ntr = ent.shape[0]
    e_hp, d_hp = _highpass_series(ent, dev, first_i)

    def build(k: int, mode: str, skip: int = 1, hp: bool = False):
        e_src, d_src = (e_hp, d_hp) if hp else (ent, dev)
        xs, ys, gs = [], [], []
        for t_i in range(ntr):
            for i in range(first_i[t_i] + skip, n):
                if mode == "single":
                    j0, j1 = i + k, i + k
                else:
                    j0, j1 = i + k, i + k + 3
                if j1 > n - 1:
                    continue
                xs.append(e_src[t_i, i])
                ys.append(np.nanmean(d_src[t_i, j0:j1 + 1]))
                gs.append(tracks[t_i])
        return np.asarray(xs, float), np.asarray(ys, float), np.asarray(gs, object)

    shifts = list(range(8, max(9, n - 8)))
    out: dict = {}
    for mode in ("single", "fwd4"):
        out[mode] = {}
        for k in ks:
            x, y, g = build(k, mode)
            ci = cluster_bootstrap_spearman(x, y, g, B=B, seed=seed)
            perm = circular_shift_permutation(x, y, g, shifts, B=B, seed=seed + 1)
            out[mode][f"k{k}"] = {
                "spearman": ci["spearman"], "ci95": [ci["lo"], ci["hi"]],
                "p_boot": ci["p"], "p_perm": perm["p_perm"],
                "null_sd": perm.get("null_sd"), "n": ci["n"],
                "n_clusters": ci["n_clusters"],
            }
    for label, kwargs in (("sensitivity_including_first_quarter", {"skip": 0}),
                          ("sensitivity_within_track_highpass", {"hp": True})):
        out[label] = {}
        for mode in ("single", "fwd4"):
            out[label][mode] = {}
            for k in ks:
                x, y, g = build(k, mode, **kwargs)
                ci = cluster_bootstrap_spearman(x, y, g, B=B, seed=seed)
                out[label][mode][f"k{k}"] = {
                    "spearman": ci["spearman"], "ci95": [ci["lo"], ci["hi"]],
                    "p_boot": ci["p"], "n": ci["n"],
                }
    out["definition"] = {
        "entrants_t": "companies whose first-ever event in the track is in quarter t",
        "rate": "device (510k+pma) events per quarter; single = quarter t+k, "
                "fwd4 = mean over t+k..t+k+3",
        "permutation": "circular shift of each track's entrant series by 8..n-8 quarters",
    }
    return out


def h6_descriptive(series: dict, B: int = B_BOOT, seed: int = SEED) -> dict:
    """Protocol §6 H6 test 1: Spearman(dHHI_{t-4->t}, dHHI_{t->t+4}), cluster bootstrap.

    HHI is undefined in quarters with no events, so pairs are formed only where
    both the trailing and the forward 4Q HHI change are computable.
    """
    hhi, first_i, tracks = series["hhi"], series["first_i"], series["tracks"]
    n = hhi.shape[1]
    xs, ys, gs = [], [], []
    for t_i in range(hhi.shape[0]):
        for i in range(max(first_i[t_i], 4), n - 4):
            if not (np.isfinite(hhi[t_i, i]) and np.isfinite(hhi[t_i, i - 4])
                    and np.isfinite(hhi[t_i, i + 4])):
                continue
            xs.append(hhi[t_i, i] - hhi[t_i, i - 4])
            ys.append(hhi[t_i, i + 4] - hhi[t_i, i])
            gs.append(tracks[t_i])
    x, y, g = np.asarray(xs, float), np.asarray(ys, float), np.asarray(gs, object)
    ci = cluster_bootstrap_spearman(x, y, g, B=B, seed=seed)
    out = {
        "test": "H6 test 1 (descriptive association)",
        "spearman": ci["spearman"], "ci95": [ci["lo"], ci["hi"]],
        "p_boot": ci["p"], "n_pairs": ci["n"], "n_clusters": ci["n_clusters"],
        "ci_excludes_zero": bool(np.isfinite(ci["lo"]) and (ci["lo"] > 0 or ci["hi"] < 0)),
        "definition": "dHHI_{t-4->t} vs dHHI_{t->t+4}, single-quarter event-share HHI, "
                      "company_key non-null events, within track",
    }
    # sensitivity: 8-quarter window and device-only HHI are reported with the same shape
    for w, label in ((8, "w8"),):
        xs, ys = [], []
        for t_i in range(hhi.shape[0]):
            for i in range(max(first_i[t_i], w), n - w):
                if not (np.isfinite(hhi[t_i, i]) and np.isfinite(hhi[t_i, i - w])
                        and np.isfinite(hhi[t_i, i + w])):
                    continue
                xs.append(hhi[t_i, i] - hhi[t_i, i - w])
                ys.append(hhi[t_i, i + w] - hhi[t_i, i])
        out[f"sensitivity_{label}_spearman"] = spearman(xs, ys)
        out[f"sensitivity_{label}_n"] = len(xs)
    return out


# ------------------------------------------------------- descriptive helpers
def spearman(x, y) -> float:
    from scipy.stats import spearmanr


    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 5:
        return float("nan")
    return float(spearmanr(x[ok], y[ok]).statistic)


def cluster_bootstrap_spearman(x, y, groups, B: int = B_BOOT, seed: int = SEED) -> dict:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    groups = np.asarray(groups)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y, groups = x[ok], y[ok], groups[ok]
    point = spearman(x, y)
    uniq = np.unique(groups)
    idx_by = {g: np.flatnonzero(groups == g) for g in uniq}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by[g] for g in pick])
        v = spearman(x[idx], y[idx])
        if np.isfinite(v):
            vals.append(v)
    vals = np.asarray(vals)
    if len(vals) < 20:
        return {"spearman": point, "lo": float("nan"), "hi": float("nan"), "p": float("nan"),
                "n": int(ok.sum()), "n_clusters": int(len(uniq))}
    lo, hi = np.quantile(vals, [0.025, 0.975])
    p = 2 * min((vals <= 0).mean(), (vals >= 0).mean())
    return {"spearman": point, "lo": float(lo), "hi": float(hi), "p": float(min(1.0, p)),
            "n": int(ok.sum()), "n_clusters": int(len(uniq)), "B": B}


def circular_shift_permutation(x, y, groups, shifts, B: int = B_BOOT, seed: int = SEED) -> dict:
    """Permutation null that respects within-track autocorrelation.

    Each cluster's x-series is circularly shifted by one random offset drawn from
    `shifts` (in quarter units); the pooled Spearman is recomputed.
    `x, y, groups` must be aligned to a dense within-track quarter ordering.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    groups = np.asarray(groups)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y, groups = x[ok], y[ok], groups[ok]
    point = spearman(x, y)
    uniq = np.unique(groups)
    idx_by = {g: np.flatnonzero(groups == g) for g in uniq}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        xs = x.copy()
        for g in uniq:
            idx = idx_by[g]
            off = int(rng.choice(shifts))
            xs[idx] = np.roll(x[idx], off)
        v = spearman(xs, y)
        if np.isfinite(v):
            vals.append(v)
    vals = np.asarray(vals)
    if len(vals) < 20:
        return {"spearman": point, "p_perm": float("nan"), "null_sd": float("nan"), "B": B}
    p = float(np.mean(np.abs(vals) >= abs(point)))
    return {"spearman": point, "p_perm": p, "null_mean": float(vals.mean()),
            "null_sd": float(vals.std(ddof=1)), "B": B, "n": int(ok.sum())}


# --------------------------------------------------------------- misc utilities
def df_to_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def _sanitize(o):
    """Recursively make a result object strict-JSON-safe (NaN/Inf -> null)."""
    if isinstance(o, dict):
        return {str(k): _sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sanitize(v) for v in o]
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, (int, np.integer)) and not isinstance(o, bool):
        return int(o)
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _sanitize(o.tolist())
    return o


def save(obj, path: Path) -> Path:
    pc.save_json(_sanitize(obj), path)
    return path


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with Path(p).open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
