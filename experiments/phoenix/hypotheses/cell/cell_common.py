"""PHOENIX-001 / T-CELL shared helpers (H1, H2, H4, H5, H10).

Nothing in here re-implements the frozen harness: panel construction, labels,
features, folds, metrics, bootstraps, models and Holm all come from
`experiments/phoenix/common/phoenix_common.py`. This module only

  * pins the frozen constants for the cell-level task (seed, B, lags),
  * declares the *feature sets* and *model arms* once so run_cell.py and
    audit_cell.py cannot drift apart,
  * adds the bipartite company x track network features that the protocol
    assigns to arm B7 (pure numpy, no new dependency),
  * provides provenance metadata (protocol version, db sha256, command, lag).

Frozen protocol: docs/phoenix/PHOENIX_FROZEN_PROTOCOL.md (phoenix-001/v1).
"""
from __future__ import annotations

import os
import pickle
import platform as _platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PHOENIX = HERE.parents[1]  # medradar/experiments/phoenix
sys.path.insert(0, str(PHOENIX / "common"))
import phoenix_common as pc  # noqa: E402

# --------------------------------------------------------------- frozen knobs
SEED = 20261108
B_BOOT = 1000
LAGS = (0, 90, 180)
HEADLINE_LAG = 90
LAG_SCENARIO = {0: "L000", 90: "L090", 180: "L180"}
ENT = ["company_key", "track_id"]

CACHE = HERE / "cache"
RESULTS = HERE / "results"
EVIDENCE = HERE / "evidence"
for _d in (CACHE, RESULTS, EVIDENCE):
    _d.mkdir(parents=True, exist_ok=True)

# The 10 columns that pc.add_history_features() emits per count column.
HIST_SUFFIX = ("_sum1", "_sum2", "_sum4", "_sum8", "_sum12", "_cum",
               "_mean4", "_std8", "_accel", "_log4")
# Own-history count columns carried through the harness feature builder.
OWN_COUNTS = ["f_n_device", "f_n_510k", "f_n_pma", "f_n_trial", "f_n_device_recall"]
# Context (enclosing track) count columns.
CTX_COUNTS = ["f_n_device", "f_n_510k", "f_n_pma", "f_n_trial", "f_n_device_recall"]

HOLDOUT_START = pd.Period("2022Q1", freq="Q")
BLOCKS = [(2014, 2016), (2017, 2019), (2020, 2022), (2023, 2025)]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- provenance
def _git_head() -> str | None:
    try:
        return (pc.REPO / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return None


def db_meta() -> dict:
    """Verify the frozen database once per process; abort on a hash mismatch."""
    v = pc.verify_db(check_hash=True)
    if not v.get("sha256_matches_frozen", False):
        raise SystemExit(
            f"FATAL: database sha256 does not match the frozen protocol value: {v}"
        )
    return v


def provenance(command: str, lag: int | None = None, db: dict | None = None) -> dict:
    db = db or db_meta()
    return {
        "protocol_version": pc.PROTOCOL_VERSION,
        "harness_version": pc.HARNESS_VERSION,
        "study": "PHOENIX-001",
        "task": "T-CELL",
        "hypotheses": ["H1", "H2", "H4", "H5", "H10"],
        "db_path": db["path"],
        "db_sha256": db["sha256"],
        "db_sha256_matches_frozen": bool(db["sha256_matches_frozen"]),
        "lag_days": (None if lag is None else int(lag)),
        "lag_scenario": (None if lag is None else LAG_SCENARIO[lag]),
        "command": command,
        "seed": SEED,
        "bootstrap_B": B_BOOT,
        "python": _platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "git_head": _git_head(),
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def provenance_ok(prov: dict, lag: int) -> bool:
    return (
        prov.get("protocol_version") == pc.PROTOCOL_VERSION
        and prov.get("lag_scenario") == LAG_SCENARIO[lag]
        and prov.get("seed") == SEED
        and prov.get("bootstrap_B") == B_BOOT
        and prov.get("db_sha256_matches_frozen") is True
    )


# ------------------------------------------------------------ network features
def add_network_features(
    panel: pd.DataFrame,
    entity_cols: list[str] = ENT,
    activity_col: str = "f_n_device_sum4",
    iters: int = 20,
    damping: float = 0.85,
) -> pd.DataFrame:
    """Bipartite company x track graph features for arm B7 (protocol §4).

    The graph at origin quarter q uses ONLY trailing information: an edge exists
    at q when the cell's device activity over the trailing 4 quarters
    (`f_n_device_sum4`, already on the lagged feature clock) is > 0. Nothing
    from q+1 onward enters the graph, so the same function can be applied once,
    globally, without leaking (proved by selftest.py).

    The PageRank node universe at q is the set of nodes that actually carry an
    edge at q (the active bipartite subgraph), with uniform teleport
    1/(|C_q| + |T_q|). That keeps the normalisation causal too: a fixed universe
    taken from the whole panel would let future entrants change today's score.
    Companies/tracks with no active edge at q get degree 0 and PageRank 0.

    Features per cell (company c, track r):
      net_company_degree             # active tracks of c
      net_company_weighted_degree    trailing-4q device activity of c (all tracks)
      net_track_degree               # active companies in r
      net_track_weighted_degree      trailing-4q device activity of r (all companies)
      net_pagerank_company           20-iteration power iteration, uniform teleport
      net_pagerank_track             same, track side
      net_jaccard_company_track_peers  Jaccard between c's track set and the union
                                     of track sets of the companies active in r
                                     (a same-node-type overlap; the literal
                                     "company set vs track set" Jaccard in the
                                     task brief is not defined on a bipartite
                                     graph, so this is the well-defined analogue
                                     and is labelled as such in the report)

    Pure numpy. No new dependency. ~5 ms per quarter.
    """
    companies = pd.Index(sorted(panel["company_key"].unique()))
    tracks = pd.Index(sorted(panel["track_id"].unique()))
    cpos = {c: i for i, c in enumerate(companies)}
    tpos = {t: j for j, t in enumerate(tracks)}
    n_c, n_t = len(companies), len(tracks)

    frames = []
    work = panel[entity_cols + ["quarter", activity_col]]
    for q, g in work.groupby("quarter", observed=True):
        cidx = g["company_key"].map(cpos).to_numpy(dtype=np.int64)
        tidx = g["track_id"].map(tpos).to_numpy(dtype=np.int64)
        val = g[activity_col].to_numpy(dtype=float)
        W = np.zeros((n_c, n_t), dtype=float)
        on = val > 0
        if on.any():
            W[cidx[on], tidx[on]] = val[on]
        A = (W > 0).astype(float)
        d_c = A.sum(axis=1)
        d_t = A.sum(axis=0)

        # ---- PageRank on the ACTIVE subgraph only (causal normalisation) ----
        p_c = np.zeros(n_c)
        p_t = np.zeros(n_t)
        c_act = np.flatnonzero(d_c > 0)
        t_act = np.flatnonzero(d_t > 0)
        n_act = len(c_act) + len(t_act)
        if n_act:
            A_sub = A[np.ix_(c_act, t_act)]
            dc_sub = A_sub.sum(axis=1)
            dt_sub = A_sub.sum(axis=0)
            inv_c = np.divide(1.0, dc_sub, out=np.zeros_like(dc_sub), where=dc_sub > 0)
            inv_t = np.divide(1.0, dt_sub, out=np.zeros_like(dt_sub), where=dt_sub > 0)
            tele = (1.0 - damping) / n_act
            pc_sub = np.full(len(c_act), 1.0 / n_act)
            pt_sub = np.full(len(t_act), 1.0 / n_act)
            for _ in range(iters):
                q_c = damping * (A_sub @ (pt_sub * inv_t)) + tele
                q_t = damping * (A_sub.T @ (pc_sub * inv_c)) + tele
                pc_sub, pt_sub = q_c, q_t
            p_c[c_act] = pc_sub
            p_t[t_act] = pt_sub

        # track-track co-membership: M[r, s] = 1 if some company is active in both
        M = (A.T @ A) > 0
        inter = np.einsum("ij,ij->i", A[cidx], M[tidx])
        uni = A[cidx].sum(axis=1) + M[tidx].sum(axis=1) - inter
        jac = np.divide(inter, uni, out=np.zeros_like(inter, dtype=float), where=uni > 0)
        fr = pd.DataFrame({
            "company_key": g["company_key"].to_numpy(),
            "track_id": g["track_id"].to_numpy(),
            "quarter": q,
            "net_company_degree": d_c[cidx],
            "net_company_weighted_degree": W[cidx].sum(axis=1),
            "net_track_degree": d_t[tidx],
            "net_track_weighted_degree": W[:, tidx].sum(axis=0),
            "net_jaccard_company_track_peers": jac,
            "net_pagerank_company": p_c[cidx],
            "net_pagerank_track": p_t[tidx],
        })
        frames.append(fr)
    net = pd.concat(frames, ignore_index=True)
    out = panel.merge(net, on=entity_cols + ["quarter"], how="left", validate="one_to_one")
    return out


NET_COLS = [
    "net_company_degree",
    "net_company_weighted_degree",
    "net_track_degree",
    "net_track_weighted_degree",
    "net_jaccard_company_track_peers",
    "net_pagerank_company",
    "net_pagerank_track",
]


# ------------------------------------------------------------------ panel build
def build_cell_panel(lag_days: int, events: pd.DataFrame | None = None,
                     origin_end: pd.Period | None = None,
                     verbose: bool = True) -> pd.DataFrame:
    """Frozen T-CELL panel at one lag scenario, including the B7 network block.

    Feature clock = available_at + lag_days   (harness handles it)
    Label  clock = event_date
    Label  = any {510k, pma} event in (q, q+4] for the (company_key, track_id) cell

    ORDERING NOTE (documented in the report, not a definition change):
    pc.build_joint_panel() trims the frame to `origin_end` *before* the caller can
    call pc.add_forward_target(), so the last HORIZON_Q origins come back with
    y = NaN. We therefore ask the harness to build out to `origin_end + 4` (its
    forward-window rows), attach the frozen label, and only then trim back to
    `origin_end`. Trailing-window features are computed after the trim, so they
    are identical either way (proved by selftest.py). The frozen-numbers check in
    build_panel.py asserts that restricting this panel to origins <= 2024Q2
    reproduces experiments/phoenix/reports/03_harness_smoke.json exactly
    (62,732 labelled rows / 12,517 positives / 19.953%).
    """
    if events is None:
        con = pc.connect_ro()
        try:
            events = pc.load_events(con)
        finally:
            con.close()
    oend = origin_end or pc.ORIGIN_END
    build_out = oend + pc.HORIZON_Q
    t0 = time.time()
    p = pc.build_joint_panel(events, ENT, kinds=pc.ALL_KINDS, lag_days=lag_days,
                             origin_end=build_out)
    if verbose:
        log(f"  build_joint_panel rows={len(p)} to {build_out} ({time.time()-t0:.1f}s)")
    p = pc.add_forward_target(p, ENT, value_col="n_device", horizon=pc.HORIZON_Q,
                              target="any_activity")
    p = p[p["quarter"] <= oend].copy()
    p = pc.add_history_features(p, ENT, OWN_COUNTS)
    if verbose:
        log(f"  add_history_features ({time.time()-t0:.1f}s)")
    p = pc.add_context_features(p, ENT, ["track_id"], CTX_COUNTS, windows=(4, 8))
    if verbose:
        log(f"  add_context_features ({time.time()-t0:.1f}s)")
    p = add_network_features(p)
    if verbose:
        log(f"  add_network_features ({time.time()-t0:.1f}s)")
    p["year"] = p["quarter"].dt.year
    p["qnum"] = p["quarter"].dt.quarter
    p["q1_only"] = p["qnum"] == 1
    p["holdout"] = p["quarter"] >= HOLDOUT_START
    log(f"  panel ready rows={len(p)} cols={p.shape[1]} ({time.time()-t0:.1f}s)")
    return p


# ------------------------------------------------------- feature sets / arms
def feature_sets(panel: pd.DataFrame) -> dict[str, list[str]]:
    """The frozen feature hierarchies for the cell task.

    f_n_device is the exact sum of f_n_510k + f_n_pma (harness line ~334) and
    f_n_8k_catalyst has essentially no coverage inside the 89-company universe;
    both are excluded from the model matrices. Everything else the harness
    produced is kept. `log_exposure` is a known-at-origin control.
    """
    cols = list(panel.columns)

    def hist(c: str) -> list[str]:
        return [c + s for s in HIST_SUFFIX if c + s in cols]

    own_dev = hist("f_n_device") + hist("f_n_510k") + hist("f_n_pma")
    trial = hist("f_n_trial")
    recall = hist("f_n_device_recall")
    ctx = [c for c in cols if c.startswith("ctx_")] + ["share_of_context"]
    ctx = [c for c in ctx if c in cols]
    net = [c for c in NET_COLS if c in cols]
    expo = ["log_exposure"]
    levels = [c for c in own_dev if not c.endswith("_accel")]
    return {
        # H1 baseline: own regulatory history only (no acceleration terms -> B2_levels adds them)
        "FEAT_B1_persistence": own_dev + expo,
        # H2 baseline: same columns minus the *_accel block
        "FEAT_B2_levels": levels + expo,
        # H5 arm: own device history + own trial history
        "FEAT_B1_plus_trial": own_dev + trial + expo,
        # all own features, no cross-entity context (used for the nested H4 test)
        "FEAT_B5_self": own_dev + trial + recall + expo,
        # B5 "all features" = own + enclosing-track context  (H4 arm)
        "FEAT_B5_context": own_dev + trial + recall + expo + ctx,
        # B7 = B5 feature set + network block
        "FEAT_B7_hgb_net": own_dev + trial + recall + expo + ctx + net,
    }


ARM_NAMES = [
    "B0_prevalence",
    "B1_persistence",
    "B2_levels",
    "B1_plus_trial",
    "B5_self",
    "B5_context",
    "B6_hgb",
    "B7_hgb_net",
]


def make_arm(name: str):
    if name == "B0_prevalence":
        return pc.ConstantBaseline()
    if name == "B6_hgb":
        return pc.GradientBoostingModel(name=name)
    if name == "B7_hgb_net":
        return pc.GradientBoostingModel(name=name)
    return pc.LogisticModel(name=name)


def arms(panel: pd.DataFrame) -> list[tuple[str, object, list[str]]]:
    """All model arms, each with the frozen feature set it is allowed to see."""
    fs = feature_sets(panel)
    spec = {
        "B0_prevalence": "FEAT_B5_context",      # constant score ignores X
        "B1_persistence": "FEAT_B1_persistence",
        "B2_levels": "FEAT_B2_levels",
        "B1_plus_trial": "FEAT_B1_plus_trial",
        "B5_self": "FEAT_B5_self",
        "B5_context": "FEAT_B5_context",
        "B6_hgb": "FEAT_B5_context",
        "B7_hgb_net": "FEAT_B7_hgb_net",
    }
    return [(n, make_arm(n), fs[spec[n]]) for n in ARM_NAMES]


# Hypothesis -> (arm A, arm B) primary contrast, A - B.
PRIMARY_CONTRASTS: dict[str, tuple[str, str]] = {
    "H1": ("B1_persistence", "B0_prevalence"),
    "H2": ("B1_persistence", "B2_levels"),
    "H4": ("B5_context", "B1_persistence"),
    "H5": ("B1_plus_trial", "B1_persistence"),
    "H10": ("B7_hgb_net", "B5_context"),
}
SECONDARY_CONTRASTS: dict[str, tuple[str, str]] = {
    "H4_nested": ("B5_context", "B5_self"),
    "H10_hgb": ("B6_hgb", "B5_context"),
}
# Pre-registered pass thresholds (protocol §6). H2 is one-sided.
THRESHOLDS = {"H1": 0.05, "H2": 0.02, "H4": 0.03, "H5": 0.02, "H10": 0.03}
REFUTATION_BAR = {"H1": 0.01, "H2": 0.01, "H4": 0.01, "H5": 0.01, "H10": 0.01}
FOLD_CONSISTENCY_REQUIRED = {"H1": 9, "H2": 9, "H4": 9, "H5": None, "H10": 9}


# --------------------------------------------------------------- cache helpers
def cache_path(lag: int) -> Path:
    return CACHE / f"cell_{LAG_SCENARIO[lag]}.pkl"


def meta_path() -> Path:
    return CACHE / "panel_meta.json"


def load_panel(lag: int) -> pd.DataFrame:
    p = cache_path(lag)
    if not p.exists():
        raise SystemExit(f"FATAL: cache missing: {p}\nRun: python build_panel.py --lag {lag}")
    with p.open("rb") as fh:
        panel = pickle.load(fh)
    return panel


def save_panel(panel: pd.DataFrame, lag: int) -> Path:
    p = cache_path(lag)
    with p.open("wb") as fh:
        pickle.dump(panel, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return p


def r6(x):
    """Round for JSON readability, keeping None/NaN explicit."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return x
    if not np.isfinite(v):
        return None
    return round(v, 6)
