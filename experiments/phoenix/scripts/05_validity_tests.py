#!/usr/bin/env python3
"""PHOENIX-001 / Step 05: harness validity tests.

Implements the automated part of the frozen protocol's audit list:
  L2  future-information test (features must not change when future events are deleted)
  L5  overlapping forward window accounting
  L7  track-taxonomy anachronism facts
and asserts the feature clock really moves under lag injection.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
import phoenix_common as pc  # noqa: E402

OUT = HERE.parent / "reports" / "05_validity_tests.json"
ENTS = ["company_key", "track_id"]


def build(events, lag):
    p = pc.build_joint_panel(events, ENTS, kinds=pc.ALL_KINDS, lag_days=lag)
    p = pc.add_forward_target(p, ENTS, value_col="n_device", horizon=pc.HORIZON_Q)
    p = pc.add_history_features(
        p, ENTS,
        ["f_n_device", "f_n_510k", "f_n_pma", "f_n_trial", "f_n_device_recall"],
    )
    return p


def main() -> int:
    rep: dict = {"protocol": pc.PROTOCOL_VERSION}
    con = pc.connect_ro()
    ev = pc.load_events(con)
    con.close()

    # ---- L2: future-information test ------------------------------------
    # Take one origin quarter. Delete every event that *became available* after
    # that quarter, rebuild the panel, and compare the feature values at the
    # origin. They must be identical.
    test_q = pd.Period("2018Q2", freq="Q")
    p0 = build(ev, 90)
    feat_cols = [c for c in p0.columns if c.startswith("f_n_")]
    origin_rows = p0[p0["quarter"] == test_q][ENTS + feat_cols].sort_values(ENTS).reset_index(drop=True)

    cut = (test_q + 1).start_time
    ev_future_deleted = ev[ev["available_dt"] < cut].copy()
    p1 = build(ev_future_deleted, 90)
    rows1 = p1[p1["quarter"] == test_q][ENTS + feat_cols].sort_values(ENTS).reset_index(drop=True)

    # entities that only exist because of future data must be absent from p1
    common = origin_rows.merge(rows1, on=ENTS, suffixes=("_a", "_b"))
    diffs = {}
    for c in feat_cols:
        a, b = common[f"{c}_a"].to_numpy(), common[f"{c}_b"].to_numpy()
        diffs[c] = {
            "max_abs_diff": float(np.max(np.abs(a - b))) if len(a) else None,
            "n_compared": int(len(a)),
        }
    rep["L2_future_information"] = {
        "origin": str(test_q),
        "entities_in_full_panel": int(len(origin_rows)),
        "entities_in_truncated_panel": int(len(rows1)),
        "max_abs_feature_diff": max(
            (v["max_abs_diff"] or 0.0) for v in diffs.values()
        ) if diffs else None,
        "per_column": diffs,
        "verdict": None,
    }
    rep["L2_future_information"]["verdict"] = (
        "PASS" if rep["L2_future_information"]["max_abs_feature_diff"] == 0.0 else "FAIL"
    )

    # ---- lag injection really changes the feature clock -----------------
    p90 = build(ev, 90)
    p0l = build(ev, 0)
    m = p90.merge(p0l, on=ENTS + ["quarter"], suffixes=("_l90", "_l000"))
    cmp_cols = ["f_n_device_sum4", "f_n_device_cum", "f_n_device_sum1"]
    rep["lag_injection"] = {
        c: {
            "share_rows_differ": float((m[f"{c}_l90"] != m[f"{c}_l000"]).mean()),
            "corr": float(np.corrcoef(m[f"{c}_l90"], m[f"{c}_l000"])[0, 1]),
        }
        for c in cmp_cols if f"{c}_l90" in m.columns
    }
    rep["lag_injection"]["verdict"] = (
        "PASS" if rep["lag_injection"].get("f_n_device_sum4", {}).get("share_rows_differ", 0) > 0.01
        else "FAIL"
    )

    # ---- L5: overlapping window accounting ------------------------------
    d = p90.dropna(subset=["y"]).copy()
    d["year"] = d["quarter"].dt.year
    non_overlap = d[d["quarter"].dt.quarter == 1]
    rep["L5_overlap"] = {
        "all_origins": {"n": int(len(d)), "n_pos": int(d["y"].sum()), "prev": float(d["y"].mean())},
        "non_overlapping_Q1_only": {
            "n": int(len(non_overlap)),
            "n_pos": int(non_overlap["y"].sum()),
            "prev": float(non_overlap["y"].mean()),
        },
        "note": "headline numbers use the non-overlapping Q1-only sample",
    }

    # ---- L7: track-taxonomy coverage over time --------------------------
    ev2 = ev[ev["kind"].isin(pc.DEVICE_KINDS)]
    rep["L7_track_coverage_by_year"] = (
        ev2.assign(y=ev2["event_dt"].dt.year)
        .groupby("y")
        .apply(lambda g: float(g["track_id"].notna().mean()), include_groups=False)
        .loc[lambda s: s.index >= 2000]
        .round(4)
        .to_dict()
    )
    rep["L7_track_first_seen"] = (
        ev2.groupby("track_id", observed=True)["event_dt"].min().dt.strftime("%Y-%m-%d").to_dict()
    )

    # ---- L3: entity mapping conflicts -----------------------------------
    con = pc.connect_ro()
    conf = pd.read_sql_query(
        "select applicant_raw, count(distinct company_key) k, count(*) n from events "
        "where company_key is not null and applicant_raw is not null "
        "group by applicant_raw having k > 1 order by k desc limit 25",
        con,
    )
    coverage = pd.read_sql_query(
        "select kind, sum(case when company_key is null then 1 else 0 end) unmapped, count(*) n "
        "from events group by kind",
        con,
    )
    con.close()
    rep["L3_entity_mapping"] = {
        "applicant_raw_mapping_conflicts": int(len(conf)),
        "examples": conf.head(8).to_dict(orient="records"),
        "company_key_unmapped_share_by_kind": {
            r["kind"]: round(r["unmapped"] / r["n"], 4) for _, r in coverage.iterrows()
        },
    }

    # ---- L4: left truncation distribution -------------------------------
    rep["L4_exposure"] = {
        "exposure_q_quantiles": {
            str(k): float(v) for k, v in p90["exposure_q"].describe(
                percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]
            ).items()
        },
        "share_rows_exposure_lt_8": float((p90["exposure_q"] < 8).mean()),
    }

    # ---- L6: duplicate-record screening ---------------------------------
    con = pc.connect_ro()
    dup = pd.read_sql_query(
        "select count(*) c from (select company_key, track_id, product_code, substr(event_date,1,10) d, "
        "count(*) n from events where company_key is not null and product_code is not null "
        "group by 1,2,3,4 having n > 1)",
        con,
    )
    con.close()
    rep["L6_duplicates"] = {
        "same_company_track_code_day_duplicate_groups": int(dup["c"].iloc[0]),
        "note": "counted, not removed: these are legitimate distinct submissions in most cases",
    }

    # ---- panel summary at the frozen configuration ----------------------
    rep["panel_l090"] = {
        "rows": int(len(p90)),
        "labeled_rows": int(p90["y"].notna().sum()),
        "pos_rate_all": float(p90["y"].mean(skipna=True)),
        "pos_rate_q1_only": float(non_overlap["y"].mean()),
        "entities": int(p90.groupby(ENTS, observed=True).ngroups),
        "feature_columns": int(len(feat_cols)),
    }
    statuses = [
        rep["L2_future_information"]["verdict"],
        rep["lag_injection"]["verdict"],
    ]
    rep["verdict"] = "PASS" if all(s == "PASS" for s in statuses) else "FAIL"
    pc.save_json(rep, OUT)
    print(pc.json.dumps({k: v for k, v in rep.items() if k != "L7_track_first_seen"},
                        indent=2, ensure_ascii=False, default=str))
    print("\nwritten:", OUT)
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
