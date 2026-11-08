#!/usr/bin/env python
"""Audit A - training-label maturity / temporal leakage in the PHOENIX-001 walk-forward.

Run from the repository root:

    python experiments/phoenix/h8_validation_v2/audits/a_maturity.py

Writes a_maturity.json next to this file. Reads only: data/medradar.sqlite (sqlite
URI mode=ro&immutable=1), the cached v1 track panels, and the frozen v1 result/log
files. Does not modify any file outside this audit directory.

WHAT IS TESTED
--------------
PHOENIX-001 uses pc.walk_forward_folds(first_test_year=2014, last_test_year=2025).
For test year Y the training range is every origin quarter from 2004Q1 through
(Y-1)Q4 and the test range is YQ1..YQ4.  For both targets the label of an origin q
is built from the FUTURE event clock: growth / any_activity use device events with
event_date in (q, q+4].  The v1 drivers (run_track.oof_scores, run_cell.fit_folds)
fit on every labelled training row in that range with no purge at the train/test
boundary.  The executable assertion audited here is

    train_label_observable_at  <=  test_decision_time

with
    decision time         = end of quarter q            (harness convention)
    label window          = (q, q+4]  on the event clock
    label_observable_at   = end(q+4) + L days           (declared publication delay)

Violations are training rows whose label could not have been published by the time
the fold's first prediction had to be made.  A weaker, always-necessary criterion is
also reported: training labels whose window contains events inside the fold's TEST
period (this is the channel through which test-period information enters training).

All numbers printed/written here are computed by this script.  Where a number is read
from a v1 artefact (published result, archived run log) it is labelled as such.
"""
from __future__ import annotations

import json
import re
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "experiments" / "phoenix" / "common"))
sys.path.insert(0, str(REPO / "experiments" / "phoenix" / "hypotheses" / "track"))
sys.path.insert(0, str(REPO / "experiments" / "phoenix" / "hypotheses" / "cell"))

import phoenix_common as pc          # noqa: E402
import track_common as tc            # noqa: E402
import run_track as rt               # noqa: E402
import cell_common as cc             # noqa: E402

DB = REPO / "data" / "medradar.sqlite"
DB_SHA_EXPECTED = pc.DB_SHA256_EXPECTED
OUT_JSON = HERE / "a_maturity.json"
TRACK_DIR = REPO / "experiments" / "phoenix" / "hypotheses" / "track"
CELL_DIR = REPO / "experiments" / "phoenix" / "hypotheses" / "cell"

HORIZON = int(pc.HORIZON_Q)          # 4
LAGS = (0, 90, 180)
PRIMARY_L = 90
TERMINALS = {0: "L000", 90: "L090", 180: "L180"}

# published v1 headline numbers (used only for the replication check)
PUBLISHED_H8 = TRACK_DIR / "results" / "h8_scitrends.json"


# --------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def read_text_auto(path: Path) -> str:
    """V1 logs are a mix of UTF-8 and UTF-16LE-with-BOM; decode either."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def qend(q: pd.Period) -> pd.Timestamp:
    """End of quarter q, the decision instant for a prediction at origin q."""
    return q.end_time


def obs_at(q: pd.Period, lag_days: int) -> pd.Timestamp:
    """label_observable_at = end(q+HORIZON) + lag_days."""
    return (q + HORIZON).end_time + pd.Timedelta(days=int(lag_days))


def quarters_between(a: pd.Period, b: pd.Period) -> int:
    return int((b - a).n) + 1


def obs_series(quarters: pd.Series, lag_days: int) -> pd.Series:
    """Map each origin quarter to its label_observable_at (cached over unique values)."""
    uniq = pd.unique(quarters.astype(str))
    lut = {s: obs_at(pd.Period(s, freq="Q"), lag_days) for s in uniq}
    return quarters.astype(str).map(lut)


def fmt_ts(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def pct(a: int, b: int) -> float:
    return float(a) / float(b) if b else float("nan")


# ------------------------------------------------------------- audit one panel
def audit_folds(panel: pd.DataFrame, folds, label: str) -> dict:
    """Per-fold maturity table for one task/panel (rows = labelled origins)."""
    q = panel["quarter"]
    y = panel["y"]
    records = []
    for f in folds:
        tr_mask = (q >= f.train_origins[0]) & (q <= f.train_origins[1]) & y.notna()
        te_mask = (q >= f.test_origins[0]) & (q <= f.test_origins[1]) & y.notna()
        n_tr = int(tr_mask.sum())
        n_te = int(te_mask.sum())
        decision = qend(f.test_origins[0])
        fit_time = qend(f.train_origins[1])
        rec = {
            "test_year": int(f.test_year),
            "train_origins": [str(f.train_origins[0]), str(f.train_origins[1])],
            "test_origins": [str(f.test_origins[0]), str(f.test_origins[1])],
            "decision_time": fmt_ts(decision),
            "fit_time_stricter": fmt_ts(fit_time),
            "executed_in_v1_walk_forward": bool(n_tr > 0 and n_te > 0),
            "n_train_rows_used": n_tr,
            "n_test_rows_scored": n_te,
            "by_lag": {},
        }
        train_qs = panel.loc[tr_mask, "quarter"]
        train_qstr = train_qs.astype(str)
        # admissible origins are defined over the fold's declared train range
        range_q = [str(x) for x in pd.period_range(f.train_origins[0],
                                                   f.train_origins[1], freq="Q")]
        for lag in LAGS:
            obs = obs_series(train_qs, lag)
            viol = obs > decision
            viol_fit = obs > fit_time
            # latest admissible training origin (over the declared train range)
            lut = {s: obs_at(pd.Period(s, freq="Q"), lag) for s in
                   (str(x) for x in pd.period_range(f.train_origins[0],
                                                    f.train_origins[1], freq="Q"))}
            admissible = [s for s in range_q if lut[s] <= decision]
            qmax = admissible[-1] if admissible else None
            def _dropped(q_max, f=f):
                """number of trailing train origin quarters that must be dropped"""
                if q_max is None:
                    return quarters_between(f.train_origins[0], f.train_origins[1])
                return int((f.train_origins[1] - pd.Period(q_max, freq="Q")).n)
            purge_q = _dropped(qmax)
            # the actual leakage channel: window contains events inside the test period
            overlap = np.array([(pd.Period(s, freq="Q") + HORIZON) >= f.test_origins[0]
                                for s in train_qstr])
            rec["by_lag"][TERMINALS[lag]] = {
                "latest_admissible_train_origin": qmax,
                "required_purge_quarters": int(purge_q),
                "n_violating_train_rows": int(viol.sum()),
                "share_violating_train_rows": pct(int(viol.sum()), n_tr),
                "n_violating_origins": int(len(set(train_qstr[viol]) - {None})),
                "violating_origins": sorted(set(train_qstr[viol])),
                "n_violating_train_rows_vs_fit_time": int(viol_fit.sum()),
                "label_obs_of_last_train_origin": fmt_ts(
                    obs_at(f.train_origins[1], lag)),
            }
            # stricter variant: all training labels must be observable when the model
            # is fitted (end of the last training quarter).  Report purge for it too.
            adm_fit = [s for s in range_q if lut[s] <= fit_time]
            qmax_fit = adm_fit[-1] if adm_fit else None
            rec["by_lag"][TERMINALS[lag]]["required_purge_quarters_vs_fit_time"] = int(
                _dropped(qmax_fit))
            rec["by_lag"][TERMINALS[lag]]["test_period_overlap"] = {
                "n_train_rows": int(overlap.sum()),
                "share_of_train_rows": pct(int(overlap.sum()), n_tr),
                "n_origins": int(len(set(train_qstr[overlap]))),
                "origins": sorted(set(train_qstr[overlap])),
            }
        records.append(rec)

    # ---- aggregate over folds that the v1 driver actually executed
    ex = [r for r in records if r["executed_in_v1_walk_forward"]]
    lag_summary = {}
    for lag in LAGS:
        key = TERMINALS[lag]
        tot_tr = sum(r["n_train_rows_used"] for r in ex)
        tot_v = sum(r["by_lag"][key]["n_violating_train_rows"] for r in ex)
        tot_v_fit = sum(r["by_lag"][key]["n_violating_train_rows_vs_fit_time"] for r in ex)
        tot_ov = sum(r["by_lag"][key]["test_period_overlap"]["n_train_rows"] for r in ex)
        purge = sorted({r["by_lag"][key]["required_purge_quarters"] for r in ex})
        purge_fit = sorted({r["by_lag"][key]["required_purge_quarters_vs_fit_time"]
                            for r in ex})
        lag_summary[key] = {
            "n_executed_folds": len(ex),
            "total_train_rows_used": tot_tr,
            "total_violating_train_rows": tot_v,
            "overall_share_violating_train_rows": pct(tot_v, tot_tr),
            "total_violating_train_rows_vs_fit_time": tot_v_fit,
            "required_purge_quarters_per_fold": purge,
            "required_purge_quarters_vs_fit_time_per_fold": purge_fit,
            "total_train_rows_with_test_period_events_in_label": tot_ov,
            "overall_share_train_rows_with_test_period_events_in_label": pct(tot_ov, tot_tr),
            "per_fold_share_train_rows_with_test_period_events_in_label": {
                str(r["test_year"]): pct(
                    r["by_lag"][key]["test_period_overlap"]["n_train_rows"],
                    r["n_train_rows_used"])
                for r in ex},
            "per_fold_share_violating_train_rows": {
                str(r["test_year"]): pct(
                    r["by_lag"][key]["n_violating_train_rows"],
                    r["n_train_rows_used"])
                for r in ex},
            "n_folds_affected_by_decision_time_violation":
                sum(1 for r in ex if r["by_lag"][key]["n_violating_train_rows"] > 0),
            "assertion_train_label_observable_at_le_test_decision_time":
                bool(tot_v == 0),
        }
    return {
        "task": label,
        "n_folds_declared": len(folds),
        "folds": records,
        "summary": lag_summary,
    }


# ------------------------------------------------------------ cached v1 panels
def panel_maturity(panel: pd.DataFrame, name: str) -> dict:
    """Right/left truncation of the label column in a cached v1 panel."""
    q, y = panel["quarter"], panel["y"]
    lab = panel[y.notna()]
    last_lab = lab["quarter"].max()
    right = panel[q > last_lab]
    left = panel[(q <= last_lab) & y.isna()]
    per_entity_first_lab = lab.groupby(["track_id"], observed=True)["quarter"].min()
    rows_per_entity = panel.groupby("track_id", observed=True).size()
    leading_nan = []
    interior_gaps = 0
    for tid, sub in panel.groupby("track_id", observed=True):
        sub = sub.sort_values("quarter")
        yy = sub["y"].to_numpy()
        first_lab_i = int(np.argmax(~np.isnan(yy)))
        leading_nan.append(first_lab_i)
        end_lab_i = len(yy) - 1 - int(np.argmax(~np.isnan(yy[::-1])))
        interior_gaps += int(np.isnan(yy[first_lab_i:end_lab_i + 1]).sum())
    return {
        "panel": name,
        "n_rows": int(len(panel)),
        "n_labeled": int(y.notna().sum()),
        "n_unlabeled": int(y.isna().sum()),
        "quarters": [str(q.min()), str(q.max())],
        "n_quarters": int(q.nunique()),
        "n_tracks": int(panel["track_id"].nunique()),
        "last_labelable_origin": str(last_lab),
        "n_rows_after_last_labelable_origin": int(len(right)),
        "share_unlabeled_after_last_labelable_origin": pct(int(right["y"].isna().sum()),
                                                           len(right)) if len(right) else None,
        "n_unlabeled_left_of_last_labelable": int(len(left)),
        "n_unlabeled_left_explained_by_8q_trailing_warmup": int(
            len(left) == int(sum(leading_nan))),
        "leading_nan_quarters_per_track_value_counts": {
            str(k): int(v) for k, v in
            pd.Series(leading_nan).value_counts().sort_index().items()},
        "interior_gap_rows_between_first_and_last_label": int(interior_gaps),
        "rows_per_track": {"min": int(rows_per_entity.min()),
                           "max": int(rows_per_entity.max())},
        "label_rule_at_last_origin": (
            "growth target needs the 8Q trailing mean (NaN for the first 7 observed "
            "quarters of every track) and the 4Q forward window (NaN after 2024Q2 "
            "because the v1 track panel was trimmed to ORIGIN_END=2025Q2 before "
            "add_forward_target was called; pc.build_joint_panel lines 336-339)"),
    }


def executed_fold_test_rows(panel: pd.DataFrame, folds) -> dict:
    q, y = panel["quarter"], panel["y"]
    out = {}
    for f in folds:
        te = int(((q >= f.test_origins[0]) & (q <= f.test_origins[1]) &
                  y.notna()).sum())
        out[str(f.test_year)] = te
    return out


# -------------------------------------------------------- purged H8 re-run (v1 path)
def h8_fold_loop(panel: pd.DataFrame, purge_lag: int | None) -> tuple[pd.DataFrame, list]:
    """Exact v1 fold loop (run_track.oof_scores) for B1_persistence and H8_growth,
    optionally purging training origins whose label is not observable at the fold's
    first test decision time (purge_lag = L in days).  purge_lag=None reproduces v1."""
    folds = pc.walk_forward_folds(2014, 2025)
    specs = rt.build_specs(panel)
    arms = ("B1_persistence", "H8_growth")
    q, y = panel["quarter"], panel["y"]
    parts, per_fold = [], []
    for f in folds:
        tr_mask = ((q >= f.train_origins[0]) & (q <= f.train_origins[1]) & y.notna()).to_numpy()
        te_mask = ((q >= f.test_origins[0]) & (q <= f.test_origins[1]) & y.notna()).to_numpy()
        if tr_mask.sum() == 0 or te_mask.sum() == 0:
            continue
        if purge_lag is not None:
            decision = qend(f.test_origins[0])
            obs = obs_series(panel.loc[tr_mask, "quarter"], purge_lag)
            keep = (obs <= decision).to_numpy()
            tr_mask = tr_mask.copy()
            tr_mask[np.flatnonzero(tr_mask)] = keep
        tr = panel.loc[tr_mask]
        te = panel.loc[te_mask]
        out = te[["track_id", "quarter", "y"]].copy()
        out["fold_year"] = f.test_year
        for arm in arms:
            spec = specs[arm]
            feats = [c for c in spec["features"]
                     if tr[c].notna().any() and float(tr[c].std(ddof=0)) > 0]
            model = pc.LogisticModel()
            model.fit(tr[feats].to_numpy(dtype=float), tr["y"].to_numpy(dtype=float))
            out[arm] = model.predict_score(te[feats].to_numpy(dtype=float))
        parts.append(out)
        per_fold.append({
            "test_year": int(f.test_year),
            "n_train_rows": int(tr_mask.sum()),
            "n_test_rows": int(te_mask.sum()),
            "ap_B1": pc.average_precision(te["y"].to_numpy(float), out["B1_persistence"].to_numpy(float)),
            "ap_H8": pc.average_precision(te["y"].to_numpy(float), out["H8_growth"].to_numpy(float)),
        })
    oof = pd.concat(parts, ignore_index=True)
    return oof, per_fold


def summarise_oof(oof: pd.DataFrame) -> dict:
    y = oof["y"].to_numpy(float)
    res = {"n": int(len(oof)), "n_pos": int(np.nansum(y)),
           "prevalence": float(np.nanmean(y)), "arms": {}}
    for arm in ("B1_persistence", "H8_growth"):
        res["arms"][arm] = pc.average_precision(y, oof[arm].to_numpy(float))
    d = pc.paired_bootstrap_diff(
        y, oof["H8_growth"].to_numpy(float), oof["B1_persistence"].to_numpy(float),
        oof["track_id"].to_numpy(), B=tc.B_BOOT, seed=tc.SEED)
    res["contrast_H8_minus_B1"] = {
        "diff": float(d["diff"]), "lo": float(d["lo"]), "hi": float(d["hi"]),
        "p_two_sided": float(d["p"]), "n_boot": int(d.get("n_boot", 0)),
        "ap_a": float(res["arms"]["H8_growth"]),
        "ap_b": float(res["arms"]["B1_persistence"]),
        "n": int(len(oof)), "n_pos": int(np.nansum(y)),
    }
    # dependence-only diagnostic: overlapping 4Q windows between scored rows of the
    # same track (no future information enters training; this is not leakage).
    grp = oof.groupby("track_id")["quarter"]
    n_overlap = 0
    for _, qs in grp:
        v = sorted(int((x - pd.Period("2004Q1", freq="Q")).n) for x in qs)
        s = set(v)
        n_overlap += sum(1 for x in v if any((x + d) in s for d in (1, 2, 3)))
    res["test_window_dependence"] = {
        "n_scored_rows": int(len(oof)),
        "n_rows_with_overlapping_label_window_other_scored_row_same_track": int(n_overlap),
        "share": pct(n_overlap, len(oof)),
        "note": "dependence (overlapping label windows), NOT leakage",
    }
    return res


# ----------------------------------------------------------------------- main
def main() -> int:
    t0 = time.time()
    print("=" * 78)
    print("AUDIT A - training-label maturity in the PHOENIX-001 walk-forward")
    print("=" * 78)

    # 1. database identity
    sha = sha256_file(DB)
    db_ok = sha == DB_SHA_EXPECTED
    print(f"[db] {DB}")
    print(f"[db] sha256={sha} frozen_match={db_ok}")

    folds = pc.walk_forward_folds(2014, 2025)
    print(f"[folds] declared {len(folds)}: "
          f"{[f.test_year for f in folds]}")
    print(f"[folds] train range for Y: {folds[0].train_origins[0]}..Y-1Q4  "
          f"test range: YQ1..YQ4 (last capped at {pc.ORIGIN_END})")

    # 2. track-level panels (cached v1 panels)
    panels = {lag: tc.ensure_panel(lag) for lag in LAGS}
    p90 = panels[PRIMARY_L]
    print(f"[track] panels L000/L090/L180 rows={len(p90)} "
          f"labelled={int(p90['y'].notna().sum())} "
          f"tracks={p90['track_id'].nunique()} "
          f"quarters={p90['quarter'].min()}..{p90['quarter'].max()}")
    y_equal = all(panels[lag]["y"].equals(p90["y"]) for lag in LAGS)
    print(f"[track] label column identical across lag scenarios: {y_equal}")

    track_audit = {TERMINALS[lag]: audit_folds(panels[lag], folds, "track")
                   for lag in LAGS}

    # cross-check against the archived v1 run log
    v1_track_log = read_text_auto(TRACK_DIR / "evidence" / "03_run_track.log")
    m = re.search(r"L090: OOF rows=(\d+) folds=(\d+) positives=(\d+)", v1_track_log)
    v1_oof_rows, v1_folds, v1_pos = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    executed = [r for r in track_audit["L090"]["folds"]
                if r["executed_in_v1_walk_forward"]]
    my_oof = sum(r["n_test_rows_scored"] for r in executed)
    my_pos = int(p90[(p90["quarter"] >= pd.Period("2014Q1", freq="Q")) &
                     (p90["y"].notna())]["y"].sum())
    print(f"[track] v1 log: OOF rows={v1_oof_rows} folds={v1_folds} positives={v1_pos}; "
          f"recomputed: rows={my_oof} folds={len(executed)} positives={my_pos}")

    # 3. maturity of the cached v1 track panel (#5)
    mat = panel_maturity(p90, "track_panel_L090.pkl (v1 cache, all lags)")
    print(f"[track-panel] last labelable origin={mat['last_labelable_origin']} "
          f"unlabeled={mat['n_unlabeled']} "
          f"(right={mat['n_rows_after_last_labelable_origin']}, "
          f"left/warmup={mat['n_unlabeled_left_of_last_labelable']}) "
          f"interior_gaps={mat['interior_gap_rows_between_first_and_last_label']}")

    # 4. cell-level panel (rebuilt in memory with the frozen harness; no writes)
    t1 = time.time()
    ev = pc.load_events(pc.connect_ro())
    cell = cc.build_cell_panel(PRIMARY_L, events=ev, verbose=False)
    print(f"[cell] panel rebuilt in memory: rows={len(cell)} "
          f"labelled={int(cell['y'].notna().sum())} cells="
          f"{cell.groupby(cc.ENT, observed=True).ngroups} "
          f"({time.time() - t1:.1f}s)")
    cell_audit = {"L090": audit_folds(cell, folds, "cell")}

    v1_cell_log = read_text_auto(CELL_DIR / "evidence" / "02_run_cell_L090.log")
    v1_cell = {int(a): (int(b), int(c)) for a, b, c in
               re.findall(r"\[L090\] fold (\d+): train=(\d+) test=(\d+)", v1_cell_log)}
    my_cell = {r["test_year"]: (r["n_train_rows_used"], r["n_test_rows_scored"])
               for r in cell_audit["L090"]["folds"]}
    cell_log_match = bool(v1_cell) and all(my_cell.get(y) == v for y, v in v1_cell.items())
    print(f"[cell] v1 log fold train/test row counts reproduced exactly: {cell_log_match}")
    mat_cell = {
        "panel": "cell_L090 (rebuilt, frozen harness)",
        "n_rows": int(len(cell)),
        "n_labeled": int(cell["y"].notna().sum()),
        "n_unlabeled": int(cell["y"].isna().sum()),
        "quarters": [str(cell["quarter"].min()), str(cell["quarter"].max())],
        "last_labelable_origin": str(cell.loc[cell["y"].notna(), "quarter"].max()),
        "v1_log_fold_counts_reproduced": cell_log_match,
        "v1_build_log_claimed_labeled": 62732,
        "note": ("current cell_common.build_cell_panel builds the frame out to "
                 "origin_end+4 before add_forward_target, so the right-truncation "
                 "defect is FIXED at cell level; the 62,732 figure in "
                 "evidence/01_build_panel.log is the pre-fix / frozen-smoke number"),
    }

    # 5. purged H8 re-run on the L090 panel (same code path as v1)
    panel090 = rt.attach_features(p90, PRIMARY_L)
    published = json.loads(PUBLISHED_H8.read_text(encoding="utf-8"))
    reruns = {}
    for key, purge_lag in (("v1_no_purge", None), ("purge_L000", 0),
                           ("purge_L090", 90), ("purge_L180", 180)):
        tt = time.time()
        oof, per_fold = h8_fold_loop(panel090, purge_lag)
        res = summarise_oof(oof)
        res["purge_lag_days"] = purge_lag
        res["elapsed_sec"] = round(time.time() - tt, 2)
        res["per_fold"] = per_fold
        reruns[key] = res
        print(f"[h8-rerun] {key:13s} n={res['n']} n_pos={res['n_pos']} "
              f"AP_B1={res['arms']['B1_persistence']:.6f} "
              f"AP_H8={res['arms']['H8_growth']:.6f} "
              f"dAP={res['contrast_H8_minus_B1']['diff']:+.6f} "
              f"CI=[{res['contrast_H8_minus_B1']['lo']:+.4f},"
              f"{res['contrast_H8_minus_B1']['hi']:+.4f}] "
              f"p={res['contrast_H8_minus_B1']['p_two_sided']:.3f} "
              f"({res['elapsed_sec']}s)")

    # 6. replication check against the published v1 H8 numbers
    rep = reruns["v1_no_purge"]
    pub_ap_h8 = published["arms_ap"]["H8_growth"]
    pub_ap_b1 = published["arms_ap"]["B1_persistence"]
    pub_d = published["primary_contrast"]["diff"]
    rep_ok = bool(abs(rep["arms"]["H8_growth"] - pub_ap_h8) < 1e-9 and
                  abs(rep["arms"]["B1_persistence"] - pub_ap_b1) < 1e-9 and
                  abs(rep["contrast_H8_minus_B1"]["diff"] - pub_d) < 1e-9)
    print(f"[replication] unpublished-code re-run reproduces published APs exactly: {rep_ok}")

    out = {
        "audit": "A - training-label maturity / temporal leakage in the PHOENIX-001 walk-forward",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": "python experiments/phoenix/h8_validation_v2/audits/a_maturity.py",
        "elapsed_sec": None,
        "db": {"path": str(DB), "sha256": sha, "matches_frozen": bool(db_ok)},
        "code_audited": {
            "harness": "experiments/phoenix/common/phoenix_common.py",
            "harness_lines": {
                "walk_forward_folds": "453-477 (train = ORIGIN_START..test_start-1)",
                "split_by_origin": "480-484 (no purge, no embargo)",
                "add_forward_target": "234-276 (label = (q, q+4] event clock)",
                "build_joint_panel_trim": "336-339 (trim to origin_end BEFORE label)",
            },
            "track": "experiments/phoenix/hypotheses/track/run_track.py "
                     "oof_scores lines 128-162 (train filter: quarter<=test_start-1 and y.notna())",
            "cell": "experiments/phoenix/hypotheses/cell/run_cell.py "
                    "fit_folds lines 46-76 (pc.split_by_origin then dropna(y))",
        },
        "definitions": {
            "origin_q": "a prediction is made for origin quarter q",
            "decision_time": "end of quarter q (end_time); features at q may include "
                             "events whose available_at + injected lag falls inside q",
            "label_window": f"(q, q+HORIZON] on the event clock, HORIZON={HORIZON}",
            "label_observable_at": "end(q+HORIZON) + L days (declared publication delay)",
            "assertion": "train_label_observable_at <= test_decision_time",
            "test_decision_time_primary": "end of the fold's FIRST test origin quarter "
                                          "(earliest prediction made with that training set)",
            "fit_time_stricter": "end of the fold's last training quarter (the instant the "
                                 "training set is frozen); reported as a stricter variant",
            "required_purge_quarters": "number of trailing training origin quarters with "
                                       "label_observable_at > decision_time",
            "leakage_channel": "training rows whose label window (q,q+4] contains at least "
                               "one quarter inside the fold's test period",
            "L_values": {"0": "nominal/control", "90": "headline", "180": "stress"},
        },
        "assumptions": [
            "The harness decision convention is end-of-quarter q (stated in "
            "add_history_features docstring, phoenix_common.py lines 359-363); the audit "
            "uses that convention for both features and decisions.",
            "available_at == event_date for every row in this database (frozen protocol "
            "0.3) so L is a DECLARED publication delay, not a measured one; L=0 means the "
            "event is public the day it happens, which is optimistic.",
            "Training rows are exactly the rows the v1 drivers used: quarter inside the "
            "train range and y not NaN (run_track.py:133, run_cell.py:52).",
            "Purging is done at whole-quarter granularity (drop the offending origin "
            "quarters entirely); no fractional-quarter embargo is considered.",
            "Fold test_decision_time is the earliest test decision of the fold; a single "
            "model is fitted per fold in v1, so that is the binding deadline.",
            "The cell-level panel is rebuilt in memory from the frozen harness (no files "
            "written) and cross-checked against the archived v1 run log row counts.",
            "The purged H8 re-run uses the identical v1 features, model, folds and seed; "
            "only the training-row mask changes.",
            "Dependence between overlapping test label windows is not leakage and is "
            "reported separately.",
        ],
        "not_testable_here": [
            "The true FDA publication delay of each event: the database stores "
            "available_at == event_date, so no real lag can be measured; L is declared.",
            "Whether a real analyst would have had the labelled data at the decision "
            "instant: only the arithmetic assertion is testable.",
            "Whether the same defect exists for the cell-level MODEL RESULT at a "
            "different magnitude: the cell-level walk-forward was not re-run (structure "
            "and row counts are audited; the defect is identical by construction).",
        ],
        "track_level": {
            "panel_shape": {"rows": int(len(p90)),
                            "labeled": int(p90["y"].notna().sum()),
                            "tracks": int(p90["track_id"].nunique()),
                            "quarters": [str(p90["quarter"].min()),
                                         str(p90["quarter"].max())],
                            "label_identical_across_lags": bool(y_equal)},
            "v1_log_cross_check": {"v1_oof_rows": v1_oof_rows, "v1_folds": v1_folds,
                                   "v1_positives": v1_pos,
                                   "recomputed_oof_rows": int(my_oof),
                                   "recomputed_folds": int(len(executed)),
                                   "recomputed_positives": int(my_pos)},
            "by_lag": track_audit,
        },
        "cell_level": {
            "v1_log_fold_counts": {str(k): {"train": v[0], "test": v[1]}
                                   for k, v in sorted(v1_cell.items())},
            "v1_log_fold_counts_reproduced": cell_log_match,
            "panel_maturity": mat_cell,
            "by_lag": cell_audit,
        },
        "second_maturity_problem_cached_v1_track_panel": mat,
        "h8_rerun": {
            "panel": "track_panel_L090.pkl + entrants_hhi_L090.csv (v1 cache), same "
                     "features/model/folds/seed as run_track.py",
            "purge_rule": "drop training rows whose label_observable_at exceeds the "
                          "fold's first test decision time, for the stated L",
            "replication_of_published": bool(rep_ok),
            "published_h8": {
                "source": "experiments/phoenix/hypotheses/track/results/h8_scitrends.json",
                "n": published["n"], "n_pos": published["n_pos"],
                "lag_scenario": published["lag_scenario"],
                "ap_B1": pub_ap_b1, "ap_H8": pub_ap_h8,
                "diff": pub_d,
                "lo": published["primary_contrast"]["lo"],
                "hi": published["primary_contrast"]["hi"],
                "p": published["primary_contrast"]["p"],
                "verdict": published["verdict"],
            },
            "variants": reruns,
        },
    }
    out["elapsed_sec"] = round(time.time() - t0, 2)
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False,
                                   default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                        encoding="utf-8")

    # ------------------------------------------------------------ human summary
    print("\n" + "-" * 78)
    print("FACTS - TRACK LEVEL (T-TRACK, test years 2014..2025)")
    print("-" * 78)
    for lag in LAGS:
        s = track_audit[TERMINALS[lag]]["summary"][TERMINALS[lag]]
        print(f"L={lag:3d}d  assertion train_label_observable_at <= test_decision_time: "
              f"{'PASS' if s['assertion_train_label_observable_at_le_test_decision_time'] else 'FAIL'}"
              f"  folds_affected={s['n_folds_affected_by_decision_time_violation']}"
              f"/{s['n_executed_folds']}"
              f"  violating_rows={s['total_violating_train_rows']}"
              f"/{s['total_train_rows_used']}"
              f" ({100 * s['overall_share_violating_train_rows']:.2f}%)"
              f"  purge={s['required_purge_quarters_per_fold']}q/fold"
              f"  test-period-events-in-train-label="
              f"{s['total_train_rows_with_test_period_events_in_label']}"
              f" ({100 * s['overall_share_train_rows_with_test_period_events_in_label']:.2f}%)")
    print("\nper fold (L=0 / L=90 / L=180 violating rows, purge quarters):")
    print(f"{'year':>5} {'n_train':>8} {'vL0':>6} {'pL0':>4} {'vL90':>6} {'pL90':>4} "
          f"{'vL180':>6} {'pL180':>4} {'overlap':>8} {'n_test':>7}")
    for r in track_audit["L090"]["folds"]:
        b = r["by_lag"]
        print(f"{r['test_year']:>5} {r['n_train_rows_used']:>8} "
              f"{b['L000']['n_violating_train_rows']:>6} "
              f"{b['L000']['required_purge_quarters']:>4} "
              f"{b['L090']['n_violating_train_rows']:>6} "
              f"{b['L090']['required_purge_quarters']:>4} "
              f"{b['L180']['n_violating_train_rows']:>6} "
              f"{b['L180']['required_purge_quarters']:>4} "
              f"{b['L090']['test_period_overlap']['n_train_rows']:>8} "
              f"{r['n_test_rows_scored']:>7}"
              + ("" if r["executed_in_v1_walk_forward"] else "   (NOT EXECUTED in v1)"))

    print("\n" + "-" * 78)
    print("FACTS - CELL LEVEL (T-CELL, same folds)")
    print("-" * 78)
    for lag in LAGS:
        s = cell_audit["L090"]["summary"][TERMINALS[lag]]
        print(f"L={lag:3d}d  assertion: "
              f"{'PASS' if s['assertion_train_label_observable_at_le_test_decision_time'] else 'FAIL'}"
              f"  folds_affected={s['n_folds_affected_by_decision_time_violation']}"
              f"/{s['n_executed_folds']}"
              f"  violating_rows={s['total_violating_train_rows']}"
              f"/{s['total_train_rows_used']}"
              f" ({100 * s['overall_share_violating_train_rows']:.2f}%)"
              f"  purge={s['required_purge_quarters_per_fold']}q/fold"
              f"  test-period-events-in-train-label="
              f"{s['total_train_rows_with_test_period_events_in_label']}"
              f" ({100 * s['overall_share_train_rows_with_test_period_events_in_label']:.2f}%)")
    print(f"{'year':>5} {'n_train':>8} {'vL90':>6} {'purge':>5} {'overlap':>8} {'n_test':>7}")
    for r in cell_audit["L090"]["folds"]:
        b = r["by_lag"]["L090"]
        print(f"{r['test_year']:>5} {r['n_train_rows_used']:>8} "
              f"{b['n_violating_train_rows']:>6} {b['required_purge_quarters']:>5} "
              f"{b['test_period_overlap']['n_train_rows']:>8} {r['n_test_rows_scored']:>7}")

    print("\n" + "-" * 78)
    print("FACTS - SECOND MATURITY PROBLEM IN THE CACHED V1 TRACK PANEL")
    print("-" * 78)
    for k in ("n_rows", "n_labeled", "n_unlabeled", "last_labelable_origin",
              "n_rows_after_last_labelable_origin",
              "n_unlabeled_left_of_last_labelable",
              "interior_gap_rows_between_first_and_last_label"):
        print(f"  {k} = {mat[k]}")
    print(f"  leading NaN quarters per track = {mat['leading_nan_quarters_per_track_value_counts']}")
    print(f"  executed folds = {len(executed)} of {len(folds)}; test rows by year = "
          f"{executed_fold_test_rows(p90, folds)}")

    print("\n" + "-" * 78)
    print("FACTS - H8 RE-RUN UNDER THE MATURITY ASSERTION (L090 panel, v1 code path)")
    print("-" * 78)
    for key, r in reruns.items():
        c = r["contrast_H8_minus_B1"]
        print(f"  {key:13s} AP_H8={r['arms']['H8_growth']:.6f} "
              f"AP_B1={r['arms']['B1_persistence']:.6f} dAP={c['diff']:+.6f} "
              f"CI=[{c['lo']:+.4f},{c['hi']:+.4f}] p={c['p_two_sided']:.3f} "
              f"n_train_sum={sum(p['n_train_rows'] for p in r['per_fold'])}")
    print(f"  replication of published APs/diff exactly: {rep_ok}")
    print(f"\nwrote {OUT_JSON}  ({out['elapsed_sec']}s)")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
