"""Fast self-tests for the track-level experiment code.

One command:
    python experiments/phoenix/hypotheses/track/selftest.py

Exits non-zero if any test fails. Writes results/selftest.json.

Tests
-----
1. PELT recovers a single synthetic step change (and finds none in a flat series).
2. CUSUM does not fire on a flat series.
3. Features at origin q are unchanged when every later event is deleted (L2 mini).
4. Walk-forward folds are strictly ordered and non-overlapping.
5. Detector helpers: pre-window statistics are NaN, detection window logic, HHI.
"""
from __future__ import annotations

import math
import time

import numpy as np
import pandas as pd

import cp_methods as cp
import track_common as tc

pc = tc.pc

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    RESULTS.append({"test": name, "passed": bool(ok), "detail": detail})
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail != "" else ""))


def test_pelt_recovers_step() -> None:
    rng = np.random.default_rng(tc.SEED)
    n = 86
    true_cp = 40
    y = np.concatenate([rng.poisson(2.0, true_cp), rng.poisson(9.0, n - true_cp)]).astype(float)
    for lam in (0.2, 0.5, 1.0):
        cps = cp.pelt_cps(y, cp.pelt_penalty(lam, n))
        near = [c for c in cps if abs(c - true_cp) <= 2]
        check(f"pelt_recovers_step(lam={lam})", bool(near),
              f"found={cps[:6]} true={true_cp}")
    check("pelt_flat_no_change", cp.pelt_cps(np.full(n, 3.0), cp.pelt_penalty(1.0, n)) == [],
          "flat series -> no change points")
    # a deliberately huge penalty must return no change points on the stepped series
    check("pelt_penalty_monotone", len(cp.pelt_cps(y, 1e6)) == 0,
          "infinite penalty -> zero change points")


def test_cusum_flat() -> None:
    flat = np.full(86, 2.0)
    check("cusum_flat_no_alarm", cp.cusum_alarms(flat, k=0.5, h=5.0, r=np.inf) == [])
    # and it must fire on a large persistent step
    step = np.concatenate([np.full(40, 1.0), np.full(46, 10.0)])
    alarms = cp.cusum_alarms(step, k=0.5, h=5.0, r=np.inf)
    near = [a for a in alarms if abs(a - 40) <= 5]
    check("cusum_detects_step", bool(near), f"alarms={alarms[:5]} true=40")


def test_future_information() -> None:
    con = pc.connect_ro()
    try:
        ev = pc.load_events(con)
    finally:
        con.close()
    origin = pd.Period("2016Q3", freq="Q")
    full = tc.build_track_panel(ev, tc.HEADLINE_LAG)
    ev_lag = pc.apply_lag(ev, tc.HEADLINE_LAG)
    trunc = ev_lag[ev_lag["feat_quarter"] <= origin].drop(
        columns=["feat_dt", "feat_quarter", "lag_days"], errors="ignore")
    part = tc.build_track_panel(trunc, tc.HEADLINE_LAG)
    feat = [c for c in full.columns if c.startswith(("f_n_", "sct_", "b2_"))]
    a = full[full["quarter"] == origin].set_index("track_id")
    b = part[part["quarter"] == origin].set_index("track_id")
    common = a.index.intersection(b.index)
    worst, bad = 0.0, []
    for c in feat:
        x = a.loc[common, c].to_numpy(float)
        y = b.loc[common, c].to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y)
        d = float(np.max(np.abs(x[ok] - y[ok]))) if ok.any() else 0.0
        worst = max(worst, d)
        if d > 1e-9 or int((np.isfinite(x) != np.isfinite(y)).sum()):
            bad.append(c)
    check("future_information_at_origin", len(bad) == 0,
          f"origin={origin} entities={len(common)} max|diff|={worst:.2e} bad={bad[:4]}")


def test_folds() -> None:
    folds = pc.walk_forward_folds(2014, 2025)
    ok_order, ok_gap, ok_cov = True, True, True
    prev_end = None
    for f in folds:
        if not (f.train_origins[1] < f.test_origins[0] <= f.test_origins[1]):
            ok_order = False
        if (f.test_origins[0] - f.train_origins[1]).n != 1:
            ok_gap = False
        if prev_end is not None and f.test_origins[0] <= prev_end:
            ok_order = False
        prev_end = f.test_origins[1]
    if not (folds[0].test_origins[0] == pd.Period("2014Q1", freq="Q")
            and folds[-1].test_origins[1] == pc.ORIGIN_END):
        ok_cov = False
    check("folds_strictly_ordered", ok_order,
          f"{len(folds)} folds, first={folds[0].test_origins}, last={folds[-1].test_origins}")
    check("folds_contiguous_no_gap", ok_gap, "train end is always one quarter before test start")
    check("folds_cover_frozen_span", ok_cov, "2014Q1 .. 2025Q2")


def test_helpers() -> None:
    y = np.concatenate([np.full(30, 1.0), np.full(56, 4.0)])
    ratio = cp.fixed_threshold_ratio(y)
    check("fixed_ratio_nan_before_window", bool(np.all(np.isnan(ratio[:8]))))
    g = cp.growth_rate(y)
    check("growth_nan_before_window", bool(np.all(np.isnan(g[:8]))))
    d, delay = cp.detection_from_alarms([10, 41, 60], 40, win=2)
    check("detection_window", d and delay == 1.0, f"delay={delay}")
    d2, delay2 = cp.detection_from_alarms([10, 60], 40, win=2)
    check("detection_window_negative", (not d2) and np.isnan(delay2))
    # HHI arithmetic used by entrants_hhi: equal shares over 4 companies -> 0.25,
    # a single company -> 1.0, no events -> undefined
    import entrants_hhi as eh
    check("hhi_arithmetic",
          abs(eh.hhi_from_counts(np.array([1.0, 1, 1, 1])) - 0.25) < 1e-12
          and abs(eh.hhi_from_counts(np.array([5.0])) - 1.0) < 1e-12
          and np.isnan(eh.hhi_from_counts(np.array([0.0, 0.0]))))
    # high-pass removes a constant, keeps a deviation
    e = np.full((1, 10), 5.0)
    d = np.full((1, 10), 2.0)
    e[0, 6] = 8.0
    eh_s, dh = tc._highpass_series(e, d, np.array([0]))
    check("highpass_removes_level",
          abs(float(np.nanmean(eh_s[0, :6]))) < 1e-9 and eh_s[0, 6] > 2.0,
          f"mean(highpass first 6)={np.nanmean(eh_s[0, :6]):.2e} spike={eh_s[0, 6]:.2f}")


def main(log: tc.RunLog) -> int:
    t0 = time.time()
    log.step("running self-tests")
    test_pelt_recovers_step()
    test_cusum_flat()
    test_helpers()
    test_folds()
    test_future_information()
    n_fail = sum(1 for r in RESULTS if not r["passed"])
    out = {
        "protocol_version": pc.PROTOCOL_VERSION,
        "db_sha256": pc.DB_SHA256_EXPECTED,
        "lag_scenario": "L090",
        "command": tc.command_line(),
        "seed": tc.SEED,
        "n": len(RESULTS),
        "n_pos": len(RESULTS) - n_fail,
        "prevalence": (len(RESULTS) - n_fail) / max(1, len(RESULTS)),
        "checks": RESULTS,
        "n_failed": n_fail,
        "verdict": "PASS" if n_fail == 0 else "FAIL",
        "elapsed_sec": round(time.time() - t0, 2),
    }
    tc.save(out, tc.RESULTS_DIR / "selftest.json")
    log.step(f"selftest verdict={out['verdict']} ({out['n_pos']}/{out['n']} checks) "
             f"in {out['elapsed_sec']}s")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(tc.run_script("00_selftest", main))
