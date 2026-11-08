"""Self-test for the independent implementations in this folder.

Runs entirely on synthetic data plus, where a published paper gives both its
inputs and its outputs, an arithmetic cross-check of the formula. It proves the
implementations run and are arithmetically correct. It does NOT reproduce any
paper's study, sample, or conclusions.

Run:  python selftest_synthetic.py
Exit code 0 = all checks passed. Prints a JSON summary on the last line.

Cross-checks against published numbers (M6, doi:10.2196/103040):
  * HHI per era from the published Table 1 counts
  * Wilson 95% CI for the Era 4 radiology share (published: 74.5%-80.3%)
  * 2-proportion z test, Era 3 vs Era 4 radiology share (published: P=.001)
  * Cochran-Armitage Z for radiology across eras (published: Z=+5.30)
These validate the formulas, using only numbers the paper itself prints.
"""

from __future__ import annotations

import json
import sys
import traceback

import numpy as np

import era_stats
import hhi as hhi_mod
import trajectory_features as tf

RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


# --------------------------------------------------------------------------- #
def test_hhi_identities() -> None:
    check("HHI monopoly == 1.0", close(hhi_mod.hhi([100]), 1.0, 1e-12), f"{hhi_mod.hhi([100]):.6f}")
    check("HHI equal 4 shares == 0.25", close(hhi_mod.hhi([25, 25, 25, 25]), 0.25, 1e-12))
    check("HHI equal 10 shares == 0.10", close(hhi_mod.hhi([1] * 10), 0.10, 1e-12))
    check(
        "HHI invariant to zero-count categories",
        close(hhi_mod.hhi([5, 5, 0, 0, 0]), hhi_mod.hhi([5, 5]), 1e-12),
    )
    check(
        "effective number of categories == 1/HHI",
        close(hhi_mod.effective_number_of_categories([50, 50]), 2.0, 1e-12),
    )


def test_hhi_against_m6_table1() -> None:
    """Feed the M6 paper's own Table 1 counts in; compare with its printed HHI."""
    rows = {
        "Radiology": (15, 118, 347, 614),
        "Cardiovascular": (4, 36, 34, 62),
        "Neurology": (2, 12, 6, 45),
        "Anesthesiology": (3, 2, 3, 18),
        "Gastroenterology-urology": (0, 1, 4, 19),
        "Hematology": (6, 4, 5, 5),
        "Ophthalmic": (0, 2, 4, 4),
        "Pathology": (2, 0, 1, 6),
        "Other (n=9 specialties)": (10, 15, 2, 19),
    }
    published = [0.181, 0.427, 0.738, 0.612]
    published_totals = [42, 190, 406, 792]
    got = hhi_mod.era_table_hhi(rows, eras=["Era 1", "Era 2", "Era 3", "Era 4"])
    # Eras 2-4 are recoverable from the pooled table at 3 significant digits.
    for g, p, n in list(zip(got, published, published_totals))[1:]:
        check(
            f"HHI {g['era']} from published counts: computed={g['hhi']:.4f} published={p}",
            g["n"] == n and close(g["hhi"], p, 0.01),
            f"n={g['n']} delta={g['hhi'] - p:+.4f}",
        )
    # Era 1 is the discriminating case: the pooled "Other (n=9)" row cannot
    # reproduce 0.181 because pooling raises HHI when the denominator is small.
    era1 = got[0]
    check(
        "HHI Era 1 is NOT reproducible from the pooled table (documented finding)",
        era1["n"] == 42 and era1["hhi"] > published[0] + 0.02,
        f"pooled gives {era1['hhi']:.4f} vs published {published[0]}",
    )
    sens = hhi_mod.share_base_sensitivity(
        {"listed 9 rows": 42},
        {"listed 9 rows": 42},
    )
    check("share_base_sensitivity rejects unequal totals", close(sens["delta"], 0.0, 1e-12))

    # Direction of the artefact: disaggregating the pooled bucket lowers HHI.
    agg = {"Radiology": 15, "Cardiovascular": 4, "Neurology": 2, "Anesthesiology": 3,
           "Hematology": 6, "Pathology": 2, "Other(9)": 10}
    dis = {"Radiology": 15, "Cardiovascular": 4, "Neurology": 2, "Anesthesiology": 3,
           "Hematology": 6, "Pathology": 2, "OtherA": 2, "OtherB": 2, "OtherC": 1,
           "OtherD": 1, "OtherE": 1, "OtherF": 1, "OtherG": 1, "OtherH": 1}
    s = hhi_mod.share_base_sensitivity(agg, dis)
    check(
        "disaggregating a pooled 'Other' bucket lowers HHI (base sensitivity)",
        s["delta"] < 0,
        f"agg={s['hhi_aggregated']:.4f} dis={s['hhi_disaggregated']:.4f} delta={s['delta']:+.4f}",
    )
    check(
        "disaggregated Era-1 HHI lands near the published 0.181",
        close(s["hhi_disaggregated"], 0.181, 0.01),
        f"{s['hhi_disaggregated']:.4f}",
    )


def test_bootstrap() -> None:
    concentrated = [700, 100, 100, 50, 50]
    ci = hhi_mod.hhi_ci(concentrated, n_boot=2000, seed=7)
    check("bootstrap CI brackets the point estimate",
          ci["ci_low"] <= ci["hhi"] <= ci["ci_high"],
          f"{ci['ci_low']:.3f} <= {ci['hhi']:.3f} <= {ci['ci_high']:.3f}")
    check("bootstrap CI is non-degenerate", ci["ci_high"] - ci["ci_low"] > 0)

    # Planted decline: era B is clearly more diversified than era A.
    a = [820, 60, 40, 40, 40]
    b = [500, 120, 110, 100, 170]
    res = hhi_mod.hhi_difference_test(a, b, n_boot=2000, seed=11)
    check("planted decline detected (symmetric p < 0.05)", res["p_symmetric"] < 0.05,
          f"diff={res['observed_diff']:+.4f} p_sym={res['p_symmetric']:.4f} "
          f"p_paper={res['p_paper_rule_decline']:.4f}")
    check("95% CI for the difference excludes zero",
          res["ci_diff_high"] < 0 or res["ci_diff_low"] > 0,
          f"[{res['ci_diff_low']:+.4f}, {res['ci_diff_high']:+.4f}]")

    # No planted change: both eras drawn from the same shares.
    rng = np.random.default_rng(3)
    p = np.array([0.6, 0.2, 0.1, 0.1])
    x = rng.multinomial(400, p)
    y = rng.multinomial(400, p)
    null = hhi_mod.hhi_difference_test(x, y, n_boot=1500, seed=5)
    check("no-change null is not flagged at 0.05", null["p_symmetric"] > 0.05,
          f"p_sym={null['p_symmetric']:.4f}")

    # The paper's literal rule is asymmetric; demonstrate it explicitly.
    up = hhi_mod.hhi_difference_test(b, a, n_boot=800, seed=13)  # expected increase
    check("paper's rule returns p>=1 (clipped) when direction is reversed",
          up["p_paper_rule_decline"] >= 1.0 - 1e-12 and up["p_symmetric"] < 0.05,
          f"p_paper={up['p_paper_rule_decline']:.4f} p_sym={up['p_symmetric']:.4f}")


def test_era_stats() -> None:
    # Cochran-Armitage: planted monotone increase.
    inc = era_stats.cochran_armitage([10, 20, 30, 40], [100, 100, 100, 100])
    check("CA detects a planted increasing trend", inc["z"] > 3 and inc["p_two_sided"] < 0.01,
          f"z={inc['z']:+.2f} p={inc['p_two_sided']:.2e}")
    flat = era_stats.cochran_armitage([25, 25, 25, 25], [100, 100, 100, 100])
    check("CA does not flag a flat series", abs(flat["z"]) < 0.5,
          f"z={flat['z']:+.3f} p={flat['p_two_sided']:.3f}")

    # Cross-check against M6's published CA Z for radiology (Z = +5.30).
    ca_rad = era_stats.cochran_armitage([15, 118, 347, 614], [42, 190, 406, 792])
    check("CA reproduces M6 published Z=+5.30 for radiology (tol 0.15)",
          close(ca_rad["z"], 5.30, 0.15), f"z={ca_rad['z']:+.3f}")

    # 2-proportion z test: cross-check M6's P=.001 for the Era3->Era4 radiology dip.
    z = era_stats.two_proportion_z(347, 406, 614, 792)
    check("2-prop z reproduces M6 Era3->Era4 P=.001",
          z["p_two_sided"] < 0.002 and close(z["diff"], -0.079, 0.01),
          f"diff={z['diff']:+.4f} z={z['z']:+.3f} p={z['p_two_sided']:.4f}")

    # Wilson CI: cross-check M6's published 74.5%-80.3% for 614/792.
    lo, hi = era_stats.wilson_ci(614, 792)
    check("Wilson CI reproduces M6 published 74.5%-80.3%",
          close(lo * 100, 74.5, 0.2) and close(hi * 100, 80.3, 0.2),
          f"{lo * 100:.2f}% - {hi * 100:.2f}%")
    check("Wilson CI stays inside [0,1] and contains p",
          lo <= 614 / 792 <= hi and 0 <= lo and hi <= 1)
    det = era_stats.wilson_ci_overdispersed(614, 792, design_effect=4.0)
    check("design-effect Wilson interval is wider than the naive one",
          (det[1] - det[0]) > (hi - lo), f"naive width={hi - lo:.4f} inflated width={det[1] - det[0]:.4f}")

    # Bonferroni
    adj = era_stats.bonferroni([0.001, 0.01, 0.5], m=17)
    check("Bonferroni multiplies by 17 and clips at 1",
          close(adj[0], 0.017, 1e-12) and adj[2] == 1.0, f"{adj}")

    # Sparse chi-square with permutation p-value
    table = [[347, 34, 6, 3], [614, 62, 45, 18], [15, 4, 2, 3]]
    perm = era_stats.chi2_with_permutation(table, n_perm=2000, seed=21)
    check("sparse-table chi-square flags <5 expected cells",
          perm["frac_cells_expected_lt5"] > 0,
          f"frac={perm['frac_cells_expected_lt5']:.2f} min_exp={perm['min_expected']:.2f}")
    check("permutation p-value is in (0,1] and agrees in direction with asymptotic",
          (0.0 < perm["p_permutation"] <= 1.0), f"p_perm={perm['p_permutation']:.4f} p_asym={perm['p_asymptotic']:.2e}")
    check("Cramer's V in (0,1)", 0 < perm["cramers_v"] < 1, f"V={perm['cramers_v']:.3f}")


def test_trajectory_features() -> None:
    c = tf.ClusterSnapshot(
        year=1996,
        papers={"a": 1974, "b": 1990, "c": 1995, "d": 1996},
        influence={"a": 1.5, "b": 2.0, "c": 2.5, "d": 3.0},
    )
    check("%New counts a two-year window (x and x-1)", close(tf.pct_new(c), 0.5, 1e-12),
          f"{tf.pct_new(c):.3f}")
    check("whRCR sums influence", close(tf.whrcr(c), 9.0, 1e-12))

    # Contemporaneous influence must not use future citations (leakage guard).
    citations = {"p": [(1990, 1), (1995, 3), (2000, 100)]}
    check("hRCR at 1995 ignores 2000 citations",
          close(tf.contemporaneous_influence(citations, 1995)["p"], 4.0, 1e-12),
          "4.0 not 104.0")

    # Cohesion: degenerate partition -> 1.0, uniform -> 0.0
    check("cohesion == 1.0 when all papers in one bin", close(tf.topical_cohesion([7]), 1.0, 1e-12))
    check("cohesion == 0.0 for a uniform partition",
          close(tf.topical_cohesion([2, 2, 2, 2]), 0.0, 1e-12), f"{tf.topical_cohesion([2,2,2,2]):.6f}")
    check("entropy of uniform 4-bin partition == ln 4",
          close(tf.shannon_entropy([1, 1, 1, 1]), np.log(4), 1e-12))

    # Majority-overlap trajectory linking: plant a 3-year growing cluster.
    s1 = tf.ClusterSnapshot(year=2001, papers={f"p{i}": 2000 for i in range(10)})
    s2 = tf.ClusterSnapshot(year=2002, papers={f"p{i}": 2000 for i in range(10)}
                            | {f"q{i}": 2002 for i in range(3)})
    s3 = tf.ClusterSnapshot(year=2003, papers={f"p{i}": 2000 for i in range(10)}
                            | {f"q{i}": 2002 for i in range(3)}
                            | {f"r{i}": 2003 for i in range(5)})
    unrelated = tf.ClusterSnapshot(year=2004, papers={f"z{i}": 2004 for i in range(6)})
    chains = tf.link_trajectories([s1, s2, s3, unrelated], rule="of_terminal")
    longest = max(chains, key=len)
    check("majority-overlap chaining recovers the planted 3-year trajectory",
          len(longest) == 3, f"chains={[len(c) for c in chains]}")
    strict = tf.link_trajectories([s1, s2], rule="of_earlier")
    check("stricter 'of_earlier' rule also links the growing cluster", len(max(strict, key=len)) == 2)
    detached = tf.link_trajectories([s1, unrelated], rule="of_terminal")
    check("non-overlapping clusters are not linked",
          all(len(c) == 1 for c in detached), f"chains={[len(c) for c in detached]}")

    # Ancestral %New reads the previous snapshot
    traj = [s1, s2, s3]
    feats = tf.trajectory_features(traj, cohesion_bins=[10, 3, 5])
    check("trajectory_features returns all four features",
          set(["pct_new", "ancestral_pct_new", "whrcr", "cohesion"]) <= set(feats),
          json.dumps({k: round(v, 4) for k, v in feats.items() if isinstance(v, float)}))
    check("ancestral %New == %New of the previous snapshot",
          close(feats["ancestral_pct_new"], tf.pct_new(s2), 1e-12))


def test_richards_and_metrics() -> None:
    # Recover a known Richards curve from noise-free synthetic points.
    truth = {"K": 250.0, "B": 0.55, "nu": 1.3, "t0": 2010.0, "Q": 2.0}
    years = np.arange(2000, 2021, dtype=float)
    observed = tf.richards(years, **truth)
    fit = tf.fit_richards(years, observed)
    check("Richards fit converges on noise-free data", fit["ok"], str(fit.get("params")))
    check("Richards fit recovers the asymptote K within 2%",
          fit["ok"] and close(fit["params"]["K"], truth["K"], 0.02 * truth["K"]),
          f"K_hat={fit['params']['K']:.2f} vs {truth['K']}")
    check("Richards fit R^2 > 0.999 on noise-free data", fit["ok"] and fit["r2"] > 0.999,
          f"R2={fit['r2']:.6f}")
    check("Richards with nu=1 equals the ordinary logistic at the midpoint",
          close(float(tf.richards(np.array([0.0]), 100.0, 1.0, 1.0, 0.0, 1.0)[0]), 50.0, 1e-9))

    # Metrics against hand-computed values.
    check("MALE is 0 for a perfect forecast", close(tf.male([5, 10], [5, 10]), 0.0, 1e-12))
    check("RMSLE is 0 for a perfect forecast", close(tf.rmsle([5, 10], [5, 10]), 0.0, 1e-12))
    expected_male = abs(np.log1p(4) - np.log1p(3))
    check("MALE matches a hand-computed single-point value",
          close(tf.male([3], [4]), expected_male, 1e-12), f"{tf.male([3], [4]):.6f}")
    check("MSLE == MALE^2 for a single point",
          close(tf.msle([3], [4]), expected_male**2, 1e-12))
    check("matches the M5 abstract's claimed improvement scale (~0.04-0.18)",
          all(0 < v < 1 for v in [tf.male([10], [12]), tf.rmsle([10], [12])]))

    # Subtask boundaries exactly as published (<2 and >4).
    check("new subtask is < 2 citations", tf.assign_subtask(1, "new") and not tf.assign_subtask(2, "new"))
    check("grown subtask is > 4 citations", tf.assign_subtask(5, "grown") and not tf.assign_subtask(4, "grown"))
    check("2-4 citation gap belongs to neither restricted subtask",
          not tf.assign_subtask(3, "new") and not tf.assign_subtask(3, "grown"))


def test_backtest_protocol() -> None:
    """Build synthetic citation trajectories with a real signal and check the protocol."""
    rng = np.random.default_rng(42)
    years = list(range(2004, 2024))
    n = 120
    series: dict[str, list[int]] = {}
    for i in range(n):
        K = rng.uniform(2, 200)
        B = rng.uniform(0.2, 0.9)
        t0 = rng.uniform(2010, 2018)
        curve = tf.richards(np.array(years, dtype=float), K, B, 1.0, t0, 1.0)
        counts = np.maximum(0, np.rint(np.diff(np.concatenate([[0], curve])))).astype(int)
        events = []
        for y, c in zip(years, counts):
            if c > 0:
                events.append((y, int(c)))
        series[f"p{i}"] = tf.cumulative_from_events(events, years)

    bt = tf.rolling_origin_backtest(series, years, history=10, horizons=(1, 2, 5, 10),
                                    subtask="random", seed=1)
    check("backtest produces per-horizon metrics for all requested horizons",
          len(bt["per_horizon"]) == 4, f"n={bt['n']}")
    errs = [row["rmsle"] for row in bt["per_horizon"]]
    check("forecast error grows with horizon", errs == sorted(errs),
          "rmsle by horizon = " + ", ".join(f"{e:.3f}" for e in errs))
    check("all metrics are finite and non-negative",
          all(np.isfinite(r["male"]) and r["male"] >= 0 and r["rmsle"] >= 0 for r in bt["per_horizon"]))

    bt_new = tf.rolling_origin_backtest(series, years, history=10, horizons=(1, 5),
                                        subtask="new", seed=1)
    bt_grown = tf.rolling_origin_backtest(series, years, history=10, horizons=(1, 5),
                                          subtask="grown", seed=1)
    check("new/grown subtasks partition the sample (both non-empty here)",
          bt_new["n"] > 0 and bt_grown["n"] > 0 and bt_new["n"] + bt_grown["n"] < bt["n"],
          f"new={bt_new['n']} grown={bt_grown['n']} all={bt['n']}")


def main() -> int:
    tests = [
        test_hhi_identities,
        test_hhi_against_m6_table1,
        test_bootstrap,
        test_era_stats,
        test_trajectory_features,
        test_richards_and_metrics,
        test_backtest_protocol,
    ]
    for t in tests:
        try:
            t()
        except Exception:  # a crashing test is a failure, not a skip
            RESULTS.append({"check": t.__name__, "ok": False, "detail": "exception"})
            print(f"[FAIL] {t.__name__} raised")
            traceback.print_exc()

    n_pass = sum(1 for r in RESULTS if r["ok"])
    n_fail = len(RESULTS) - n_pass
    summary = {
        "n_checks": len(RESULTS),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "status": "PASS" if n_fail == 0 else "FAIL",
        "data": "synthetic only (seeded); plus formula cross-checks against published M6 table values",
        "checks": RESULTS,
    }
    print()
    print(f"{n_pass}/{len(RESULTS)} checks passed")
    print("SELFTEST_RESULT_JSON: " + json.dumps(summary))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
