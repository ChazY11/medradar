"""Audit B - historical risk set / point-in-time eligible universe (PHOENIX-002 H8 validation).

Independent audit of the PHOENIX-001 v1 T-TRACK and T-CELL risk sets. Read-only on
data/medradar.sqlite (sqlite URI mode=ro&immutable=1). Does not import-modify or write
anything outside experiments/phoenix/h8_validation_v2/audits/.

Run:
    python experiments/phoenix/h8_validation_v2/audits/b_riskset.py

Writes b_riskset.json next to this file and prints every fact it writes.

Point-in-time rule used (state it exactly):
  * Feature clock = events.available_at + 90 days (the frozen injected lag).
  * A unit (track_id, or (company_key, track_id)) is ELIGIBLE at origin quarter q iff at
    least one of its events has feature-clock quarter <= q. Origin decisions are assumed
    to be made at the end of q (same convention as the frozen harness).
  * This rule uses only events with feature quarter <= q, i.e. only information that was
    public by the end of q under the injected lag. It never looks at q+1.. onward.
  * v1 eligibility (what the harness actually does) is: a unit row exists from its first
    event quarter on the EVENT clock (quarter in which event_date falls); the 90-day lag
    is applied to feature values only, never to universe membership.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PHOENIX = REPO / "experiments" / "phoenix"
COMMON = PHOENIX / "common"
sys.path.insert(0, str(COMMON))
import phoenix_common as pc  # noqa: E402

DB = REPO / "data" / "medradar.sqlite"
DB_SHA256_FROZEN = "445807CAB60DF66E0F0853C973AAF0DAE6065E72B6C9807D5DD5265097002C92"
TRACK_CACHE = PHOENIX / "hypotheses" / "track" / "cache" / "track_panel_L090.pkl"
CELL_META = PHOENIX / "hypotheses" / "cell" / "cache" / "panel_meta.json"
GROWTH_HISTORY_COLS = ["f_n_510k", "f_n_pma", "f_n_trial", "f_n_device_recall",
                       "f_n_device", "f_n_total"]
TRACK_ENTITY = ["track_id"]
CELL_ENTITY = ["company_key", "track_id"]
LAG_DAYS = 90
PIT_ORIGINS = ["2004Q1", "2010Q1", "2014Q1", "2020Q1", "2024Q2"]


def sec(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def clean(o):
    """JSON-safe: numpy -> python, NaN/Inf -> None."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Period):
        return str(o)
    if isinstance(o, Path):
        return str(o)
    return o


def main() -> int:
    t0 = time.time()
    out: dict = {"audit": "B_riskset",
                 "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat()}
    con = pc.connect_ro(DB)
    try:
        # ------------------------------------------------------------------ 0
        sec("0. PROVENANCE / DB")
        sha = sha256_file(DB)
        db_info = {
            "path": str(DB),
            "size_bytes": DB.stat().st_size,
            "sha256": sha,
            "matches_frozen": sha == DB_SHA256_FROZEN,
            "integrity_check": con.execute("pragma integrity_check").fetchone()[0],
        }
        out["provenance"] = db_info
        print(f"db sha256={sha} matches_frozen={sha == DB_SHA256_FROZEN} "
              f"size={DB.stat().st_size} integrity={db_info['integrity_check']}")
        kind_counts = pd.read_sql_query(
            "select kind, count(*) n from events group by kind order by n desc", con)
        out["db_event_kinds"] = kind_counts.set_index("kind")["n"].to_dict()
        print("event kinds (whole db):", out["db_event_kinds"])
        print("tracks table rows:",
              con.execute("select count(*) from tracks").fetchone()[0])

        # ------------------------------------------------------------ load v1 events
        ev = pc.load_events(con)          # exactly the v1 call (attributed, windowed)
        raw_win = pd.read_sql_query(
            """select event_id, kind, event_date, available_at, company_key, track_id,
                      product_code from events
               where event_date is not null and event_date >= ? and event_date <= ?""",
            con, params=[pc.PANEL_START, pc.PANEL_END])
        raw_win["dt"] = pd.to_datetime(raw_win["event_date"])
        raw_win["q"] = raw_win["dt"].dt.to_period("Q")
        print(f"v1 load_events rows={len(ev)}  raw window rows={len(raw_win)}")
        n_all_db = con.execute("select count(*) from events").fetchone()[0]
        out["v1_keep"] = {
            "all_db_events": int(n_all_db),
            "raw_window_events": int(len(raw_win)),
            "v1_kept": int(len(ev)),
            "v1_share_of_all_db": float(len(ev) / n_all_db),
            "v1_share_of_window": float(len(ev) / len(raw_win)),
        }
        print(f"v1 keeps {len(ev)}/{n_all_db} = {len(ev) / n_all_db:.2%} of all DB events; "
              f"{len(ev)}/{len(raw_win)} = {len(ev) / len(raw_win):.2%} of in-window events")
        avail_mismatch = int((raw_win["available_at"] != raw_win["event_date"]).sum())
        print(f"rows where available_at != event_date: {avail_mismatch}")
        mm_kind = raw_win[raw_win["available_at"] != raw_win["event_date"]]
        av_lag_days = (pd.to_datetime(mm_kind["available_at"], errors="coerce")
                       - mm_kind["dt"]).dt.days
        out["available_at_equals_event_date"] = {
            "window_rows": int(len(raw_win)),
            "mismatch_rows": avail_mismatch,
            "mismatch_rows_by_kind": mm_kind["kind"].value_counts().to_dict(),
            "mismatch_available_after_event": int((av_lag_days > 0).sum()),
            "mismatch_available_before_event": int((av_lag_days < 0).sum()),
            "mismatch_available_median_lag_days": float(av_lag_days.median())
            if len(av_lag_days) else None,
            "v1_loaded_mismatch_rows": int(
                (ev["available_dt"] != ev["event_dt"]).sum()),
        }
        print("   mismatch detail:", out["available_at_equals_event_date"])

        # feature clock column (+90d) for eligibility
        ev_lag = pc.apply_lag(ev, LAG_DAYS)
        ev_lag["feat_q"] = ev_lag["feat_quarter"]

        # ------------------------------------------------------------ whole-DB device sets
        dev_all = pd.read_sql_query(
            "select track_id, company_key, event_date from events "
            "where kind in ('510k','pma') and event_date is not null", con)
        dev_all["q"] = pd.to_datetime(dev_all["event_date"]).dt.to_period("Q")
        dev_tracks_ever = set(dev_all["track_id"].dropna().unique())
        track_ids_all = set(con.execute(
            "select distinct track_id from events where track_id is not null").fetchall())
        track_ids_all = {t[0] for t in track_ids_all}
        tracks_tbl = pd.read_sql_query("select * from tracks", con)
        out["taxonomy_table"] = {
            "tracks_rows": int(len(tracks_tbl)),
            "tracks_updated_at_distinct": tracks_tbl["updated_at"].value_counts().to_dict(),
            "product_codes_rows": con.execute("select count(*) from product_codes").fetchone()[0],
            "product_codes_updated_at_distinct": dict(pd.read_sql_query(
                "select updated_at, count(*) n from product_codes group by updated_at", con)
                .values.tolist()),
        }
        print(f"tracks table={len(tracks_tbl)} ids; updated_at={out['taxonomy_table']['tracks_updated_at_distinct']}")
        print(f"device tracks ever (whole DB, track_id not null) = {len(dev_tracks_ever)}; "
              f"distinct track_id any kind = {len(track_ids_all)}")

        # ============================================================ 1. T-TRACK
        sec("1. T-TRACK v1 panel composition (59 tracks)")
        cached = pd.read_pickle(TRACK_CACHE)
        rebuilt = pc.build_joint_panel(ev, TRACK_ENTITY, lag_days=LAG_DAYS)
        rebuilt = pc.add_forward_target(rebuilt, TRACK_ENTITY, value_col="n_device",
                                        target="growth")
        rebuilt = pc.add_history_features(rebuilt, TRACK_ENTITY, GROWTH_HISTORY_COLS)
        rebuilt = rebuilt.sort_values(TRACK_ENTITY + ["quarter"]).reset_index(drop=True)
        same_shape = (len(cached) == len(rebuilt))
        max_dev = 0.0
        for c in ["n_device", "f_n_device", "y", "f_n_device_sum8", "f_n_device_cum"]:
            a = cached[c].to_numpy(float)
            b = rebuilt[c].to_numpy(float)
            if same_shape and len(a) == len(b):
                m = np.nanmax(np.abs(a - b)) if len(a) else 0.0
                max_dev = max(max_dev, float(m))
        print(f"cached panel rows={len(cached)} tracks={cached.track_id.nunique()} | "
              f"rebuilt rows={len(rebuilt)} tracks={rebuilt.track_id.nunique()} same_shape={same_shape} "
              f"max_abs_dev={max_dev:.3e}")
        panel = rebuilt
        trk = pd.DataFrame({"track_id": sorted(panel["track_id"].unique())})
        trk["is_t_star"] = trk["track_id"].str.startswith("t_")
        trk["has_device_ever_dbwide"] = trk["track_id"].isin(dev_tracks_ever)
        dev_track_ids = trk.loc[trk.has_device_ever_dbwide, "track_id"]
        trial_only = trk.loc[~trk.has_device_ever_dbwide, "track_id"]
        panel["is_device_track"] = panel["track_id"].isin(dev_track_ids)
        panel["labeled"] = panel["y"].notna()
        panel["is_pos"] = panel["y"] == 1
        comp = []
        for name, mask in [
            ("device_tracks_>=1_device_event_ever", panel.is_device_track),
            ("t_star_trial_only_tracks_zero_device_ever", ~panel.is_device_track),
            ("ALL_PANEL", pd.Series(True, index=panel.index)),
        ]:
            sub = panel[mask]
            comp.append({
                "group": name,
                "tracks": int(sub.track_id.nunique()),
                "panel_rows": int(len(sub)),
                "labeled_rows": int(sub.labeled.sum()),
                "positives_growth_y": int(sub.is_pos.sum()),
                "negatives_growth_y": int((sub.labeled & (sub.y == 0)).sum()),
                "mean_y": float(sub.y.mean()),
            })
        out["t_track_composition"] = comp
        for r in comp:
            print(r)
        out["t_track_tables"] = {
            "tracks_table_rows": int(len(tracks_tbl)),
            "panel_tracks": int(panel.track_id.nunique()),
            "device_tracks": int(len(dev_track_ids)),
            "t_star_trial_only": int(len(trial_only)),
            "tracks_in_table_absent_from_panel": sorted(track_ids_all - set(trk.track_id)),
            "t_star_ids_in_panel": sorted(trial_only.tolist()),
            "device_track_ids": sorted(dev_track_ids.tolist()),
        }
        print("panel tracks=", panel.track_id.nunique(),
              "device=", len(dev_track_ids), "trial_only=", len(trial_only),
              "absent from panel=", out["t_track_tables"]["tracks_in_table_absent_from_panel"])
        # secondary: growth label needs >=3 device events in a forward 4Q window
        # how many "device tracks" can never satisfy that?
        max4 = (panel.groupby("track_id", observed=True)["n_device"]
                .apply(lambda s: s.rolling(4, min_periods=1).sum().max()))
        trk = trk.set_index("track_id")
        trk["max_4q_device"] = max4
        cannot_growth = trk.index[trk["max_4q_device"] < 3].tolist()
        rows_cg = int(panel[panel.track_id.isin(cannot_growth)].shape[0])
        out["t_track_cannot_hit_growth_min_events"] = {
            "definition": "tracks whose max trailing/forward 4Q device count < 3 "
                          "(growth label requires forward total >= 3)",
            "n_tracks": len(cannot_growth),
            "tracks": cannot_growth,
            "panel_rows": rows_cg,
            "labeled_rows": int(panel[panel.track_id.isin(cannot_growth)].labeled.sum()),
            "positives": int(panel[panel.track_id.isin(cannot_growth)].is_pos.sum()),
        }
        print("tracks that cannot ever satisfy growth min_events=3:", len(cannot_growth),
              cannot_growth)
        pos_by_track = panel.groupby("track_id", observed=True)["y"].agg(["count", "sum"])
        sup = pos_by_track[pos_by_track["sum"] > 0]
        out["t_track_positive_support"] = {
            "tracks_with_at_least_one_positive": int(len(sup)),
            "tracks_with_zero_positives": int(len(pos_by_track) - len(sup)),
            "tracks_with_zero_positives_ids": sorted(pos_by_track.index[
                pos_by_track["sum"] == 0].tolist()),
            "labelled_rows_on_positive_tracks": int(sup["count"].sum()),
            "positives_on_positive_tracks": int(sup["sum"].sum()),
            "prevalence_on_positive_tracks": float(sup["sum"].sum() / sup["count"].sum()),
        }
        print("positive support:", out["t_track_positive_support"])

        # ============================================================ 2. T-CELL
        sec("2. T-CELL v1 panel universe")
        cell_build = pc.build_joint_panel(ev, CELL_ENTITY, lag_days=LAG_DAYS,
                                          origin_end=pc.ORIGIN_END + pc.HORIZON_Q)
        cell_panel = pc.add_forward_target(cell_build, CELL_ENTITY, value_col="n_device",
                                           horizon=pc.HORIZON_Q, target="any_activity")
        cell_panel = cell_panel[cell_panel["quarter"] <= pc.ORIGIN_END].copy()
        cell_panel["labeled"] = cell_panel["y"].notna()
        cell_panel["is_pos"] = cell_panel["y"] == 1
        meta = json.loads(CELL_META.read_text(encoding="utf-8"))["panels"]["L090"]
        recomp = {
            "rows": int(len(cell_panel)),
            "labeled_rows": int(cell_panel.labeled.sum()),
            "n_pos": int(cell_panel.is_pos.sum()),
            "prevalence": float(cell_panel.y.mean()),
            "n_cells": int(cell_panel.groupby(CELL_ENTITY).ngroups),
            "n_companies": int(cell_panel.company_key.nunique()),
            "n_tracks": int(cell_panel.track_id.nunique()),
        }
        match_meta = (
            recomp["rows"] == meta["rows"] and recomp["n_pos"] == meta["n_pos"]
            and recomp["n_cells"] == meta["n_cells"]
        )
        out["t_cell_panel_meta"] = {"recomputed": recomp, "cached_L090": {
            "rows": meta["rows"], "labeled_rows": meta["labeled_rows"],
            "n_pos": meta["n_pos"], "prevalence": meta["prevalence"],
            "n_cells": meta["n_cells"], "n_companies": meta["n_companies"],
            "n_tracks": meta["n_tracks"]}, "matches_cached_meta": bool(match_meta)}
        print("recomputed:", recomp)
        print("cached meta:", out["t_cell_panel_meta"]["cached_L090"], "match:", match_meta)

        cells_raw = ev[CELL_ENTITY].drop_duplicates()
        LABEL_END = pc.ORIGIN_END + pc.HORIZON_Q   # 2026Q2: last quarter counted by the label
        cell_dev_q = (ev[ev.kind.isin(pc.DEVICE_KINDS) & (ev.quarter <= LABEL_END)]
                      .groupby(CELL_ENTITY, observed=True)["quarter"].min())
        cell_dev_q_anywindow = ev[ev.kind.isin(pc.DEVICE_KINDS)].groupby(
            CELL_ENTITY, observed=True)["quarter"].min()
        cell_first_q = ev.groupby(CELL_ENTITY, observed=True)["quarter"].min()
        cell_first_feat_q = ev_lag.groupby(CELL_ENTITY, observed=True)["feat_q"].min()
        cell_dev_all_db = dev_all.dropna(subset=["company_key"]).groupby(
            ["company_key", "track_id"], observed=True)["q"].min()
        panel_cells = cell_panel[CELL_ENTITY].drop_duplicates()
        pidx = pd.MultiIndex.from_frame(panel_cells)
        raw_idx = pd.MultiIndex.from_frame(cells_raw)
        dev_idx = pd.MultiIndex.from_frame(cell_dev_q.reset_index()[CELL_ENTITY])
        devdb_idx = cell_dev_all_db.index
        cell_flags = pd.DataFrame(index=pidx)
        cell_flags["ever_device_panelrange"] = pidx.isin(dev_idx)
        cell_flags["ever_device_anywindow"] = pidx.isin(
            pd.MultiIndex.from_frame(cell_dev_q_anywindow.reset_index()[CELL_ENTITY]))
        cell_flags["ever_device_dbwide"] = pidx.isin(devdb_idx)
        cell_flags["device_event_at_origin_quarter"] = pidx.isin(pd.MultiIndex.from_frame(
            cell_panel[cell_panel["n_device"] > 0][CELL_ENTITY].drop_duplicates()))
        cell_flags["in_t_star_track"] = cell_flags.index.get_level_values("track_id").str.startswith("t_")
        cf = cell_flags.reset_index()
        cp = cell_panel.merge(cf, on=CELL_ENTITY, how="left")
        devcells = int(cell_flags["ever_device_panelrange"].sum())
        cells_comp = []
        for name, mask in [
            ("cells_ever_device_>=1_device_event_(panel_label_range)", cp.ever_device_panelrange),
            ("cells_never_device_in_panel_range", ~cp.ever_device_panelrange),
            ("cells_in_t_star_tracks", cp.in_t_star_track),
            ("ALL_PANEL", pd.Series(True, index=cp.index)),
        ]:
            sub = cp[mask]
            cells_comp.append({
                "group": name,
                "cells": int(sub.groupby(CELL_ENTITY).ngroups),
                "panel_rows": int(len(sub)),
                "labeled_rows": int(sub.labeled.sum()),
                "positives": int(sub.is_pos.sum()),
                "negatives": int((sub.labeled & (sub.y == 0)).sum()),
                "mean_y": float(sub.y.mean()),
            })
        out["t_cell_composition"] = cells_comp
        for r in cells_comp:
            print(r)
        out["t_cell_tables"] = {
            "raw_attributed_cell_pairs_in_events": int(len(cells_raw)),
            "cells_in_joint_label_panel": int(cell_build.groupby(CELL_ENTITY).ngroups),
            "cells_in_trimmed_panel": int(len(panel_cells)),
            "cells_ever_device_panel_label_range": devcells,
            "cells_ever_device_at_an_origin_quarter": int(
                cell_flags["device_event_at_origin_quarter"].sum()),
            "cells_ever_device_any_window_incl_2026H2": int(cell_flags["ever_device_anywindow"].sum()),
            "cells_ever_device_dbwide": int(cell_flags["ever_device_dbwide"].sum()),
            "cells_never_device_panel_range": int(len(cell_flags) - devcells),
            "cells_never_device_raw_universe": int(len(raw_idx) - raw_idx.isin(dev_idx).sum()),
            "cells_in_t_star_tracks": int(cell_flags["in_t_star_track"].sum()),
        }
        print("cell tables:", out["t_cell_tables"])

        # ============================================================ 3. structurally impossible
        sec("3. Structurally impossible units (zero device events in ENTIRE database)")
        out["structurally_impossible"] = {}
        # T-TRACK
        tp = panel.copy()
        imp_rows = int((~tp.is_device_track).sum())
        imp_lab = int(((~tp.is_device_track) & tp.labeled).sum())
        imp_pos = int(((~tp.is_device_track) & tp.is_pos).sum())
        neg_pool = int((tp.labeled & (tp.y == 0)).sum())
        out["structurally_impossible"]["t_track"] = {
            "units_zero_device_ever": int(len(trial_only)),
            "panel_rows": imp_rows,
            "share_panel_rows": float(imp_rows / len(tp)),
            "labeled_rows": imp_lab,
            "positives": imp_pos,
            "negatives": imp_lab,
            "share_of_negative_pool": float(imp_lab / neg_pool),
            "negative_pool": neg_pool,
        }
        print("T-TRACK:", out["structurally_impossible"]["t_track"])
        # T-CELL
        imp = ~cp.ever_device_panelrange
        neg_pool_c = int((cp.labeled & (cp.y == 0)).sum())
        out["structurally_impossible"]["t_cell"] = {
            "units_zero_device_ever": int(len(cell_flags) - devcells),
            "panel_rows": int(imp.sum()),
            "share_panel_rows": float(imp.sum() / len(cp)),
            "labeled_rows": int((imp & cp.labeled).sum()),
            "positives": int((imp & cp.is_pos).sum()),
            "negatives": int((imp & cp.labeled & (cp.y == 0)).sum()),
            "share_of_negative_pool": float((imp & cp.labeled & (cp.y == 0)).sum() / neg_pool_c),
            "negative_pool": neg_pool_c,
            "cells_in_t_star_tracks": int(cf.in_t_star_track.sum()),
            "rows_in_t_star_tracks": int(cp.in_t_star_track.sum()),
            "negatives_in_t_star_tracks": int((cp.in_t_star_track & cp.labeled & (cp.y == 0)).sum()),
        }
        print("T-CELL:", out["structurally_impossible"]["t_cell"])
        # device-naive negatives (unit exists but has had zero device events yet)
        cp = cp.sort_values(CELL_ENTITY + ["quarter"]).reset_index(drop=True)
        cp["cum_device_own"] = cp.groupby(CELL_ENTITY)["n_device"].cumsum()
        cp["device_naive_row"] = cp["cum_device_own"] == 0
        out["structurally_impossible"]["t_cell_device_naive_negatives"] = {
            "definition": "panel row whose unit has had zero device events up to and "
                          "including origin q (label-clock cumulative count)",
            "labeled_negative_rows": int((cp.device_naive_row & cp.labeled & (cp.y == 0)).sum()),
            "share_of_negative_pool": float(
                (cp.device_naive_row & cp.labeled & (cp.y == 0)).sum() / neg_pool_c),
        }
        print("T-CELL device-naive negatives:",
              out["structurally_impossible"]["t_cell_device_naive_negatives"])

        # ============================================================ 4. PIT universe
        sec("4. Point-in-time eligible universe (lag +90d on availability clock)")
        origins = list(pd.period_range(pc.ORIGIN_START, pc.ORIGIN_END, freq="Q"))

        def pit_setup(df, entity_cols, first_feat_src):
            ff = (first_feat_src.groupby(entity_cols, observed=True)["feat_q"].min()
                  .rename("first_feat_q").reset_index())
            d = df.drop(columns=[c for c in ("first_feat_q",) if c in df.columns])
            d = d.merge(ff, on=entity_cols, how="left")
            d["pit_eligible"] = d["quarter"] >= d["first_feat_q"]
            # unit-level first quarters, used for the per-origin eligible counts
            unit = (d.groupby(entity_cols, observed=True)
                    .agg(first_event_q=("first_event_q", "first"),
                         first_feat_q=("first_feat_q", "first")).reset_index())
            return d, unit

        tp, t_unit = pit_setup(panel, TRACK_ENTITY, ev_lag)
        cp, c_unit = pit_setup(cp, CELL_ENTITY, ev_lag)

        def per_origin(d, unit):
            rows = d.groupby("quarter", observed=True).size().rename("v1_rows")
            out_rows = []
            for q in origins:
                v1_units = int((unit["first_event_q"] <= q).sum())
                pit_units = int((unit["first_feat_q"] <= q).sum())
                out_rows.append({"quarter": q, "v1_rows": int(rows.get(q, 0)),
                                 "v1_units": v1_units, "pit_units": pit_units})
            return pd.DataFrame(out_rows)

        t_per = per_origin(tp, t_unit)
        c_per = per_origin(cp, c_unit)

        def summarize(d, per, n_units):
            pi = per.set_index("quarter")
            s = {
                "n_origins": int(len(per)),
                "units_total_in_panel": int(n_units),
                "pit_units_min": int(per.pit_units.min()),
                "pit_units_median": float(per.pit_units.median()),
                "pit_units_max": int(per.pit_units.max()),
                "v1_rows_total": int(per.v1_rows.sum()),
                "rows_not_pit_eligible": int((~d.pit_eligible).sum()),
                "rows_not_pit_share": float((~d.pit_eligible).mean()),
                "by_origin": {str(q): {"v1_rows": int(r.v1_rows), "v1_units": int(r.v1_units),
                                       "pit_units": int(r.pit_units)}
                              for q, r in pi.iterrows()},
                "requested_origins": {q: {"v1_rows": int(pi.loc[pd.Period(q, "Q"), "v1_rows"]),
                                          "v1_units": int(pi.loc[pd.Period(q, "Q"), "v1_units"]),
                                          "pit_units": int(pi.loc[pd.Period(q, "Q"), "pit_units"])}
                                      for q in PIT_ORIGINS},
            }
            return s

        out["pit_universe"] = {
            "rule": "unit eligible at origin q iff min(feature-clock quarter) <= q; "
                    "feature clock = available_at + 90 days; origin decided at end of q",
            "t_track": summarize(tp, t_per, panel.track_id.nunique()),
            "t_cell": summarize(cp, c_per, len(panel_cells)),
        }
        for k in ("t_track", "t_cell"):
            s = out["pit_universe"][k]
            print(f"{k}: units total={s['units_total_in_panel']} pit_units min/med/max="
                  f"{s['pit_units_min']}/{s['pit_units_median']}/{s['pit_units_max']} "
                  f"rows_not_pit={s['rows_not_pit_eligible']} ({s['rows_not_pit_share']:.2%})")
            print("   requested origins:", s["requested_origins"])
        # distribution of the eligibility delay in quarters
        for nm, d in (("t_track", tp), ("t_cell", cp)):
            delay = (d["first_feat_q"] - d["first_event_q"]).apply(lambda x: x.n)
            unit_delay = delay.groupby([d[c] for c in (
                TRACK_ENTITY if nm == "t_track" else CELL_ENTITY)]).first()
            out["pit_universe"][nm]["first_lag_delay_quarters"] = {
                "row_level_min": int(delay.min()), "row_level_median": float(delay.median()),
                "row_level_max": int(delay.max()),
                "row_counts": {str(k): int(v) for k, v in delay.value_counts().sort_index().items()},
                "unit_counts": {str(k): int(v) for k, v in
                                unit_delay.value_counts().sort_index().items()},
            }
            print(f"   {nm} first-availability delay (quarters):",
                  out["pit_universe"][nm]["first_lag_delay_quarters"])

        # ============================================================ 5. future-first cells
        sec("5. Future-first company x track cells (> 2014Q1)")
        first_dev_q = cell_dev_q.rename("first_device_q").reset_index()
        first_feat_dev_q = ev_lag[ev_lag.kind.isin(pc.DEVICE_KINDS)].groupby(
            CELL_ENTITY, observed=True)["feat_q"].min().rename("first_device_feat_q").reset_index()
        cellinfo = (cell_first_q.rename("first_event_q_check").reset_index()
                    .merge(first_dev_q, on=CELL_ENTITY, how="left")
                    .merge(first_feat_dev_q, on=CELL_ENTITY, how="left"))
        ci = cp.merge(cellinfo, on=CELL_ENTITY, how="left")
        cut = pd.Period("2014Q1", "Q")
        first_after = ci.first_event_q_check > cut
        dev_after = ci.first_device_q.notna() & (ci.first_device_q > cut)
        no_dev_ever = ci.first_device_q.isna()
        rows_before_first_event = int((ci.quarter < ci.first_event_q_check).sum())
        rows_before_dev = int(((ci.quarter < ci.first_device_q) & ci.first_device_q.notna()).sum())
        out["future_first"] = {
            "panel_cells": int(len(cell_flags)),
            "cells_first_appear_after_2014Q1_any_event": int(
                ci[first_after].groupby(CELL_ENTITY).ngroups),
            "cells_first_device_event_after_2014Q1": int(
                ci[dev_after].groupby(CELL_ENTITY).ngroups),
            "cells_with_no_device_event_ever": int(ci[no_dev_ever].groupby(CELL_ENTITY).ngroups),
            "v1_rows_before_cell_first_event": rows_before_first_event,
            "v1_negative_rows_at_origins_before_first_event": int(
                ((ci.quarter < ci.first_event_q_check) & ci.labeled & (ci.y == 0)).sum()),
            "v1_rows_at_origins_before_first_device_event (device-naive)": rows_before_dev,
            "v1_negative_rows_at_origins_before_first_device_event": int(
                ((ci.quarter < ci.first_device_q) & ci.first_device_q.notna()
                 & ci.labeled & (ci.y == 0)).sum()),
            "late_cells_negatives_before_own_first_device": int(
                (dev_after & (ci.quarter < ci.first_device_q) & ci.labeled & (ci.y == 0)).sum()),
            "interpretation": "v1 already excludes rows before a cell's first EVENT quarter, so a "
                              "PIT rule adds no exclusions there (count 0 by construction). "
                              "Rows before a cell's first DEVICE event are included as negatives "
                              "by v1; excluding them would need future knowledge (hindsight "
                              "rule, not PIT).",
        }
        print(out["future_first"])

        # ============================================================ 6. zero-history tracks
        sec("6. Zero-history / emerging tracks (trailing-8Q device count == 0)")
        tp["prev_cum"] = tp["f_n_device_cum"] - tp["f_n_device_sum8"]
        zero = tp[tp["f_n_device_sum8"] == 0]
        never = zero[zero["f_n_device_cum"] == 0]
        dormant = zero[zero["f_n_device_cum"] > 0]
        lab = tp[tp.labeled]
        zero_lab = zero[zero.labeled]
        out["zero_history_tracks"] = {
            "definition": "panel row with f_n_device_sum8 == 0 (feature-clock trailing 8 "
                          "quarters including current); dormant = had earlier device "
                          "activity (cum - sum8 > 0); never = cum == 0",
            "all_panel_rows": int(len(tp)),
            "rows_trailing8_zero": int(len(zero)),
            "rows_trailing8_zero_share": float(len(zero) / len(tp)),
            "labeled_rows_trailing8_zero": int(len(zero_lab)),
            "dormant": {"rows": int(len(dormant)), "labeled_rows": int(dormant.labeled.sum()),
                        "positives": int(dormant.is_pos.sum()),
                        "mean_y": float(dormant.y.mean()),
                        "tracks": int(dormant.track_id.nunique())},
            "never_yet_active": {"rows": int(len(never)), "labeled_rows": int(never.labeled.sum()),
                                 "positives": int(never.is_pos.sum()),
                                 "mean_y": float(never.y.mean()),
                                 "tracks": int(never.track_id.nunique()),
                                 "rows_device_tracks": int(never.is_device_track.sum()),
                                 "rows_t_star_tracks": int((~never.is_device_track).sum()),
                                 "labeled_rows_device_tracks": int(
                                     (never.is_device_track & never.labeled).sum()),
                                 "labeled_rows_t_star_tracks": int(
                                     ((~never.is_device_track) & never.labeled).sum())},
            "all_zero_history_label_rate": float(zero_lab.y.mean()),
            "non_zero_history_label_rate": float(lab[lab.f_n_device_sum8 > 0].y.mean()),
            "zero_history_share_of_negative_pool": float(
                (zero_lab.y == 0).sum() / (lab.y == 0).sum()),
            "tracks_with_labeled_rows_in_never_yet_active_stratum": sorted(
                never.loc[never.labeled, "track_id"].unique().tolist()),
            "n_tracks_with_labeled_rows_in_never_yet_active_stratum": int(
                never.loc[never.labeled, "track_id"].nunique()),
            "tracks_with_zero_device_events_ever": sorted(
                set(panel["track_id"].unique()) - set(dev_track_ids)),
            "warmup_note": "every device track starts with a run of never-yet-active rows: "
                           "the first event is at best observable one quarter later and the "
                           "trailing-8Q sum needs 8 more quarters; 21 t_* tracks are "
                           "never-yet-active for their entire panel life",
        }
        print(out["zero_history_tracks"])

        # ============================================================ 7. attribution coverage
        sec("7. Company-attribution coverage of device events")
        attr = pd.read_sql_query(
            """select kind, event_date, company_key, track_id from events
               where kind in ('510k','pma') and event_date is not null""", con)
        attr["dt"] = pd.to_datetime(attr["event_date"])
        attr["yr"] = attr.dt.dt.year
        attr["tracked"] = attr.track_id.notna()
        attr["attributed"] = attr.track_id.notna() & attr.company_key.notna()
        win = attr[(attr.dt >= pc.PANEL_START) & (attr.dt <= pc.PANEL_END)].copy()
        rows = []
        for y in range(2004, 2026):
            d = win[win.yr == y]
            rows.append({
                "year": y,
                "device_events": int(len(d)),
                "tracked_device_events": int(d.tracked.sum()),
                "attributed_device_events": int(d.attributed.sum()),
                "attributed_over_all_device": float(d.attributed.mean()),
                "attributed_over_tracked": float(d.attributed.sum() / max(d.tracked.sum(), 1)),
            })
        by_year = pd.DataFrame(rows)
        out["attribution_by_year"] = by_year.to_dict("records")
        print(by_year.to_string(index=False))
        r = by_year["attributed_over_tracked"].to_numpy(float)
        r_all = by_year["attributed_over_all_device"].to_numpy(float)
        yr = by_year["year"].to_numpy(float)
        from scipy.stats import spearmanr
        rho = spearmanr(yr, r)
        rho_all = spearmanr(yr, r_all)
        out["attribution_trend"] = {
            "window": [2004, 2025],
            "rate_definition_A": "attributed device events / device events WITH track_id",
            "rate_definition_B": "attributed device events / ALL device events",
            "spearman_year_vs_rate_A": {"rho": float(rho.statistic), "p": float(rho.pvalue)},
            "spearman_year_vs_rate_B": {"rho": float(rho_all.statistic),
                                        "p": float(rho_all.pvalue)},
            "ols_slope_pp_per_year_A": float(np.polyfit(yr, r, 1)[0] * 100.0),
            "ols_slope_pp_per_year_B": float(np.polyfit(yr, r_all, 1)[0] * 100.0),
            "mean_2004_2008_A": float(r[:5].mean()),
            "mean_2019_2025_A": float(r[-7:].mean()),
            "ratio_late_over_early_A": float(r[-7:].mean() / r[:5].mean()),
            "mean_2004_2008_B": float(r_all[:5].mean()),
            "mean_2019_2025_B": float(r_all[-7:].mean()),
            "ratio_late_over_early_B": float(r_all[-7:].mean() / r_all[:5].mean()),
            "min_year_B": int(by_year.loc[by_year.attributed_over_all_device.idxmin(), "year"]),
            "max_year_B": int(by_year.loc[by_year.attributed_over_all_device.idxmax(), "year"]),
            "min_rate_B": float(by_year.attributed_over_all_device.min()),
            "max_rate_B": float(by_year.attributed_over_all_device.max()),
        }
        print("trend:", out["attribution_trend"])
        # per-track attribution over window
        tr = win[win.tracked].groupby("track_id").agg(
            tracked=("attributed", "size"), attributed=("attributed", "sum"))
        tr["rate"] = tr.attributed / tr.tracked
        tr = tr.sort_values("rate")
        out["attribution_by_track"] = {k: {"tracked": int(v.tracked),
                                           "attributed": int(v.attributed),
                                           "rate": float(v.rate)}
                                       for k, v in tr.iterrows()}
        print(tr.to_string())
        # aggregate loss
        dev_total_db = int(len(attr))
        attr_db = int(attr.attributed.sum())
        tracked_db = int(attr.tracked.sum())
        out["attribution_aggregate"] = {
            "dbwide_device_events": dev_total_db,
            "dbwide_tracked": tracked_db,
            "dbwide_attributed": attr_db,
            "dbwide_attributed_over_all": attr_db / dev_total_db,
            "dbwide_attributed_over_tracked": attr_db / tracked_db,
            "window_device_events": int(len(win)),
            "window_tracked": int(win.tracked.sum()),
            "window_attributed": int(win.attributed.sum()),
            "window_attributed_over_all": float(win.attributed.mean()),
            "window_attributed_over_tracked": float(win.attributed.sum() / win.tracked.sum()),
            "v1_kept_events_over_all_db_events": out["v1_keep"]["v1_share_of_all_db"],
            "pre2004_device_events": int((attr.dt < pc.PANEL_START).sum()),
            "pre2004_tracked": int(((attr.dt < pc.PANEL_START) & attr.tracked).sum()),
            "pre2004_attributed": int(((attr.dt < pc.PANEL_START) & attr.attributed).sum()),
        }
        print("aggregate:", json.dumps(out["attribution_aggregate"], indent=1))
        # panel composition by year (does the negative pool shift?)
        py = cp.groupby(cp.quarter.dt.year if hasattr(cp.quarter, "dt") else
                        cp.quarter.astype(str).str.slice(0, 4).astype(int)).agg(
            rows=("y", "size"), pos=("is_pos", "sum"))
        out["cell_panel_rows_by_year"] = {int(k): {"rows": int(v.rows), "pos": int(v.pos)}
                                          for k, v in py.iterrows()}

        # ============================================================ 8. taxonomy backfill
        sec("8. Frozen current taxonomy backfilled onto historical events")
        dmet = pd.read_sql_query(
            """select kind, event_date, track_id, product_code from events
               where kind in ('510k','pma') and event_date is not null""", con)
        dmet["dt"] = pd.to_datetime(dmet["event_date"])
        dmet["q"] = dmet.dt.dt.to_period("Q")
        pcmap = pd.read_sql_query("select product_code, track_id from product_codes", con)
        mm = dmet[dmet.product_code.notna()].merge(pcmap, on="product_code", how="left",
                                                   suffixes=("", "_pc"))
        mapped = mm.track_id_pc.notna()
        both = mapped & mm.track_id.notna()
        agree = int((mm.track_id == mm.track_id_pc)[both].sum())
        pc_row = mm.product_code.notna() & mm.product_code.isin(set(pcmap.product_code))
        pc_row_track_null = pc_row & ~mapped
        tracked = dmet.track_id.notna()
        ft = dmet[dmet.track_id.notna()].groupby("track_id").q.min()
        out["taxonomy_backfill"] = {
            "tracks_table_updated_at": tracks_tbl["updated_at"].value_counts().to_dict(),
            "product_codes_rows": int(len(pcmap)),
            "product_codes_null_track_id": int(pcmap.track_id.isna().sum()),
            "product_codes_updated_at": dict(pd.read_sql_query(
                "select updated_at, count(*) n from product_codes group by updated_at", con)
                .values.tolist()),
            "product_code_to_track_rule": {
                "device_events_with_product_code": int(mm.shape[0]),
                "product_code_found_in_product_codes": int(pc_row.sum()),
                "events_with_track_id_and_pc_track": int(both.sum()),
                "pc_track_equals_event_track": agree,
                "agreement_rate": agree / int(both.sum()) if both.sum() else None,
                "tracked_events_with_pc_row_but_pc_track_null": int(
                    (pc_row_track_null & mm.track_id.notna()).sum()),
                "device_events_with_track_id_but_no_pc_row": int(
                    (dmet.track_id.notna() & ~dmet.product_code.isin(
                        set(pcmap.product_code))).sum()),
            },
            "first_tracked_device_quarter_per_track": {str(k): str(v) for k, v in ft.items()},
            "n_tracks_first_device_q_1976Q3": int((ft == pd.Period("1976Q3", "Q")).sum()),
            "n_tracks_first_device_q_before_1977": int((ft < pd.Period("1977Q1", "Q")).sum()),
            "n_tracks_first_device_q_before_2004": int((ft < pd.Period("2004Q1", "Q")).sum()),
            "n_device_tracks": int(len(ft)),
            "share_tracked_device_events_pre2004": float(
                out["attribution_aggregate"]["pre2004_tracked"] / tracked_db),
            "distinct_device_tracks_active_at": {
                str(q): int(dmet[dmet.track_id.notna() & (dmet.q == pd.Period(q, "Q"))]
                            .track_id.nunique())
                for q in ("2004Q1", "2010Q1", "2020Q1", "2025Q2")},
            "t_star_tracks_first_panel_quarter": dict(
                ev[ev.track_id.isin(out.get("t_track_tables", {}).get(
                    "t_star_ids_in_panel", []))]
                .groupby("track_id")["quarter"].min().astype(str)),
            "pre2004_device_events_with_track_id": out["attribution_aggregate"]["pre2004_tracked"],
            "pre2004_device_events_total": out["attribution_aggregate"]["pre2004_device_events"],
            "unknown": [
                "no historical taxonomy snapshot / version history exists in the DB "
                "(tracks has one row per track and one updated_at; product_codes likewise)",
                "the assignment timestamp per event is not stored; only tracks.updated_at "
                "and product_codes.updated_at (both 2026-10-30) bound it",
                "the keyword/product rules that produced track_id for events without a "
                "product_codes row are not stored, so their counterfactual historical "
                "assignment cannot be reconstructed or falsified",
                "it is therefore NOT measurable whether a given 2004-2013 event would have "
                "been assigned to the same track by an analyst in 2004-2013",
            ],
        }
        print(json.dumps(out["taxonomy_backfill"], indent=1, default=str))

        # ---------------------------------------------------------------- save
        out["elapsed_sec"] = round(time.time() - t0, 1)
        outp = HERE / "b_riskset.json"
        outp.write_text(json.dumps(clean(out), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {outp} ({outp.stat().st_size} bytes) in {out['elapsed_sec']}s")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
