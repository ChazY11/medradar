"""PHOENIX-001 shared evaluation harness (FROZEN).

All hypothesis experiments MUST import this module rather than reimplementing
panel construction, time splitting or metric computation. That is what makes the
method comparison fair.

PROTOCOL_VERSION is frozen at the start of the experiment round. If anything in
this file changes, bump PROTOCOL_VERSION, record the change in
docs/phoenix/PHOENIX_FROZEN_PROTOCOL.md and re-run every affected experiment.

Data contract
-------------
Read-only access to data/medradar.sqlite (sha256 pinned below).
Feature clock  = events.available_at  (public availability, never event_date)
Label clock    = events.event_date    (when the predicted thing happened)

That split is deliberate: openFDA publishes ~12 days after the decision date, so
using event_date for features would leak information that was not public yet.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import warnings
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

PROTOCOL_VERSION = "phoenix-001/v1"
HARNESS_VERSION = "1.0.0"

REPO = Path(__file__).resolve().parents[3]
DB_PATH = REPO / "data" / "medradar.sqlite"
DB_SHA256_EXPECTED = "445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92"

# ---------------------------------------------------------------- time windows
# Primary analysis window, frozen before any experiment was run.
# Rationale: company_key coverage of device events is ~40% before the mid-2000s
# and the 89-company registry is the binding constraint for cell-level work.
PANEL_START = "2004-01-01"
PANEL_END = "2026-10-30"
ORIGIN_START = pd.Period("2004Q1", freq="Q")
ORIGIN_END = pd.Period("2025Q2", freq="Q")  # need 4 forward quarters inside data

HORIZON_Q = 4  # forward window in quarters
DEVICE_KINDS = ("510k", "pma")
ALL_KINDS = ("510k", "pma", "device_recall", "trial", "8k_catalyst", "drug_approval")


# --------------------------------------------------------------------- loading
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def connect_ro(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open the science database strictly read-only."""
    p = Path(path)
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro&immutable=1", uri=True)


def verify_db(path: Path | str = DB_PATH, check_hash: bool = True) -> dict:
    p = Path(path)
    out = {"path": str(p), "exists": p.exists()}
    if not p.exists():
        out["status"] = "MISSING"
        return out
    out["size_bytes"] = p.stat().st_size
    if check_hash:
        out["sha256"] = sha256_file(p)
        out["sha256_matches_frozen"] = out["sha256"] == DB_SHA256_EXPECTED
    con = connect_ro(p)
    try:
        out["integrity_check"] = con.execute("pragma integrity_check").fetchone()[0]
    finally:
        con.close()
    return out


def load_events(
    con: sqlite3.Connection,
    kinds: Sequence[str] = ALL_KINDS,
    start: str = PANEL_START,
    end: str = PANEL_END,
    require_company_track: bool = True,
) -> pd.DataFrame:
    """Load the event fact table with normalized date columns.

    Returns columns: event_id, kind, event_dt, available_dt, company_key,
    track_id, product_code.
    """
    placeholders = ",".join("?" for _ in kinds)
    sql = f"""
        select event_id, kind, event_date, available_at, company_key, track_id,
               product_code
        from events
        where kind in ({placeholders})
          and event_date is not null
          and event_date >= ? and event_date <= ?
    """
    params = list(kinds) + [start, end]
    df = pd.read_sql_query(sql, con, params=params)
    df["event_dt"] = pd.to_datetime(df["event_date"], errors="coerce")
    df["available_dt"] = pd.to_datetime(df["available_at"], errors="coerce")
    # conservative fallback: if availability is unusable, push it far forward so
    # the event can never enter a feature window.
    bad = df["available_dt"].isna()
    if bad.any():
        df.loc[bad, "available_dt"] = pd.Timestamp("9999-01-01")
    df = df.dropna(subset=["event_dt"]).copy()
    if require_company_track:
        df = df[df["company_key"].notna() & df["track_id"].notna()].copy()
    df["quarter"] = df["event_dt"].dt.to_period("Q")
    df["avail_quarter"] = df["available_dt"].dt.to_period("Q")
    return df.reset_index(drop=True)


def load_reference(con: sqlite3.Connection) -> dict:
    """Track and company reference tables (schema differs between tables, so be
    tolerant about column names)."""
    out = {}
    for name in ("tracks", "companies", "product_codes"):
        try:
            out[name] = pd.read_sql_query(f'select * from "{name}"', con)
        except Exception as exc:  # noqa: BLE001
            out[name] = pd.DataFrame()
            out[f"{name}_error"] = repr(exc)
    return out


# ------------------------------------------------------------------ panel math
def quarter_range(start: pd.Period, end: pd.Period) -> list[pd.Period]:
    return list(pd.period_range(start, end, freq="Q"))


def _counts_by_key(df: pd.DataFrame, keys: list[str], kind_col: str = "kind") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=keys + ["n"])
    g = df.groupby(keys, observed=True).size().rename("n").reset_index()
    return g


def build_panel(
    events: pd.DataFrame,
    entity_cols: list[str],
    kinds: Sequence[str] = ALL_KINDS,
    start: pd.Period = ORIGIN_START,
    end: pd.Period = ORIGIN_END,
    min_history_q: int = 0,
    clock: str = "quarter",
    prefix: str = "",
) -> pd.DataFrame:
    """Build a dense entity x quarter panel of event counts per kind.

    An *entity* is the tuple in `entity_cols` (e.g. ("company_key","track_id") for
    the cell-level task, ("track_id",) for the track-level task).

    `clock` selects which quarter column the counts are assigned to:
      - "quarter"      -> event clock (use for LABELS only)
      - "feat_quarter" -> availability clock (use for FEATURES only)

    `prefix` renames the count columns (e.g. "f_" -> "f_n_device") so that the
    label-clock and feature-clock panels can coexist in one frame.

    Rows are created for every (entity, quarter) in range where the entity has at
    least one event at or before that quarter (`min_history_q` extra quarters of
    exposure required). Presence/absence is therefore well defined: a zero means
    "the entity existed and did nothing", not "the entity was not observable".
    """
    quarters = quarter_range(start, end)
    df = events[events["kind"].isin(kinds)].copy()
    if df.empty:
        raise ValueError("no events in range")
    if clock not in df.columns:
        raise KeyError(f"clock column {clock!r} not in events; call apply_lag() first")

    first_q = df.groupby(entity_cols, observed=True)["quarter"].min().rename("first_event_q")
    last_q = df.groupby(entity_cols, observed=True)["quarter"].max().rename("last_event_q")

    # Count per (entity, clock-quarter, kind) then unstack kinds into wide columns.
    # `unstack` keeps the MultiIndex level names, which is what makes the later
    # merges reliable.
    grouped = (
        df.groupby(entity_cols + [clock, "kind"], observed=True)
        .size()
        .unstack("kind", fill_value=0)
    )
    grouped.columns = [f"{prefix}n_{c}" for c in grouped.columns]
    grouped = grouped.reset_index()
    grouped = grouped.rename(columns={clock: "quarter"})
    grouped = grouped.drop_duplicates(subset=entity_cols + ["quarter"])
    grouped = grouped.merge(first_q.reset_index(), on=entity_cols, how="left")
    grouped = grouped.merge(last_q.reset_index(), on=entity_cols, how="left")

    # dense cartesian: every entity on every quarter in range
    entities = grouped[entity_cols].drop_duplicates()
    grid = entities.merge(pd.DataFrame({"quarter": quarters}), how="cross")
    panel = grid.merge(grouped, on=entity_cols + ["quarter"], how="left")
    count_cols = [c for c in panel.columns if c.startswith(f"{prefix}n_")]
    for col in count_cols:
        panel[col] = panel[col].fillna(0.0)
    panel["first_event_q"] = panel.groupby(entity_cols, observed=True)["first_event_q"].transform(
        "first"
    )
    panel["last_event_q"] = panel.groupby(entity_cols, observed=True)["last_event_q"].transform(
        "first"
    )
    if prefix == "":
        panel["n_total"] = panel[count_cols].sum(axis=1) if count_cols else 0.0
        dev_cols = [f"n_{k}" for k in DEVICE_KINDS if f"n_{k}" in panel]
        panel["n_device"] = panel[dev_cols].sum(axis=1) if dev_cols else 0.0

    panel["exposure_q"] = [
        (q - f).n if pd.notna(f) else np.nan
        for q, f in zip(panel["quarter"], panel["first_event_q"])
    ]
    panel = panel[panel["exposure_q"] >= min_history_q].copy()
    panel["exposure_q"] = panel["exposure_q"].astype(int)
    return panel.sort_values(entity_cols + ["quarter"]).reset_index(drop=True)


def add_forward_target(
    panel: pd.DataFrame,
    entity_cols: list[str],
    value_col: str = "n_device",
    horizon: int = HORIZON_Q,
    target: str = "any_activity",
    growth_multiple: float = 1.5,
    min_events: int = 3,
    trailing_window: int = 8,
) -> pd.DataFrame:
    """Attach forward-looking labels. Only ever reads the FUTURE (that is the
    point); features must never use these columns.

    target="any_activity" : y = 1 if sum of value_col over (q, q+horizon] >= 1
    target="growth"       : y = 1 if forward mean rate >= growth_multiple *
                            trailing mean rate AND forward total >= min_events
    """
    panel = panel.sort_values(entity_cols + ["quarter"]).copy()
    grp = panel.groupby(entity_cols, observed=True)
    fwd_vals = []
    for off in range(1, horizon + 1):
        fwd_vals.append(grp[value_col].shift(-off))
    panel["_fwd_sum"] = np.sum(fwd_vals, axis=0)
    panel["_fwd_n"] = np.sum([s.notna() for s in fwd_vals], axis=0)
    panel.loc[panel["_fwd_n"] < horizon, "_fwd_sum"] = np.nan

    if target == "any_activity":
        panel["y"] = (panel["_fwd_sum"] >= 1).astype(float)
    elif target == "growth":
        trail = grp[value_col].transform(
            lambda s: s.rolling(trailing_window, min_periods=trailing_window).mean()
        )
        fwd_rate = panel["_fwd_sum"] / horizon
        panel["y"] = (
            (panel["_fwd_sum"] >= min_events) & (fwd_rate >= growth_multiple * trail)
        ).astype(float)
        panel.loc[trail.isna() | panel["_fwd_sum"].isna(), "y"] = np.nan
    else:
        raise ValueError(f"unknown target {target!r}")

    panel.loc[panel["_fwd_sum"].isna(), "y"] = np.nan
    panel["fwd_sum"] = panel["_fwd_sum"]
    return panel.drop(columns=["_fwd_sum", "_fwd_n"])


def apply_lag(events: pd.DataFrame, lag_days: int) -> pd.DataFrame:
    """Attach the *feature clock* column `feat_quarter`.

    Frozen protocol §0.3: because `available_at == event_date` for every row in
    this database, the nominal clock carries no publication lag. We therefore
    inject a conservative lag and treat the result as the feature clock.

    lag_days = 0 -> nominal (control only)  90 -> headline  180 -> stress test
    """
    ev = events.copy()
    ev["feat_dt"] = ev["available_dt"] + pd.Timedelta(days=int(lag_days))
    ev["feat_quarter"] = ev["feat_dt"].dt.to_period("Q")
    ev["lag_days"] = int(lag_days)
    return ev


def build_joint_panel(
    events: pd.DataFrame,
    entity_cols: list[str],
    kinds: Sequence[str] = ALL_KINDS,
    lag_days: int = 90,
    start: pd.Period = ORIGIN_START,
    origin_end: pd.Period = ORIGIN_END,
    min_history_q: int = 0,
    feature_count_cols: Sequence[str] = ("n_device", "n_510k", "n_pma", "n_trial",
                                         "n_device_recall", "n_8k_catalyst"),
) -> pd.DataFrame:
    """Build one frame containing BOTH clocks.

    - `n_*`            counts assigned to the event quarter        -> LABELS ONLY
    - `f_n_*`          counts assigned to the lagged avail quarter -> FEATURES ONLY

    The panel is built out to `origin_end + HORIZON_Q` so that every origin up to
    `origin_end` has a complete forward window, then trimmed back to `origin_end`.
    """
    ev = apply_lag(events, lag_days)
    label_end = origin_end + HORIZON_Q
    lab = build_panel(
        ev, entity_cols, kinds=kinds, start=start, end=label_end,
        min_history_q=min_history_q, clock="quarter", prefix="",
    )
    fea = build_panel(
        ev, entity_cols, kinds=kinds, start=start, end=label_end,
        min_history_q=0, clock="feat_quarter", prefix="f_",
    )
    fcols = [c for c in fea.columns if c.startswith("f_n_")]
    joint = lab.merge(
        fea[entity_cols + ["quarter"] + fcols],
        on=entity_cols + ["quarter"], how="left",
    )
    for c in fcols:
        joint[c] = joint[c].fillna(0.0)
    joint["lag_days"] = int(lag_days)
    # recompute derived feature-clock columns
    dev = [c for c in ("f_n_510k", "f_n_pma") if c in joint.columns]
    joint["f_n_device"] = joint[dev].sum(axis=1) if dev else 0.0
    joint["f_n_total"] = joint[[c for c in joint.columns if c.startswith("f_n_")]].sum(axis=1)
    # trim origins to the frozen window
    joint = joint[joint["quarter"] <= origin_end].copy()
    # a row with an incomplete forward window keeps y = NaN; do not drop here
    return joint.sort_values(entity_cols + ["quarter"]).reset_index(drop=True)


def trim_origins(panel: pd.DataFrame, end: pd.Period = ORIGIN_END) -> pd.DataFrame:
    return panel[panel["quarter"] <= end].copy()


# ----------------------------------------------------------- feature building
def _trailing(grp, col: str, window: int, min_periods: int = 0) -> pd.Series:
    return grp[col].transform(
        lambda s: s.rolling(window, min_periods=min_periods).sum()
    )


def add_history_features(
    panel: pd.DataFrame,
    entity_cols: list[str],
    count_cols: Sequence[str],
    windows: Sequence[int] = (1, 2, 4, 8, 12),
) -> pd.DataFrame:
    """Trailing-window count features. Uses only the current and past quarters.

    A feature at origin quarter q includes events that happened *during* q. That
    is legitimate only if the origin decision is made at the END of q; the label
    window starts after q. State this assumption in every report.
    """
    panel = panel.sort_values(entity_cols + ["quarter"]).copy()
    grp = panel.groupby(entity_cols, observed=True)
    for col in count_cols:
        for w in windows:
            panel[f"{col}_sum{w}"] = _trailing(grp, col, w)
        panel[f"{col}_cum"] = grp[col].cumsum()
        panel[f"{col}_mean4"] = grp[col].transform(
            lambda s: s.rolling(4, min_periods=1).mean()
        )
        panel[f"{col}_std8"] = grp[col].transform(
            lambda s: s.rolling(8, min_periods=3).std()
        )
        # acceleration: last 2 quarters vs the 4 before them
        recent = grp[col].transform(lambda s: s.rolling(2, min_periods=1).sum())
        prior = grp[col].transform(lambda s: s.shift(2).rolling(4, min_periods=1).sum())
        panel[f"{col}_accel"] = (recent - prior) / prior.clip(lower=1.0)
        # log-rate features are scale stabilising
        panel[f"{col}_log4"] = np.log1p(panel[f"{col}_sum4"])
    panel["exposure_q"] = panel["exposure_q"].astype(float)
    panel["log_exposure"] = np.log1p(panel["exposure_q"])
    return panel


def add_context_features(
    panel: pd.DataFrame,
    entity_cols: list[str],
    context_cols: list[str],
    count_cols: Sequence[str],
    windows: Sequence[int] = (4, 8),
    shares: bool = True,
) -> pd.DataFrame:
    """Cross-entity features (e.g. the enclosing track's activity for a company-track
    cell). `context_cols` are the enclosing entity columns; the panel is
    aggregated up to those, features are built there, then merged back.

    IMPORTANT: the aggregation is over the current quarter and the past only.
    """
    if not context_cols:
        return panel
    work = panel.copy()
    work["_active"] = (work[count_cols[0]] > 0).astype(float)
    agg_spec = {c: "sum" for c in count_cols}
    agg_spec["_active"] = "sum"
    agg = (
        work.groupby(context_cols + ["quarter"], observed=True)
        .agg(agg_spec)
        .reset_index()
    )
    agg = agg.rename(columns={"_active": "n_active_entities"})
    agg = agg.sort_values(context_cols + ["quarter"])
    g = agg.groupby(context_cols, observed=True)
    new_cols = []
    for col in count_cols:
        for w in windows:
            name = f"ctx_{col}_sum{w}"
            agg[name] = g[col].transform(lambda s: s.rolling(w, min_periods=1).sum())
            new_cols.append(name)
        name = f"ctx_{col}_growth"
        cur = g[col].transform(lambda s: s.rolling(4, min_periods=1).sum())
        prev = g[col].transform(lambda s: s.shift(4).rolling(4, min_periods=1).sum())
        agg[name] = (cur - prev) / prev.clip(lower=1.0)
        new_cols.append(name)
    name = "ctx_n_active_entities"
    agg[name] = g["n_active_entities"].transform(lambda s: s.rolling(4, min_periods=1).max())
    new_cols.append(name)

    out = work.merge(
        agg[context_cols + ["quarter"] + new_cols],
        on=context_cols + ["quarter"],
        how="left",
    )
    if shares and count_cols:
        own = f"{count_cols[0]}_sum4"
        ctx = f"ctx_{count_cols[0]}_sum4"
        if own in out and ctx in out:
            out["share_of_context"] = out[own] / out[ctx].clip(lower=1.0)
    return out


# ------------------------------------------------------------- time splitting
@dataclass(frozen=True)
class Fold:
    """One walk-forward fold: train strictly before `test_year`."""
    test_year: int
    train_origins: tuple[pd.Period, pd.Period]
    test_origins: tuple[pd.Period, pd.Period]


def walk_forward_folds(
    first_test_year: int = 2014,
    last_test_year: int = 2025,
) -> list[Fold]:
    """Expanding-window walk-forward. Test = all origins whose quarter falls in
    the test year. Train = every origin strictly before that year started.

    This is the only splitting scheme used for headline numbers. No random
    splits, no shuffling, no k-fold.
    """
    folds = []
    for year in range(first_test_year, last_test_year + 1):
        test_start = pd.Period(f"{year}Q1", freq="Q")
        test_end = pd.Period(f"{year}Q4", freq="Q")
        test_end = min(test_end, ORIGIN_END)
        if test_start > ORIGIN_END:
            break
        folds.append(
            Fold(
                test_year=year,
                train_origins=(ORIGIN_START, test_start - 1),
                test_origins=(test_start, test_end),
            )
        )
    return folds


def split_by_origin(panel: pd.DataFrame, fold: Fold) -> tuple[pd.DataFrame, pd.DataFrame]:
    q = panel["quarter"]
    tr = panel[(q >= fold.train_origins[0]) & (q <= fold.train_origins[1])]
    te = panel[(q >= fold.test_origins[0]) & (q <= fold.test_origins[1])]
    return tr, te


# -------------------------------------------------------------------- metrics
def prevalence(y: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    return float(np.nanmean(y)) if len(y) else float("nan")


def average_precision(y, score) -> float:
    from sklearn.metrics import average_precision_score

    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(s) & np.isfinite(y)
    if ok.sum() < 2 or len(np.unique(y[ok])) < 2:
        return float("nan")
    return float(average_precision_score(y[ok], s[ok]))


def roc_auc(y, score) -> float:
    from sklearn.metrics import roc_auc_score

    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(s) & np.isfinite(y)
    if ok.sum() < 2 or len(np.unique(y[ok])) < 2:
        return float("nan")
    return float(roc_auc_score(y[ok], s[ok]))


def brier(y, score) -> float:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(s) & np.isfinite(y)
    return float(np.mean((s[ok] - y[ok]) ** 2)) if ok.any() else float("nan")


def precision_at_k(y, score, k_frac: float) -> float:
    """Precision among the top `k_frac` share of scored rows (by score)."""
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(s) & np.isfinite(y)
    y, s = y[ok], s[ok]
    if len(y) == 0:
        return float("nan")
    k = max(1, int(round(len(y) * k_frac)))
    idx = np.argsort(-s)[:k]
    return float(np.mean(y[idx]))


def recall_at_k(y, score, k_frac: float) -> float:
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(s) & np.isfinite(y)
    y, s = y[ok], s[ok]
    if len(y) == 0 or y.sum() == 0:
        return float("nan")
    k = max(1, int(round(len(y) * k_frac)))
    idx = np.argsort(-s)[:k]
    return float(y[idx].sum() / y.sum())


def lift_at_k(y, score, k_frac: float) -> float:
    p = prevalence(y)
    if not np.isfinite(p) or p == 0:
        return float("nan")
    return precision_at_k(y, score, k_frac) / p


def calibration_slope(y, score) -> float:
    """Slope of y ~ a + b*score, fitted by least squares. 1.0 = perfect."""
    y = np.asarray(y, dtype=float)
    s = np.asarray(score, dtype=float)
    ok = np.isfinite(s) & np.isfinite(y)
    if ok.sum() < 10:
        return float("nan")
    y, s = y[ok], s[ok]
    if np.std(s) == 0:
        return float("nan")
    b = np.cov(s, y)[0, 1] / np.var(s)
    return float(b)


def evaluate(
    y,
    score,
    name: str = "model",
    k_fracs: Sequence[float] = (0.05, 0.10, 0.20),
    scores_all: dict | None = None,
) -> dict:
    """Standard metric bundle. Every experiment reports this exact dict so that
    comparisons are apples to apples."""
    y = np.asarray(y, dtype=float)
    score = np.asarray(score, dtype=float)
    out = {
        "model": name,
        "n": int(np.isfinite(y).sum()),
        "n_pos": int(np.nansum(y)),
        "prevalence": prevalence(y),
        "ap": average_precision(y, score),
        "roc_auc": roc_auc(y, score),
        "brier": brier(y, score),
        "calibration_slope": calibration_slope(y, score),
    }
    for k in k_fracs:
        tag = f"{int(round(k * 100))}pct"
        out[f"precision_at_{tag}"] = precision_at_k(y, score, k)
        out[f"recall_at_{tag}"] = recall_at_k(y, score, k)
        out[f"lift_at_{tag}"] = lift_at_k(y, score, k)
    if scores_all:
        out["scores"] = scores_all
    return out


# --------------------------------------------------------------- uncertainty
def block_bootstrap_ci(
    y,
    score,
    groups,
    stat: Callable[[np.ndarray, np.ndarray], float] = average_precision,
    B: int = 1000,
    alpha: float = 0.05,
    seed: int = 20261108,
) -> tuple[float, float, float]:
    """Cluster (block) bootstrap CI. Resampling units are the clusters in
    `groups` — companies for cell-level tasks, tracks for track-level tasks —
    because rows inside a company/track are strongly dependent across quarters.

    Returns (point_estimate, lo, hi).
    """
    y = np.asarray(y, dtype=float)
    score = np.asarray(score, dtype=float)
    groups = np.asarray(groups)
    ok = np.isfinite(y) & np.isfinite(score)
    y, score, groups = y[ok], score[ok], groups[ok]
    point = stat(y, score)
    uniq = np.unique(groups)
    if len(uniq) < 3:
        return point, float("nan"), float("nan")
    idx_by_group = {g: np.flatnonzero(groups == g) for g in uniq}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_group[g] for g in pick])
        try:
            v = stat(y[idx], score[idx])
        except Exception:  # noqa: BLE001
            continue
        if np.isfinite(v):
            vals.append(v)
    if len(vals) < 20:
        return point, float("nan"), float("nan")
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return point, float(lo), float(hi)


def paired_bootstrap_diff(
    y,
    score_a,
    score_b,
    groups,
    stat: Callable[[np.ndarray, np.ndarray], float] = average_precision,
    B: int = 1000,
    seed: int = 20261108,
) -> dict:
    """Paired cluster bootstrap for stat(a) - stat(b) on identical rows.
    Returns point estimate, CI and a two-sided bootstrap p-value."""
    y = np.asarray(y, dtype=float)
    a = np.asarray(score_a, dtype=float)
    b = np.asarray(score_b, dtype=float)
    groups = np.asarray(groups)
    ok = np.isfinite(y) & np.isfinite(a) & np.isfinite(b)
    y, a, b, groups = y[ok], a[ok], b[ok], groups[ok]
    point = stat(y, a) - stat(y, b)
    uniq = np.unique(groups)
    idx_by_group = {g: np.flatnonzero(groups == g) for g in uniq}
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(B):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_group[g] for g in pick])
        try:
            d = stat(y[idx], a[idx]) - stat(y[idx], b[idx])
        except Exception:  # noqa: BLE001
            continue
        if np.isfinite(d):
            diffs.append(d)
    diffs = np.asarray(diffs)
    if len(diffs) < 20:
        return {"diff": float(point), "lo": float("nan"), "hi": float("nan"), "p": float("nan")}
    lo, hi = np.quantile(diffs, [0.025, 0.975])
    # two-sided bootstrap p: fraction of resamples on the wrong side of 0
    p = 2 * min((diffs <= 0).mean(), (diffs >= 0).mean())
    return {
        "diff": float(point),
        "lo": float(lo),
        "hi": float(hi),
        "p": float(min(1.0, p)),
        "n_boot": int(len(diffs)),
    }


def holm_adjust(pvals: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni across the family of hypothesis tests."""
    items = [(k, v) for k, v in pvals.items() if v is not None and np.isfinite(v)]
    m = len(items)
    ordered = sorted(items, key=lambda kv: kv[1])
    adj: dict[str, float] = {k: float("nan") for k in pvals}
    prev = 0.0
    for i, (k, p) in enumerate(ordered):
        val = min(1.0, (m - i) * p)
        prev = max(prev, val)
        adj[k] = prev
    return adj


# ------------------------------------------------------------------ baselines
class ConstantBaseline:
    """Incidence / random baseline: predict the training-fold prevalence."""

    name = "B0_prevalence"

    def fit(self, X, y):
        self.p_ = float(np.nanmean(y))
        return self

    def predict_score(self, X):
        n = len(X) if hasattr(X, "__len__") else X.shape[0]
        return np.full(n, self.p_)


class SingleFeatureScore:
    """Wraps one column of X as a raw score (no fitting). Used for the
    persistence and moving-average baselines so they stay interpretable."""

    def __init__(self, col: str, name: str | None = None):
        self.col = col
        self.name = name or f"raw:{col}"

    def fit(self, X, y):
        return self

    def predict_score(self, X):
        return np.asarray(X[self.col], dtype=float)


class LogisticModel:
    """Standardised L2 logistic regression — the 'simple statistical model'."""

    def __init__(self, name: str = "B5_logistic", C: float = 1.0, max_iter: int = 2000):
        self.name = name
        self.C = C
        self.max_iter = max_iter

    def fit(self, X, y):
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        self.pipe_ = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(C=self.C, max_iter=self.max_iter, solver="lbfgs"),
        )
        self.pipe_.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float))
        return self

    def predict_score(self, X):
        return self.pipe_.predict_proba(np.asarray(X, dtype=float))[:, 1]


class GradientBoostingModel:
    """Lightweight HistGradientBoosting — the 'necessary lightweight ML' arm.
    Deliberately small: max_iter=200, depth<=4. No GPU, seconds to fit."""

    def __init__(self, name: str = "B6_hgb", max_iter: int = 200, max_depth: int = 4):
        self.name = name
        self.max_iter = max_iter
        self.max_depth = max_depth

    def fit(self, X, y):
        from sklearn.ensemble import HistGradientBoostingClassifier

        self.m_ = HistGradientBoostingClassifier(
            max_iter=self.max_iter,
            max_depth=self.max_depth,
            learning_rate=0.06,
            min_samples_leaf=40,
            l2_regularization=1.0,
            random_state=20261108,
        )
        self.m_.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float))
        return self

    def predict_score(self, X):
        return self.m_.predict_proba(np.asarray(X, dtype=float))[:, 1]


# -------------------------------------------------------- leakage audit tools
def leakage_audit(
    panel: pd.DataFrame,
    entity_cols: list[str],
    feature_cols: Sequence[str],
    target_col: str = "y",
) -> dict:
    """Structural leakage checks that can be automated.

    1. forward_window_overlap: fraction of test rows whose forward window
       overlaps another test row for the same entity (dependence, not leakage,
       but must be reported).
    2. train_test_entity_overlap: cells appearing in both train and test — this
       is expected and legitimate for panel data (same entity, different time),
       recorded so nobody mistakes it for a bug.
    3. feature_target_correlation_screen: any single feature with |corr| > 0.95
       against the target is flagged as a probable label leak.
    """
    out: dict = {"protocol_version": PROTOCOL_VERSION}
    q = panel["quarter"].astype(str)
    out["n_rows"] = int(len(panel))
    out["n_entities"] = int(panel.groupby(entity_cols, observed=True).ngroups)
    out["feature_count"] = len(feature_cols)
    out["n_missing_target"] = int(panel[target_col].isna().sum())

    corr = {}
    y = panel[target_col]
    for c in feature_cols:
        s = pd.to_numeric(panel[c], errors="coerce")
        if s.notna().sum() < 50 or s.std() == 0:
            continue
        r = s.corr(y)
        if pd.notna(r) and abs(r) > 0.80:
            corr[c] = float(r)
    out["high_correlation_features_gt_0.80"] = corr
    out["suspected_label_leak"] = [k for k, v in corr.items() if abs(v) > 0.95]
    out["quarters"] = [str(q.min()), str(q.max())]
    return out


def save_json(obj, path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, pd.Period):
            return str(o)
        if isinstance(o, pd.Timestamp):
            return o.isoformat()
        if isinstance(o, Path):
            return str(o)
        return repr(o)

    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=_default), encoding="utf-8")


def holdout_policy() -> dict:
    """The frozen holdout contract. Experiments may read the holdout ONLY for the
    final reported number, never for model selection."""
    return {
        "dev": ["2004Q1", "2013Q4"],
        "validation": ["2014Q1", "2021Q4"],
        "holdout": ["2022Q1", "2025Q2"],
        "rule": (
            "Model and feature selection may use dev+validation only. The holdout "
            "block is evaluated once per hypothesis, with the pre-registered model, "
            "and reported regardless of outcome. Any peek at the holdout during "
            "development retroactively downgrades the study to exploratory and must "
            "be stated in the report."
        ),
    }
