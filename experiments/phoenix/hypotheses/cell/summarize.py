#!/usr/bin/env python3
"""Print a compact digest of every number the report needs, straight from the
result JSONs. Nothing is recomputed here: this is a reader, so a number can only
appear in the report if some results/*.json file actually contains it.

Usage
    python summarize.py > evidence/10_digest.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cell_common as cc  # noqa: E402
import phoenix_common as pc  # noqa: E402

R = cc.RESULTS


def f(x, nd=4):
    if x is None:
        return "NaN"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if v != v:
        return "NaN"
    return f"{v:.{nd}f}"


def apci(a):
    c = a.get("ap_ci95") or {}
    return f"{f(a['ap'])} [{f(c.get('lo'))}, {f(c.get('hi'))}]"


def line(label, c):
    return (f"  {label:<34} dAP={f(c['diff'], 4):>8}  "
            f"CI=[{f(c.get('lo95'))}, {f(c.get('hi95'))}]  "
            f"p2={f(c.get('p_two_sided'), 4)}  n={c.get('n')} n_pos={c.get('n_pos')}")


def main() -> int:
    meta = pc.json.loads(cc.meta_path().read_text(encoding="utf-8"))
    print("=" * 110)
    print("PANELS (from cache/panel_meta.json)")
    for tag, p in meta["panels"].items():
        print(f"  {tag}: rows={p['rows']} labeled={p['labeled_rows']} n_pos={p['n_pos']} "
              f"prev={f(p['prevalence'])} unlabeled={p['unlabeled_rows']} "
              f"origin={p['origin_first']}..{p['origin_last']} cells={p['n_cells']} "
              f"companies={p['n_companies']} tracks={p['n_tracks']}")
        fc = p["frozen_subset_check"]
        print(f"        frozen subset (<= {fc['last_origin_included']}): n={fc['labeled_rows']} "
              f"n_pos={fc['n_pos']} prev={fc['prevalence']:.6f} "
              f"match_03={fc['matches_03_harness_smoke']}")
        print(f"        q1_only rows={p['q1_only_rows']} n_pos={p['q1_only_n_pos']} "
              f"prev={f(p['q1_only_prevalence'])} holdout_rows={p['holdout_rows']} "
              f"exposure<8 share={f(p['share_rows_exposure_lt_8'])} "
              f"f_n_8k_nonzero={p['f_n_8k_nonzero_rows']}")

    st_path = R / "selftest.json"
    if st_path.exists():
        st = pc.json.loads(st_path.read_text(encoding="utf-8"))
        print("\nSELFTEST: " + st["verdict"] +
              "  " + "; ".join(f"{c['check']}={c['status']}" for c in st["checks"]))
        l2 = st.get("L2_future_information", {})
        print(f"  L2 origin={l2.get('origin')} entities={l2.get('n_entities_full')}/"
              f"{l2.get('n_entities_truncated')} max_abs_feature_diff="
              f"{l2.get('max_abs_feature_diff')} n_feature_cols={l2.get('n_feature_columns')} "
              f"labels_changed={l2.get('n_rows_whose_label_changed')}")

    allm_p = R / "cell_all_metrics.json"
    if not allm_p.exists():
        print("\n(cell_all_metrics.json not written yet)")
        return 0
    allm = pc.json.loads(allm_p.read_text(encoding="utf-8"))
    prim = pc.json.loads((R / "primary_tests.json").read_text(encoding="utf-8"))

    print("\n" + "=" * 110)
    print("HEADLINE ARM TABLE (sample: headline_q1 = non-overlapping Q1 origins 2014-2025)")
    for tag in ("L090", "L000", "L180"):
        s = allm["samples"][tag]["headline_q1"]
        print(f"\n[{tag}] n={s['n']} n_pos={s['n_pos']} prev={f(s['prevalence'])} "
              f"companies={s['n_companies']} tracks={s['n_tracks']} origins={s['n_origins']}")
        print("  arm                 AP [95% CI]                              AP_holdout_q1"
              "                        roc_auc  brier  calib  P@10%  lift@10%")
        ho = allm["samples"][tag]["holdout_q1"]["arms"]
        for arm in cc.ARM_NAMES:
            a = s["arms"][arm]
            h = ho[arm]
            print(f"  {arm:<18} {apci(a):<44} {apci(h):<44} "
                  f"{f(a['roc_auc'], 3)}  {f(a['brier'], 3)}  "
                  f"{f(a['calibration_slope'], 3):>6}  {f(a['precision_at_10pct'], 3)}  "
                  f"{f(a['lift_at_10pct'], 2)}")

    print("\n" + "=" * 110)
    print("HOLDOUT_Q1 SAMPLE SIZES")
    for tag in ("L090", "L000", "L180"):
        s = allm["samples"][tag]["holdout_q1"]
        print(f"  [{tag}] n={s['n']} n_pos={s['n_pos']} prev={f(s['prevalence'])} "
              f"origins={s['n_origins']}")

    print("\n" + "=" * 110)
    print("CONTRASTS (per lag x sample)")
    for tag in ("L090", "L000", "L180"):
        print(f"\n--- {tag} ---")
        for sample in ("headline_q1", "holdout_q1", "all_origins", "holdout_all",
                       "frozen_subset_q1", "headline_q1_exposure8"):
            if sample not in allm["contrasts"][tag]:
                continue
            print(f"  sample={sample}")
            for name, c in allm["contrasts"][tag][sample].items():
                print(line(f"{name} ({c['contrast']})", c))

    print("\n" + "=" * 110)
    print("FOLD DIRECTION CONSISTENCY (per fold, Q1-only rows)")
    for tag in ("L090", "L000", "L180"):
        fc = allm["fold_consistency"][tag]
        print(f"  [{tag}]")
        for hyp, v in fc.items():
            print(f"    {hyp}: positive in {v['folds_positive']}/{v['n_valid_folds']} folds "
                  f"({v['n_folds']} configured)  diffs=" +
                  ", ".join(f"{p['fold_year']}:{f(p['diff'], 3)}" for p in v["per_fold"]))

    print("\n" + "=" * 110)
    print("DECISIONS")
    for tag in ("L090", "L000", "L180"):
        print(f"  [{tag}]")
        for hyp, d in allm["decisions"][tag].items():
            c = d["contrast_record"]
            print(f"    {hyp}: {d['verdict']:<14} dAP={f(c['diff'])} p_used={f(d['p_used'])} "
                  f"folds+={d['folds_positive']}/{d['n_valid_folds']} conds={d['conditions']}"
                  + (f"  note={d['extra_note']}" if d.get("extra_note") else ""))
    print("\n  primary_tests.json (L090, holdout_q1):")
    for hyp in ("H1", "H2", "H4", "H5", "H10"):
        p = prim[hyp]
        print(f"    {hyp}: {p['contrast']} diff={f(p['diff'])} CI={p['ci95']} "
              f"p_raw={f(p['p_raw'])} verdict={p['verdict']} "
              f"by_lag={ {k: (v['diff'], v['p_raw'], v['verdict']) for k, v in p['by_lag'].items()} }")
    print("    secondary:", {k: (f(v['diff']), f(v['p_two_sided'])) for k, v in
                            prim["secondary_contrasts"].items()})
    print("    holm_local_reference_only:", prim["holm_local_reference_only"])

    print("\n" + "=" * 110)
    print("STABILITY (L090): AP by 3-year block and by top-10 entity")
    stab = allm["stability"]["L090"]
    for rec in stab["by_3yr_block_headline_q1"]:
        print(f"  block {rec['block']} (Q1-only) n={rec['n']} n_pos={rec['n_pos']} "
              f"prev={f(rec['prevalence'])}")
        print("    " + "  ".join(f"{a}={f(rec['ap'][a], 3)}" for a in cc.ARM_NAMES))
    for rec in stab["by_3yr_block_all_origins"]:
        print(f"  block {rec['block']} (all) n={rec['n']} prev={f(rec['prevalence'])}")
        print("    " + "  ".join(f"{a}={f(rec['ap'][a], 3)}" for a in cc.ARM_NAMES))
    for key in ("top10_companies_all_origins", "top10_tracks_all_origins"):
        print(f"  {key}:")
        for rec in stab[key]:
            print(f"    {rec['entity']:<28} n={rec['n']:<5} prev={f(rec['prevalence'], 3)}  " +
                  "  ".join(f"{a}={f(rec['ap'][a], 3)}" for a in
                            ("B0_prevalence", "B1_persistence", "B5_context",
                             "B6_hgb", "B7_hgb_net")))

    audit_p = R / "audit_cell.json"
    if audit_p.exists():
        au = pc.json.loads(audit_p.read_text(encoding="utf-8"))
        print("\n" + "=" * 110)
        print("AUDIT (results/audit_cell.json)")
        print("  L1:", {k: au["L1_label_leak_screen"][k] for k in
                        ("n_rows", "n_entities", "feature_count",
                         "high_correlation_features_gt_0.80", "suspected_label_leak")})
        print("  L2:", au["L2_future_information"].get("status"),
              au["L2_future_information"].get("detail", {}).get("max_abs_feature_diff"))
        print("  L3 by_kind:", {k: (v["n"], v["share_not_in_cell_universe"])
                                for k, v in au["L3_entity_mapping"]["by_kind"].items()})
        print("  L3 device_events_not_in_cell_universe:",
              au["L3_entity_mapping"]["device_events_in_window"],
              au["L3_entity_mapping"]["device_events_not_in_cell_universe"],
              au["L3_entity_mapping"]["device_share_not_in_cell_universe"],
              "conflicts:", au["L3_entity_mapping"]["applicant_raw_mapping_conflict_groups"],
              au["L3_entity_mapping"]["applicant_raw_mapping_conflict_events"])
        print("  L4:", au["L4_left_truncation"]["share_labeled_rows_exposure_lt_8"],
              au["L4_left_truncation"]["n_labeled_rows_exposure_lt_8"],
              au["L4_left_truncation"]["cells_with_exposure_lt_8_at_some_origin"],
              "/", au["L4_left_truncation"]["n_cells"])
        print("  L5:", au["L5_overlapping_origins"])
        print("  L6:", au["L6_cross_source_duplication"])
        print("  L7:", {k: au["L7_track_anachronism"][k] for k in
                        ("n_tracks_in_cell_universe", "cells_whose_track_first_appears_after_2014",
                         "share_cells_track_first_after_2014",
                         "cells_whose_track_first_appears_after_2018")})
        print("  H1 descriptives:", pc.json.dumps(au["H1_descriptives"], indent=4)[:3000])
        print("  H2 descriptives:", pc.json.dumps(au["H2_descriptives"], indent=4)[:3000])
        print("  H5 lead time:", pc.json.dumps(au["H5_lead_time"], indent=4)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
