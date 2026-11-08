"""PHOENIX-002 data layer: independent track-level panel construction.

This module deliberately re-implements the panel / label / eligibility logic instead
of importing PHOENIX-001's builders.  The replication test (`selftest.py`) checks that
the `attr59` / `v1like` panel reproduces the frozen PHOENIX-001 T-TRACK panel exactly
(row counts, label counts, prevalence).  That gives us an independent implementation
plus a hard equality check against the published artifact.

Nothing here writes to the database.  Every connection is `mode=ro&immutable=1`.
Quarters are handled internally as integer ordinals (2004Q1 -> 0) to avoid pandas
Period comparison pitfalls; the Period column is kept only for grouping/merging/display.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

import protocol as P

HERE = Path(__file__).resolve().parent


# ------------------------------------------------------------------ quarter helpers
def qord(q) -> np.ndarray:
    """Quarter -> integer ordinal (2004Q1 = 0). Accepts Period or PeriodIndex."""
    p = pd.PeriodIndex(q, freq="Q") if not isinstance(q, pd.PeriodIndex) else q
    return ((p.year - 2004) * 4 + (p.quarter - 1)).to_numpy(dtype=np.int64)


def qnum_scalar(q: pd.Period) -> int:
    return (q.year - 2004) * 4 + (q.quarter - 1)


# --------------------------------------------------------------------- provenance
def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest().upper()


def connect_ro(path: Path | str = P.DB_PATH) -> sqlite3.Connection:
    p = Path(path)
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro&immutable=1", uri=True)


def verify_db(verbose: bool = False) -> dict:
    p = Path(P.DB_PATH)
    out = {"db_path": str(p), "exists": p.exists()}
    if not p.exists():
        out.update(status="MISSING", sha256="", sha256_matches_frozen=False)
        return out
    out["size_bytes"] = p.stat().st_size
    out["sha256"] = sha256_file(p)
    out["sha256_matches_frozen"] = out["sha256"] == P.DB_SHA256
    con = connect_ro()
    try:
        out["integrity_check"] = con.execute("pragma integrity_check").fetchone()[0]
    finally:
        con.close()
    out["status"] = "OK" if out["sha256_matches_frozen"] else "SHA256_MISMATCH"
    if verbose:
        print(f"[db] {out['status']} sha256={out['sha256'][:16]}... "
              f"size={out['size_bytes']} integrity={out['integrity_check']}")
    return out


# ------------------------------------------------------------------------ loading
def load_events(kinds: tuple[str, ...] = P.ALL_KINDS,
                require_company: bool = False) -> pd.DataFrame:
    """Load event facts in the frozen window with both clock columns normalized."""
    ph = ",".join("?" for _ in kinds)
    sql = f"""
        select event_id, kind, event_date, available_at, company_key, track_id,
               product_code
        from events
        where kind in ({ph})
          and event_date is not null
          and event_date >= ? and event_date <= ?
    """
    con = connect_ro()
    try:
        df = pd.read_sql_query(sql, con, params=list(kinds) + [P.PANEL_START, P.PANEL_END])
    finally:
        con.close()
    df["event_dt"] = pd.to_datetime(df["event_date"], errors="coerce")
    df["avail_dt"] = pd.to_datetime(df["available_at"], errors="coerce")
    df.loc[df["avail_dt"].isna(), "avail_dt"] = pd.Timestamp("9999-01-01")
    df = df.dropna(subset=["event_dt"]).copy()
    if require_company:
        df = df[df["company_key"].notna()].copy()
    df["quarter"] = df["event_dt"].dt.to_period("Q")
    df["qnum"] = qord(df["quarter"])
    return df.reset_index(drop=True)


def universe_tracks(events: pd.DataFrame, universe: str) -> list[str]:
    """Retrospective track membership. Uses full-sample information: documented."""
    ev = events[events["track_id"].notna()]
    if universe == "attr38":
        m = ev["company_key"].notna() & ev["kind"].isin(P.DEVICE_KINDS)
    elif universe == "track38":
        m = ev["kind"].isin(P.DEVICE_KINDS)
    elif universe == "attr59":
        m = ev["company_key"].notna()
    else:
        raise ValueError(universe)
    return sorted(ev.loc[m, "track_id"].unique())


# -------------------------------------------------------------------- panel build
def _counts_grid(ev: pd.DataFrame, tracks: list[str], clock: str,
                 quarters: pd.PeriodIndex, prefix: str) -> tuple[pd.DataFrame, list[str]]:
    sub = ev[ev[clock].notna() & ev["track_id"].isin(tracks)].copy()
    if sub.empty:
        g = pd.DataFrame(columns=["track_id", "quarter"])
    else:
        g = (sub.groupby(["track_id", clock, "kind"], observed=True)
             .size().unstack("kind", fill_value=0).reset_index())
        rename = {}
        for c in g.columns:
            if c == "track_id":
                continue
            if c == clock:
                rename[c] = "quarter"
            else:
                rename[c] = f"{prefix}n_{c}"
        g = g.rename(columns=rename)
    grid = pd.MultiIndex.from_product([tracks, quarters], names=["track_id", "quarter"])
    out = pd.DataFrame(index=grid).reset_index()
    out = out.merge(g, on=["track_id", "quarter"], how="left")
    count_cols = [c for c in out.columns if c.startswith(f"{prefix}n_")]
    for c in count_cols:
        out[c] = out[c].fillna(0.0)
    return out, count_cols


def build_panel(universe: str, feature_lag: int, mode: str = "v2") -> pd.DataFrame:
    """Dense track x quarter panel with both clocks.

    mode='v1like'  : trims to ORIGIN_END BEFORE labels (reproduces the PHOENIX-001
                     truncation defect; used only for the replication universe attr59).
    mode='v2'      : labels are computed on the full grid out to LABEL_GRID_END, then
                     origin rows are trimmed to ORIGIN_END.  This recovers the four
                     origins 2024Q3..2025Q2 that PHOENIX-001 silently discarded.
    """
    if universe not in P.UNIVERSES:
        raise ValueError(universe)
    require_company = universe in ("attr38", "attr59")
    events = load_events(P.ALL_KINDS, require_company=require_company)
    tracks = universe_tracks(events, universe)
    ev = events[events["track_id"].isin(tracks)].copy()
    ev["feat_dt"] = ev["avail_dt"] + pd.Timedelta(days=int(feature_lag))
    ev["feat_quarter"] = ev["feat_dt"].dt.to_period("Q")

    quarters = pd.period_range(P.ORIGIN_START, P.LABEL_GRID_END, freq="Q")
    lab, _ = _counts_grid(ev, tracks, "quarter", quarters, prefix="")
    fea, fea_cols = _counts_grid(ev, tracks, "feat_quarter", quarters, prefix="f_")
    panel = lab.merge(fea, on=["track_id", "quarter"], how="left")
    for c in fea_cols:
        panel[c] = panel[c].fillna(0.0)

    count_lab = [c for c in panel.columns if c.startswith("n_")]
    count_fea = [c for c in panel.columns if c.startswith("f_n_")]
    panel["n_device"] = panel[[c for c in ("n_510k", "n_pma") if c in panel]].sum(axis=1)
    panel["f_n_device"] = panel[[c for c in ("f_n_510k", "f_n_pma") if c in panel]].sum(axis=1)
    others_lab = [c for c in count_lab if c not in ("n_510k", "n_pma")]
    others_fea = [c for c in count_fea if c not in ("f_n_510k", "f_n_pma")]
    panel["n_total"] = panel[count_lab].sum(axis=1) if others_lab else panel["n_device"]
    panel["f_n_total"] = panel[count_fea].sum(axis=1) if others_fea else panel["f_n_device"]

    panel["qnum"] = qord(panel["quarter"]).astype(np.int64)
    panel = panel.sort_values(["track_id", "qnum"]).reset_index(drop=True)

    # first quarter per track, on both clocks
    dev_lab_q = (panel.loc[panel["n_device"] > 0].groupby("track_id", observed=True)["qnum"].min())
    dev_fea_q = (panel.loc[panel["f_n_device"] > 0].groupby("track_id", observed=True)["qnum"].min())
    any_lab_q = (panel.loc[panel["n_total"] > 0].groupby("track_id", observed=True)["qnum"].min())
    panel["first_event_qnum"] = panel["track_id"].map(any_lab_q).astype("Int64")
    panel["first_dev_feat_qnum"] = panel["track_id"].map(dev_fea_q).astype("Int64")

    if mode == "v1like":
        panel = panel[panel["qnum"] >= panel["first_event_qnum"]].copy()
        panel["exposure_q"] = (panel["qnum"] - panel["first_event_qnum"]).astype(float)
        panel = panel[panel["qnum"] <= qnum_scalar(P.ORIGIN_END)].copy()
        panel = add_targets(panel)
        panel["origin_eligible"] = True
    elif mode == "v2":
        panel = panel[panel["qnum"] >= panel["first_dev_feat_qnum"]].copy()
        panel["exposure_q"] = (panel["qnum"] - panel["first_dev_feat_qnum"]).astype(float)
        panel = add_targets(panel)   # labels on the FULL grid (reaches 2026Q2)
        panel["origin_eligible"] = (
            (panel["exposure_q"] + 1 >= P.MIN_DEVICE_HISTORY_Q)
            & (panel["qnum"] <= qnum_scalar(P.ORIGIN_END))
        )
    else:
        raise ValueError(mode)

    panel["feature_lag"] = int(feature_lag)
    panel["universe"] = universe
    panel["mode"] = mode
    panel = panel[panel["qnum"] <= qnum_scalar(P.LABEL_GRID_END)].copy()
    return panel.sort_values(["track_id", "qnum"]).reset_index(drop=True)


# ------------------------------------------------------------------------ labels
def add_targets(panel: pd.DataFrame) -> pd.DataFrame:
    """Attach the four frozen targets plus every component used to explain them."""
    panel = panel.sort_values(["track_id", "qnum"]).copy()
    g = panel.groupby("track_id", observed=True)

    def gshift(off: int) -> pd.Series:
        return g["n_device"].shift(-off)

    fwd_parts = [gshift(o) for o in range(1, P.HORIZON_Q + 1)]
    arr = np.vstack([s.to_numpy(dtype=float) for s in fwd_parts])
    fwd = np.nansum(arr, axis=0)
    fwd[np.isnan(arr).any(axis=0)] = np.nan
    panel["fwd_total"] = fwd
    panel["trail8_total"] = g["n_device"].transform(
        lambda s: s.rolling(P.HISTORY_Q, min_periods=P.HISTORY_Q).sum())
    panel["trail8_mean"] = panel["trail8_total"] / P.HISTORY_Q
    panel["trail12_mean"] = g["n_device"].transform(
        lambda s: s.rolling(P.HISTORY_Q + 4, min_periods=P.HISTORY_Q + 4).mean())
    panel["trail16_mean"] = g["n_device"].transform(
        lambda s: s.rolling(P.HISTORY_LONG_Q, min_periods=P.HISTORY_LONG_Q).mean())
    panel["fwd_mean"] = panel["fwd_total"] / P.HORIZON_Q

    base_ok = panel["trail8_total"].notna() & panel["fwd_total"].notna()
    long_mean = panel[["trail8_mean", "trail12_mean", "trail16_mean"]].max(axis=1, skipna=True)
    long_ok = base_ok & panel["trail16_mean"].notna()

    y1 = ((panel["fwd_total"] >= 3) & (panel["fwd_mean"] >= 1.5 * panel["trail8_mean"])).where(base_ok)
    y2 = (panel["fwd_total"] > panel["trail8_total"] / 2.0).where(base_ok)
    y3 = ((panel["fwd_total"] >= 3) & (panel["fwd_mean"] >= 1.5 * long_mean)).where(long_ok)
    y4 = ((panel["trail8_total"] == 0) & (panel["fwd_total"] >= 3)).where(base_ok)

    panel["y_Y1_growth_ratio"] = y1.astype(float)
    panel["y_Y2_abs_increase"] = y2.astype(float)
    panel["y_Y3_new_plateau"] = y3.astype(float)
    panel["y_Y4_dormant_emergence"] = y4.astype(float)
    panel["y"] = panel[f"y_{P.PRIMARY_TARGET}"]
    panel["stratum"] = np.where(panel["trail8_total"].fillna(0) > 0, "active", "dormant")
    return panel


# ---------------------------------------------------------------------- diagnostics
def coverage_stats(events: pd.DataFrame) -> dict:
    """Company-attribution coverage of tracked device events, by year and track."""
    dev = events[events["track_id"].notna() & events["kind"].isin(P.DEVICE_KINDS)].copy()
    dev["year"] = dev["event_dt"].dt.year
    dev["attributed"] = dev["company_key"].notna().astype(int)
    by_year = (dev.groupby("year", observed=True)
               .agg(n_device=("event_id", "size"), n_attributed=("attributed", "sum"))
               .reset_index())
    by_year["attribution_rate"] = by_year["n_attributed"] / by_year["n_device"]
    by_year = by_year[(by_year["year"] >= 2004) & (by_year["year"] <= 2025)]
    by_track = (dev.groupby("track_id", observed=True)
                .agg(n_device=("event_id", "size"), n_attributed=("attributed", "sum"))
                .reset_index())
    by_track["attribution_rate"] = by_track["n_attributed"] / by_track["n_device"]
    return {
        "n_tracked_device_events": int(len(dev)),
        "n_attributed": int(dev["attributed"].sum()),
        "overall_attribution_rate": float(dev["attributed"].mean()),
        "by_year": by_year.to_dict(orient="records"),
        "by_track": by_track.sort_values("attribution_rate").to_dict(orient="records"),
        "attribution_min": float(by_track["attribution_rate"].min()),
        "attribution_median": float(by_track["attribution_rate"].median()),
        "n_tracks_below_50pct": int((by_track["attribution_rate"] < 0.5).sum()),
    }


def duplicate_stats(events: pd.DataFrame) -> dict:
    """Duplicate / cross-kind duplicate regulatory records (audit L6)."""
    dev = events[events["track_id"].notna() & events["kind"].isin(P.DEVICE_KINDS)].copy()
    key = ["track_id", "event_dt", "product_code", "kind"]
    dup = dev.duplicated(subset=key, keep=False)
    key2 = ["track_id", "event_dt", "product_code"]
    cross = dev.duplicated(subset=key2, keep=False) & dev["product_code"].notna()
    piv = (dev.dropna(subset=["product_code"])
           .groupby(["product_code", "track_id", "event_dt"], observed=True)["kind"]
           .nunique())
    return {
        "tracked_device_events": int(len(dev)),
        "exact_duplicate_rows_incl_first": int(dup.sum()),
        "exact_duplicate_groups": int(dev[dup].groupby(key, observed=True).ngroups) if dup.any() else 0,
        "same_track_day_product_rows_incl_first": int(cross.sum()),
        "product_same_day_both_510k_and_pma": int((piv > 1).sum()),
    }


if __name__ == "__main__":
    import json
    import time

    t0 = time.time()
    db = verify_db(verbose=True)
    if not db["sha256_matches_frozen"]:
        raise SystemExit("ABORT: database SHA-256 does not match the frozen value")
    ev = load_events()
    print(f"[events] {len(ev)} rows in {P.PANEL_START}..{P.PANEL_END}")
    for uni in P.UNIVERSES:
        print(f"[universe] {uni}: {len(universe_tracks(ev, uni))} tracks")
    cs = coverage_stats(ev)
    print(f"[coverage] overall={cs['overall_attribution_rate']:.4f} "
          f"min={cs['attribution_min']:.3f} median={cs['attribution_median']:.3f} "
          f"tracks<50%={cs['n_tracks_below_50pct']}")
    print("[duplicates]", json.dumps(duplicate_stats(ev)))
    for uni, mode in (("attr59", "v1like"), ("attr38", "v2"), ("track38", "v2")):
        panel = build_panel(uni, P.HEADLINE_FEATURE_LAG, mode)
        for tgt in P.TARGETS:
            y = panel[f"y_{tgt}"]
            print(f"[panel] {uni}/{mode} lag={P.HEADLINE_FEATURE_LAG} {tgt}: "
                  f"rows={len(panel)} labelled={int(y.notna().sum())} "
                  f"pos={int(np.nansum(y))} prev={np.nanmean(y):.4f} "
                  f"eligible={int(panel['origin_eligible'].sum()) if 'origin_eligible' in panel else '-'}")
    print(f"[done] {time.time() - t0:.1f}s")
