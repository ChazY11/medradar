"""Overlapping-forward-window sensitivity for the PHOENIX-002 primary contrast.

Protocol §7.3 promises a non-overlapping-origin sensitivity in addition to the
track-clustered bootstrap.  Consecutive origins share 3 of their 4 forward quarters;
keeping only Q1 origins removes that overlap (each Q1 origin's forward window ends
before the next Q1 origin's window starts).

Run:  python sensitivity_overlap.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import metrics as M
import protocol as P

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def main() -> int:
    out = {"analysis": "OVERLAP_SENSITIVITY", "protocol_version": P.PROTOCOL_VERSION,
           "db_sha256": P.DB_SHA256,
           "note": "Q1-only origins are non-overlapping (4-quarter forward windows). "
                   "This is a sensitivity check; the headline uses all origins with a "
                   "track-clustered bootstrap."}
    for name, path in (("primary_attr38", RESULTS / "oof_primary.csv"),
                       ("published_attr59", RESULTS / "oof_attr59_purged.csv")):
        d = pd.read_csv(path)
        d["quarter"] = d["quarter"].astype(str)
        q1 = d[d["quarter"].str.endswith("Q1")].copy()
        rec = {}
        for label, sub in (("all_origins", d), ("q1_only_non_overlapping", q1)):
            y = sub["y"].to_numpy(float)
            a = sub["M4_h8_growth"].to_numpy(float)
            b = sub["M1_persistence"].to_numpy(float)
            c = M.paired_bootstrap_diff(y, a, b, sub["track_id"].to_numpy(), B=P.B_BOOT,
                                        seed=P.SEED)
            rec[label] = {
                "n": int(len(sub)), "n_pos": int(np.nansum(y)),
                "prevalence": float(np.nanmean(y)),
                "ap_M1": c["ap_b"], "ap_M4": c["ap_a"],
                "dap": c["diff"], "ci95": [c["lo"], c["hi"]], "p": c["p"],
                "n_tracks": int(sub["track_id"].nunique()),
            }
        out[name] = rec
        print(f"[{name}]")
        for label, r in rec.items():
            print(f"  {label:26s} n={r['n']:5d} pos={r['n_pos']:4d} "
                  f"dAP={r['dap']:+.4f} CI=[{r['ci95'][0]:+.4f},{r['ci95'][1]:+.4f}] p={r['p']:.4f}")
    (RESULTS / "sensitivity_overlap.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=float), encoding="utf-8")
    print("wrote results/sensitivity_overlap.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
