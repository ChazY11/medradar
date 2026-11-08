"""PHOENIX-002 walk-forward runner: folds, maturity audit, out-of-fold scoring."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

import arms as A
import features as F
import metrics as M
import protocol as P
from data import qnum_scalar


# -------------------------------------------------------------------------- folds
@dataclass(frozen=True)
class Fold:
    test_year: int
    test_first_qnum: int
    test_last_qnum: int
    train_start_qnum: int
    train_latest_qnum: int
    rule: str
    label_lag_days: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["test_first_origin"] = str(P.ORIGIN_START + self.test_first_qnum)
        d["test_last_origin"] = str(P.ORIGIN_START + self.test_last_qnum)
        d["train_latest_origin"] = str(P.ORIGIN_START + self.train_latest_qnum)
        d["purge_quarters_used"] = self.test_first_qnum - self.train_latest_qnum
        return d


def make_folds(rule: str, label_lag_days: int,
               first_test_year: int = P.FIRST_TEST_YEAR,
               last_test_year: int = P.LAST_TEST_YEAR,
               train_window: str = "expanding") -> list[Fold]:
    if rule not in P.FOLD_RULES:
        raise ValueError(rule)
    origin_end = qnum_scalar(P.ORIGIN_END)
    folds = []
    for year in range(first_test_year, last_test_year + 1):
        tf = qnum_scalar(pd.Period(f"{year}Q1", freq="Q"))
        tl = min(qnum_scalar(pd.Period(f"{year}Q4", freq="Q")), origin_end)
        if tf > origin_end:
            break
        if rule == "v1_naive":
            latest = tf - 1                      # train strictly before the test year
        else:
            latest = tf - P.purge_quarters(label_lag_days)
        start = 0 if train_window == "expanding" else max(0, tf - 32)
        folds.append(Fold(test_year=year, test_first_qnum=tf, test_last_qnum=tl,
                          train_start_qnum=start, train_latest_qnum=latest,
                          rule=rule, label_lag_days=int(label_lag_days)))
    return folds


# ------------------------------------------------------------------- maturity audit
def maturity_audit(panel: pd.DataFrame, folds: list[Fold], label_lag_days: int) -> dict:
    """Quantify `train_label_observable_at <= test_decision_time` per fold.

    label_observable_qnum = q_train + HORIZON_Q + ceil(L/91)
    test_decision <= end of quarter (test_first - 1)  => permissible max = test_first - 1
    """
    lag_q = P.label_lag_quarters(label_lag_days)
    per_fold = []
    tot_rows = tot_viol = tot_dep = 0
    for f in folds:
        tr = panel[(panel["y"].notna())
                   & (panel["origin_eligible"])
                   & (panel["qnum"] >= f.train_start_qnum)
                   & (panel["qnum"] <= f.train_latest_qnum)]
        n = len(tr)
        obs = tr["qnum"].to_numpy() + P.HORIZON_Q + lag_q
        latest_permitted = f.test_first_qnum - 1
        viol = int((obs > latest_permitted).sum())
        # rows whose label window overlaps the fold's test period [test_first, test_last]
        win_start = tr["qnum"].to_numpy() + 1
        win_end = tr["qnum"].to_numpy() + P.HORIZON_Q
        depends_on_test = int(((win_end >= f.test_first_qnum)
                               & (win_start <= f.test_last_qnum)).sum())
        tot_rows += n
        tot_viol += viol
        tot_dep += depends_on_test
        per_fold.append({
            "test_year": f.test_year,
            **f.to_dict(),
            "n_training_rows": n,
            "max_label_observable_qnum": int(obs.max()) if n else None,
            "latest_permitted_label_observable_qnum": int(latest_permitted),
            "violating_training_rows": viol,
            "violating_share": float(viol / n) if n else float("nan"),
            "training_rows_whose_label_depends_on_test_period_events": depends_on_test,
            "leak_channel_share": float(depends_on_test / n) if n else float("nan"),
        })
    return {
        "label_lag_days": int(label_lag_days),
        "label_lag_quarters_rounded": lag_q,
        "purge_quarters_required": P.purge_quarters(label_lag_days),
        "definition": "label_observable_q = q_train + HORIZON_Q + ceil(L/91); "
                      "permissible <= test_first - 1 (prediction decided at end of test_first quarter)",
        "total_training_rows": int(tot_rows),
        "total_violating_training_rows": int(tot_viol),
        "total_violating_share": float(tot_viol / tot_rows) if tot_rows else float("nan"),
        "total_rows_depending_on_test_period_events": int(tot_dep),
        "total_leak_channel_share": float(tot_dep / tot_rows) if tot_rows else float("nan"),
        "per_fold": per_fold,
    }


# ---------------------------------------------------------------- out-of-fold run
def _row_masks(panel: pd.DataFrame, fold: Fold, target_col: str):
    q = panel["qnum"].to_numpy()
    elig = panel["origin_eligible"].to_numpy(dtype=bool)
    y_ok = panel[target_col].notna().to_numpy()
    train = elig & y_ok & (q >= fold.train_start_qnum) & (q <= fold.train_latest_qnum)
    test = elig & y_ok & (q >= fold.test_first_qnum) & (q <= fold.test_last_qnum)
    return np.flatnonzero(train), np.flatnonzero(test)


def run_oof(panel: pd.DataFrame, target_col: str, folds: list[Fold],
            feature_sets: dict[str, list[str]], arms: tuple[str, ...] = P.ARMS,
            return_fit: bool = False) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """Score every arm out-of-fold on identical rows."""
    panel = panel.reset_index(drop=True)
    X = {}
    for arm, feats in feature_sets.items():
        if arm == "M0_prevalence":
            X[arm] = np.zeros((len(panel), 0))
            continue
        use = [c for c in feats if c in panel.columns]
        X[arm] = panel[use].to_numpy(dtype=float)
        feature_sets[arm] = use
    y_all = panel[target_col].to_numpy(dtype=float)

    pieces, fold_meta, fit_records = [], [], []
    for f in folds:
        tr_idx, te_idx = _row_masks(panel, f, target_col)
        rec = {**f.to_dict(), "target": target_col, "n_train": int(len(tr_idx)),
               "n_test": int(len(te_idx)),
               "n_pos_train": int(np.nansum(y_all[tr_idx])),
               "n_pos_test": int(np.nansum(y_all[te_idx]))}
        if len(tr_idx) == 0 or len(te_idx) == 0 or np.nansum(y_all[te_idx]) == 0:
            rec["status"] = "SKIPPED_EMPTY"
            fold_meta.append(rec)
            continue
        rec["status"] = "OK"
        extra_cols = [c for c in ("stratum", "trail8_total", "fwd_total",
                                  "attribution_rate") if c in panel.columns]
        out = panel.iloc[te_idx][["track_id", "quarter", "qnum"] + extra_cols].copy()
        # the evaluated label is the requested target, not always Y1
        out["y"] = y_all[te_idx]
        out["target"] = target_col
        out["fold_year"] = f.test_year
        fit_this = {"test_year": f.test_year}
        for arm in arms:
            if arm == "M0_prevalence":
                out[arm] = float(np.nanmean(y_all[tr_idx]))
                continue
            scores, info = A.fit_arm(arm, X[arm][tr_idx], y_all[tr_idx], X[arm][te_idx],
                                     feature_sets.get(arm))
            out[arm] = scores
            fit_this[arm] = {"n_features_used": info.get("n_features_used"),
                             "kind": info.get("kind")}
        fit_records.append(fit_this)
        fold_meta.append(rec)
        pieces.append(out)
    if not pieces:
        return pd.DataFrame(), fold_meta, fit_records
    oof = pd.concat(pieces, ignore_index=True)
    return oof, fold_meta, fit_records


# ------------------------------------------------------------------ configuration
def add_attribution_rate(panel: pd.DataFrame, coverage: dict) -> pd.DataFrame:
    rates = {r["track_id"]: r["attribution_rate"] for r in coverage["by_track"]}
    panel = panel.copy()
    panel["attribution_rate"] = panel["track_id"].map(rates).astype(float)
    return panel


def run_config(panel: pd.DataFrame, target_col: str, rule: str, label_lag_days: int,
               arms: tuple[str, ...] = P.ARMS, with_ci: bool = True,
               first_test_year: int = P.FIRST_TEST_YEAR,
               train_window: str = "expanding",
               B: int = P.B_BOOT, seed: int = P.SEED) -> tuple[dict, pd.DataFrame]:
    folds = make_folds(rule, label_lag_days, first_test_year=first_test_year,
                       train_window=train_window)
    oof, fold_meta, fit_records = run_oof(panel, target_col, folds, feature_sets_dict(), arms)
    res = {
        "target": target_col, "fold_rule": rule, "label_lag_days": int(label_lag_days),
        "train_window": train_window, "first_test_year": first_test_year,
        "folds": fold_meta,
        "n": int(len(oof)),
        "n_pos": int(oof["y"].sum()) if len(oof) else 0,
        "prevalence": float(oof["y"].mean()) if len(oof) else float("nan"),
        "n_tracks": int(oof["track_id"].nunique()) if len(oof) else 0,
        "maturity": maturity_audit(panel, folds, label_lag_days),
        "arms": {}, "contrasts": {},
    }
    if oof.empty:
        return res, oof
    for arm in arms:
        res["arms"][arm] = M.evaluate_arm(oof, arm, arm, with_ci=with_ci, B=B, seed=seed)
    # pre-registered contrasts H8 vs each comparator + each arm vs prevalence
    for b in ("M1_persistence", "M2_ma_level", "M3_trend", "M7_mean_reversion",
              "M5_full_regularised", "M6_hgb"):
        if b in arms:
            res["contrasts"][f"M4_h8_growth - {b}"] = M.contrast(oof, "M4_h8_growth", b, B=B, seed=seed)
    if "M0_prevalence" in arms:
        for a in arms:
            if a != "M0_prevalence":
                res["contrasts"][f"{a} - M0_prevalence"] = M.contrast(
                    oof, a, "M0_prevalence", B=B, seed=seed)
    # stability / heterogeneity
    yr = oof["quarter"].astype(str).str.slice(0, 4).astype(int)
    oof["year"] = yr
    res["ap_by_year"] = {}
    for year, g in oof.groupby("year", observed=True):
        res["ap_by_year"][str(year)] = {
            arm: {"n": int(len(g)), "n_pos": int(g["y"].sum()),
                  "ap": M.average_precision(g["y"], g[arm])}
            for arm in ("M1_persistence", "M4_h8_growth")}
    res["delta_ap_by_year"] = {
        y: (v["M4_h8_growth"]["ap"] - v["M1_persistence"]["ap"])
        for y, v in res["ap_by_year"].items()}
    res["stratified_by_activity"] = {
        "definition": "trail8_total buckets",
        "buckets": _activity_buckets(oof),
    }
    res["stratified_by_attribution"] = _attribution_strata(oof)
    return res, oof


def _activity_buckets(oof: pd.DataFrame) -> dict:
    bins = [(-1, 0), (0, 2), (2, 5), (5, 12), (12, 10 ** 9)]
    labels = ["0", "1-2", "3-5", "6-12", "13+"]
    out = {}
    t = oof["trail8_total"].fillna(0).to_numpy(dtype=float)
    for (lo, hi), lab in zip(bins, labels):
        m = (t > lo) & (t <= hi)
        g = oof[m]
        if len(g) == 0:
            continue
        rec = {"n": int(len(g)), "n_pos": int(g["y"].sum()),
               "prevalence": float(g["y"].mean())}
        if g["y"].sum() >= 3:
            rec["ap_M1"] = M.average_precision(g["y"], g["M1_persistence"])
            rec["ap_M4"] = M.average_precision(g["y"], g["M4_h8_growth"])
            rec["delta_ap"] = rec["ap_M4"] - rec["ap_M1"]
        out[lab] = rec
    return out


def _attribution_strata(oof: pd.DataFrame, cut: float = 0.5) -> dict:
    if "attribution_rate" not in oof.columns:
        return {}
    out = {}
    for lab, m in (("high_ge_50pct", oof["attribution_rate"] >= cut),
                   ("low_lt_50pct", oof["attribution_rate"] < cut)):
        g = oof[m]
        rec = {"n": int(len(g)), "n_pos": int(g["y"].sum())}
        if g["y"].sum() >= 3:
            rec["ap_M1"] = M.average_precision(g["y"], g["M1_persistence"])
            rec["ap_M4"] = M.average_precision(g["y"], g["M4_h8_growth"])
            rec["delta_ap"] = rec["ap_M4"] - rec["ap_M1"]
        out[lab] = rec
    return out


# ------------------------------------------------------------------- placebos
def growth_columns() -> list[str]:
    return list(F.GROWTH_COLS)


def feature_sets_dict() -> dict[str, list[str]]:
    d = {k: list(v) for k, v in F.FEATURE_SETS.items()}
    d["M0_prevalence"] = []
    return d


def shuffle_growth_within_track(panel: pd.DataFrame, cols: list[str], rng: np.random.Generator) -> pd.DataFrame:
    """Permute the H8 growth-feature vectors in time inside each track."""
    out = panel.copy()
    vals = np.array(out[cols].to_numpy(dtype=float), copy=True)
    for _, idx in out.groupby("track_id", observed=True).indices.items():
        idx = np.sort(np.asarray(idx))
        perm = rng.permutation(len(idx))
        vals[idx] = vals[idx][perm]
    out[cols] = vals
    return out


def shift_growth_within_track(panel: pd.DataFrame, cols: list[str], k: int) -> pd.DataFrame:
    """Use growth features from k quarters earlier (time-shifted placebo)."""
    out = panel.copy()
    g = out.groupby("track_id", observed=True)
    for c in cols:
        out[c] = g[c].shift(k)
    return out


def shuffle_growth_across_tracks(panel: pd.DataFrame, cols: list[str], rng: np.random.Generator) -> pd.DataFrame:
    """Permute the growth-feature vectors across tracks within each quarter."""
    out = panel.copy()
    vals = np.array(out[cols].to_numpy(dtype=float), copy=True)
    for _, idx in out.groupby("qnum", observed=True).indices.items():
        idx = np.sort(np.asarray(idx))
        if len(idx) < 2:
            continue
        perm = rng.permutation(len(idx))
        vals[idx] = vals[idx][perm]
    out[cols] = vals
    return out
