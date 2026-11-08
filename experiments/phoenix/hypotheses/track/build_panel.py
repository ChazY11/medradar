"""Stage 1 — build the frozen T-TRACK panel for lag in {0, 90, 180} days.

One command:
    python experiments/phoenix/hypotheses/track/build_panel.py [--force]

Writes:
    cache/track_panel_L000.pkl / L090 / L180   (pandas pickle; pyarrow absent)
    results/panel_facts.json

The panel definition is frozen (PHOENIX_FROZEN_PROTOCOL §2.2):
  entity = track_id (59 tracks that have company x track events)
  y = 1 iff forward-4Q mean device rate >= 1.5 x trailing-8Q mean AND forward
      device total >= 3
Feature clock = available_at + lag_days (never event_date); label clock = event_date.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

import track_common as tc
import phoenix_common as pc


def main(log: tc.RunLog, force: bool) -> int:
    t0 = time.time()
    db = tc.db_meta()
    log.step(f"db sha256 {db['db_sha256']} matches_frozen={db['db_sha256_matches_frozen']}")
    if not db["db_sha256_matches_frozen"]:
        log.write("ABORT: database SHA-256 does not match the frozen protocol value.")
        return 2

    con = pc.connect_ro()
    try:
        ev = pc.load_events(con)
    finally:
        con.close()
    log.step(f"events loaded: {len(ev)} rows, {ev['kind'].nunique()} kinds, "
             f"tracks={ev['track_id'].nunique()} companies={ev['company_key'].nunique()}")
    log.step(f"events by kind: {ev['kind'].value_counts().to_dict()}")

    facts: dict = {
        "protocol_version": pc.PROTOCOL_VERSION,
        "harness_version": pc.HARNESS_VERSION,
        "db_sha256": db["db_sha256"],
        "db_sha256_matches_frozen": db["db_sha256_matches_frozen"],
        "command": tc.command_line(),
        "lag_scenario": "L000+L090+L180 (all three built; headline is L090)",
        "seed": tc.SEED,
        "entity": "track_id",
        "target": "growth",
        "target_definition": (
            "y=1 iff forward-4Q mean device (510k+pma) event rate >= 1.5 x trailing-8Q "
            "mean AND forward-4Q device total >= 3; device events restricted to rows "
            "with BOTH company_key and track_id non-null (frozen entity universe)"
        ),
        "walk_forward": "test years 2014..2025, expanding train window",
        "lags": {},
    }

    for lag in tc.LAG_SCENARIOS:
        tag = tc.LAG_TAG[lag]
        t1 = time.time()
        if force or not tc.panel_path(lag).exists():
            panel = tc.build_track_panel(ev, lag)
            panel.to_pickle(tc.panel_path(lag))
            src = "built"
        else:
            panel = pd.read_pickle(tc.panel_path(lag))
            src = "cache"
        y = panel["y"]
        fcols = [c for c in panel.columns if c.startswith(("f_n_", "sct_", "b2_"))]
        facts["lags"][tag] = {
            "lag_scenario": tag,
            "lag_days": int(lag),
            "source": src,
            "n": int(len(panel)),
            "n_labeled": int(y.notna().sum()),
            "n_pos": int(np.nansum(y)),
            "prevalence": float(np.nanmean(y)),
            "n_tracks": int(panel["track_id"].nunique()),
            "quarters": [str(panel["quarter"].min()), str(panel["quarter"].max())],
            "n_quarters": int(panel["quarter"].nunique()),
            "n_feature_columns": int(len(fcols)),
            "feature_columns": fcols,
            "n_rows_exposure_lt_8": int((panel["exposure_q"] < 8).sum()),
            "mean_device_events_per_track_quarter": float(panel["n_device"].mean()),
            "elapsed_sec": round(time.time() - t1, 2),
        }
        log.step(f"{tag}: rows={len(panel)} labeled={int(y.notna().sum())} "
                 f"pos={int(np.nansum(y))} prev={float(np.nanmean(y)):.5f} ({src})")

    # sanity: prevalence must reproduce the frozen 05_validity_tests numbers at L090
    ref = {"n": 4904, "n_pos": 406, "prevalence": 0.09541715628672151}
    got = facts["lags"]["L090"]
    facts["frozen_reference_check"] = {
        "reference_from": "experiments/phoenix/reports/05_validity_tests.json (03_harness_smoke)",
        "reference_n": ref["n"],
        "reference_n_pos": ref["n_pos"],
        "reference_prevalence": ref["prevalence"],
        "observed_n": got["n"],
        "observed_n_pos": got["n_pos"],
        "observed_prevalence": got["prevalence"],
        "match": bool(got["n"] == ref["n"] and got["n_pos"] == ref["n_pos"]),
    }
    log.step(f"frozen reference check: {facts['frozen_reference_check']['match']}")

    facts["elapsed_sec"] = round(time.time() - t0, 2)
    facts["n"] = int(facts["lags"]["L090"]["n_labeled"])
    facts["n_pos"] = int(facts["lags"]["L090"]["n_pos"])
    facts["prevalence"] = float(facts["lags"]["L090"]["prevalence"])
    tc.save(facts, tc.RESULTS_DIR / "panel_facts.json")
    log.step(f"wrote {tc._rel(tc.RESULTS_DIR / 'panel_facts.json')} in {facts['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild even if cached")
    a = ap.parse_args()
    raise SystemExit(tc.run_script("01_build_panel", lambda log: main(log, a.force)))
