"""Stage 2 — per (track, quarter) entrant / concentration block for H3 and H6.

One command:
    python experiments/phoenix/hypotheses/track/entrants_hhi.py

Computes, for every track x quarter on BOTH clocks:

FEATURE clock (available_at + lag) — these are the only ones the models may see:
    ent_q, ent_new4, ent_new8, ent_cum       new companies (first-ever feature-clock
                                             event in that track), current / trailing
                                             4Q / trailing 8Q / cumulative
    n_active_q, n_active4                    companies active in q / in the trailing
                                             4Q window (span-based, no double count)
    ent_share4                               ent_new4 / max(n_active4, 1)
    hhi_q                                    HHI of that quarter's event shares (T-HHI,
                                             frozen definition: quarterly event shares,
                                             within track, company_key non-null only)
    hhi_q_fill                               hhi_q carried forward when undefined
    hhi4                                     HHI pooling the trailing 4 quarters' events
    d_hhi4, d_hhi8                           hhi_q_fill - 4Q / 8Q lag
    d_hhi4_pool                              hhi4 - 4Q lag
    dev_hhi_q, d_dev_hhi4                    device-only (510k+pma) sensitivity
    n_events_q                               all events in q on the feature clock

EVENT clock (lag-independent, DESCRIPTIVE ONLY — never used as a feature):
    ent_q_ev, ent_fwd4                       entrants in q / in (q, q+4]
    hhi_ev, d_hhi4_ev, d_hhi4_fwd4           HHI level, trailing change, forward change
    dev_q_ev, dev_rate_fwd4                  device events in q / forward-4Q rate

Writes cache/entrants_hhi_L{lag}.csv and results/entrants_hhi_summary.json.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

import track_common as tc
import phoenix_common as pc

QUARTERS = pc.quarter_range(pc.ORIGIN_START, pc.ORIGIN_END)
QIDX = {q: i for i, q in enumerate(QUARTERS)}
NQ = len(QUARTERS)


def quarter_ordinal(quarters: pd.Series) -> np.ndarray:
    return np.array([QIDX.get(q, -1) for q in quarters], dtype=int)


def hhi_from_counts(counts: np.ndarray) -> float:
    """HHI = sum of squared shares. Undefined (NaN) when the quarter has no events."""
    total = counts.sum()
    if total <= 0:
        return float("nan")
    s = counts / total
    return float((s**2).sum())


def _per_track_feature_quarter(ev_lag: pd.DataFrame, track_ids: list[str]) -> dict:
    """Per-track dense arrays on the FEATURE clock."""
    out: dict = {}
    for tid in track_ids:
        sub = ev_lag[ev_lag["track_id"] == tid]
        # entrant = first-ever feature-clock event of a company inside this track
        first = sub.groupby("company_key", observed=True)["feat_quarter"].min()
        last = sub.groupby("company_key", observed=True)["feat_quarter"].max()
        first_i = np.array([QIDX.get(q, -1) for q in first.to_numpy()], dtype=int)
        last_i = np.array([QIDX.get(q, -1) for q in last.to_numpy()], dtype=int)
        ent_q = np.zeros(NQ, dtype=float)
        for i in first_i:
            if i >= 0:
                ent_q[i] += 1.0
        # active companies per quarter + per trailing-4Q window (span based)
        active_q = np.zeros(NQ, dtype=float)
        active4 = np.zeros(NQ, dtype=float)
        for q in range(NQ):
            active_q[q] = float(((first_i <= q) & (last_i >= q)).sum())
            active4[q] = float(((first_i <= q) & (last_i >= q - 3)).sum())
        # HHI from event shares
        gq = sub.groupby(["feat_quarter", "company_key"], observed=True).size()
        hhi_q = np.full(NQ, np.nan)
        dev_q = np.zeros(NQ, dtype=float)
        for q, i in QIDX.items():
            try:
                counts = gq.xs(q, level="feat_quarter").to_numpy(dtype=float)
            except KeyError:
                continue
            hhi_q[i] = hhi_from_counts(counts)
        # device-only HHI and quarterly device event counts
        dev = sub[sub["kind"].isin(pc.DEVICE_KINDS)]
        gq_dev = dev.groupby(["feat_quarter", "company_key"], observed=True).size()
        hhi_dev = np.full(NQ, np.nan)
        for q, i in QIDX.items():
            try:
                counts = gq_dev.xs(q, level="feat_quarter").to_numpy(dtype=float)
            except KeyError:
                continue
            hhi_dev[i] = hhi_from_counts(counts)
        n_events = sub.groupby("feat_quarter", observed=True).size()
        for q, i in QIDX.items():
            dev_q[i] = float(n_events.get(q, 0))
        out[tid] = {
            "ent_q": ent_q, "active_q": active_q, "active4": active4,
            "hhi_q": hhi_q, "hhi_dev": hhi_dev, "n_events_q": dev_q,
            "first_i": first_i, "last_i": last_i,
        }
    return out


def _per_track_event_quarter(ev: pd.DataFrame, track_ids: list[str]) -> dict:
    out: dict = {}
    for tid in track_ids:
        sub = ev[ev["track_id"] == tid]
        first = sub.groupby("company_key", observed=True)["quarter"].min()
        first_i = np.array([QIDX.get(q, -1) for q in first.to_numpy()], dtype=int)
        ent_q = np.zeros(NQ, dtype=float)
        for i in first_i:
            if i >= 0:
                ent_q[i] += 1.0
        gq = sub.groupby(["quarter", "company_key"], observed=True).size()
        hhi_q = np.full(NQ, np.nan)
        for q, i in QIDX.items():
            try:
                counts = gq.xs(q, level="quarter").to_numpy(dtype=float)
            except KeyError:
                continue
            hhi_q[i] = hhi_from_counts(counts)
        dev = sub[sub["kind"].isin(pc.DEVICE_KINDS)]
        dev_q = np.zeros(NQ, dtype=float)
        for q, i in QIDX.items():
            dev_q[i] = float(dev[dev["quarter"] == q].shape[0])
        out[tid] = {"ent_q_ev": ent_q, "hhi_ev": hhi_q, "dev_q_ev": dev_q}
    return out


def _trailing(a: np.ndarray, w: int) -> np.ndarray:
    s = pd.Series(a).rolling(w, min_periods=1).sum().to_numpy()
    return s


def _lagged(a: np.ndarray, w: int) -> np.ndarray:
    out = np.full_like(a, np.nan, dtype=float)
    if w < len(a):
        out[w:] = a[:-w]
    return out


def _forward_window(a: np.ndarray, w: int) -> np.ndarray:
    out = np.full_like(a, np.nan, dtype=float)
    for i in range(len(a)):
        j = min(i + w, len(a) - 1)
        seg = a[i + 1:j + 1]
        out[i] = seg.sum() if len(seg) >= w else np.nan
    return out


def build_block(events: pd.DataFrame, lag: int) -> pd.DataFrame:
    ev_lag = pc.apply_lag(events, lag)
    track_ids = sorted(events["track_id"].dropna().unique())
    feat = _per_track_feature_quarter(ev_lag, track_ids)
    evc = _per_track_event_quarter(events, track_ids)

    rows = []
    for tid in track_ids:
        f = feat[tid]
        e = evc[tid]
        # fill hhi_q forward, then backward for the very first quarters
        hhi_fill = pd.Series(f["hhi_q"]).ffill().bfill().to_numpy(dtype=float)
        ent_new4 = _trailing(f["ent_q"], 4)
        ent_new8 = _trailing(f["ent_q"], 8)
        ent_cum = np.cumsum(f["ent_q"])
        ent_share4 = ent_new4 / np.maximum(f["active4"], 1.0)
        dev_hhi_fill = pd.Series(f["hhi_dev"]).ffill().bfill().to_numpy(dtype=float)
        for i in range(NQ):
            q = QUARTERS[i]
            rows.append({
                "track_id": tid,
                "quarter": str(q),
                "qi": i,
                "lag_days": int(lag),
                # ---- feature clock
                "ent_q": f["ent_q"][i],
                "ent_new4": ent_new4[i],
                "ent_new8": ent_new8[i],
                "ent_cum": ent_cum[i],
                "n_active_q": f["active_q"][i],
                "n_active4": f["active4"][i],
                "ent_share4": ent_share4[i],
                "hhi_q": f["hhi_q"][i],
                "hhi_q_fill": hhi_fill[i],
                "d_hhi4": hhi_fill[i] - (hhi_fill[i - 4] if i >= 4 else np.nan),
                "d_hhi8": hhi_fill[i] - (hhi_fill[i - 8] if i >= 8 else np.nan),
                "dev_hhi_q": f["hhi_dev"][i],
                "dev_hhi_q_fill": dev_hhi_fill[i],
                "d_dev_hhi4": dev_hhi_fill[i] - (dev_hhi_fill[i - 4] if i >= 4 else np.nan),
                "n_events_q": f["n_events_q"][i],
                # ---- event clock (descriptive)
                "ent_q_ev": e["ent_q_ev"][i],
                "ent_fwd4": _forward_window(e["ent_q_ev"], 4)[i],
                "hhi_ev": e["hhi_ev"][i],
                "d_hhi4_ev": (e["hhi_ev"][i] - e["hhi_ev"][i - 4]) if i >= 4 else np.nan,
                "d_hhi4_fwd4": (e["hhi_ev"][i + 4] - e["hhi_ev"][i]) if i + 4 < NQ else np.nan,
                "dev_q_ev": e["dev_q_ev"][i],
                "dev_fwd4_ev": _forward_window(e["dev_q_ev"], 4)[i],
            })
    df = pd.DataFrame(rows)

    # pooled trailing-4Q HHI: shares of the pooled 4-quarter company event counts
    ev_lag2 = ev_lag.copy()
    hhi4_map = {}
    for tid in track_ids:
        sub = ev_lag2[ev_lag2["track_id"] == tid]
        g = sub.groupby(["company_key", "feat_quarter"], observed=True).size()
        companies = sorted(sub["company_key"].dropna().unique())
        if not companies:
            continue
        cidx = {c: k for k, c in enumerate(companies)}
        mat = np.zeros((len(companies), NQ))
        for (c, q), n in g.items():
            i = QIDX.get(q)
            if i is not None:
                mat[cidx[c], i] = n
        for i in range(NQ):
            pooled = mat[:, max(0, i - 3):i + 1].sum(axis=1)
            tot = pooled.sum()
            hhi4_map[(tid, i)] = float(((pooled / tot) ** 2).sum()) if tot > 0 else np.nan
    df["hhi4"] = [hhi4_map.get((r.track_id, int(r.qi)), np.nan) for r in df.itertuples()]
    df["d_hhi4_pool"] = np.nan
    for tid, idx in df.groupby("track_id", observed=True).indices.items():
        idx = np.sort(np.asarray(idx))
        v = df.loc[idx, "hhi4"].to_numpy(dtype=float)
        d = np.full(len(v), np.nan)
        d[4:] = v[4:] - v[:-4]
        df.loc[idx, "d_hhi4_pool"] = d
    return df


def main(log: tc.RunLog) -> int:
    t0 = time.time()
    db = tc.db_meta()
    if not db["db_sha256_matches_frozen"]:
        log.write("ABORT: db sha256 mismatch")
        return 2
    con = pc.connect_ro()
    try:
        ev = pc.load_events(con)
        # source coverage: how many events of each kind even carry a track_id?
        cov = pd.read_sql_query(
            """select kind, count(*) as n,
                      sum(case when track_id is not null then 1 else 0 end) as n_with_track,
                      sum(case when company_key is not null then 1 else 0 end) as n_with_company,
                      sum(case when track_id is not null and company_key is not null
                               then 1 else 0 end) as n_with_both
               from events
               where event_date >= '2004-01-01' and event_date <= '2026-10-30'
               group by kind order by kind""",
            con,
        )
    finally:
        con.close()
    log.step(f"events={len(ev)} tracks={ev['track_id'].nunique()}")

    cov_rec = cov.to_dict(orient="records")
    log.step("source coverage (track_id availability): "
             + "; ".join(f"{r['kind']}={r['n_with_track']}/{r['n']}" for r in cov_rec))

    summary = {
        "protocol_version": pc.PROTOCOL_VERSION,
        "db_sha256": db["db_sha256"],
        "db_sha256_matches_frozen": db["db_sha256_matches_frozen"],
        "command": tc.command_line(),
        "lag_scenario": "L000+L090+L180 (feature-clock columns per lag; event-clock "
                        "descriptive columns identical across lags)",
        "seed": tc.SEED,
        "n_tracks": int(ev["track_id"].nunique()),
        "n_quarters": NQ,
        "quarters": [str(QUARTERS[0]), str(QUARTERS[-1])],
        "source_coverage": cov_rec,
        "t_entrant_definition": (
            "new entrant = company whose first-ever event in the track (on the feature "
            "clock, i.e. available_at + lag) falls in the quarter; forward variant "
            "ent_fwd4 uses the event clock and is descriptive only"
        ),
        "t_hhi_definition": (
            "sum of squared company shares of that quarter's events inside the track; "
            "company_key non-null events only (frozen track event set); dev_hhi_* "
            "restricts to 510k+pma as a sensitivity"
        ),
        "lags": {},
        "elapsed_sec": None,
    }

    for lag in tc.LAG_SCENARIOS:
        tag = tc.LAG_TAG[lag]
        df = build_block(ev, lag)
        path = tc.CACHE_DIR / f"entrants_hhi_{tag}.csv"
        tc.write_csv(df, path)
        hh = df.dropna(subset=["hhi_q"])
        summary["lags"][tag] = {
            "lag_scenario": tag,
            "lag_days": int(lag),
            "rows": int(len(df)),
            "csv": tc._rel(path),
            "n_quarters_hhi_defined": int(len(hh)),
            "share_quarters_hhi_defined": float(len(hh) / len(df)),
            "hhi_q_mean": float(hh["hhi_q"].mean()) if len(hh) else float("nan"),
            "hhi_q_median": float(hh["hhi_q"].median()) if len(hh) else float("nan"),
            "hhi4_mean": float(df["hhi4"].mean(skipna=True)),
            "n_active4_mean": float(df["n_active4"].mean()),
            "ent_new4_mean": float(df["ent_new4"].mean()),
            "ent_q_ev_mean": float(df["ent_q_ev"].mean()),
            "share_track_quarters_with_entrant": float((df["ent_q_ev"] > 0).mean()),
            "share_track_quarters_with_entrant_featclock": float((df["ent_q"] > 0).mean()),
        }
        log.step(f"{tag}: wrote {tc._rel(path)} ({len(df)} rows) in {(time.time()-t0):.1f}s")

    summary["elapsed_sec"] = round(time.time() - t0, 2)
    summary["n"] = int(summary["lags"]["L090"]["rows"])
    summary["n_pos"] = int(summary["lags"]["L090"]["n_quarters_hhi_defined"])
    summary["prevalence"] = float(summary["lags"]["L090"]["share_quarters_hhi_defined"])
    tc.save(summary, tc.RESULTS_DIR / "entrants_hhi_summary.json")
    log.step(f"wrote {tc._rel(tc.RESULTS_DIR / 'entrants_hhi_summary.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(tc.run_script("02_entrants_hhi", main))
