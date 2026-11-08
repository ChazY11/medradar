"""Quick smoke test: replicate the PHOENIX-001 H8 result with the v2 implementation.

Run:  python _smoke_replication.py
Expected (PHOENIX-001 published): B1 AP 0.1234, H8 AP 0.1613, dAP +0.0379,
95% CI [+0.0115,+0.0618], raw p 0.004, n=2443, n_pos=155, prevalence 6.3447%.
"""
from __future__ import annotations

import json
import time

import numpy as np

import data as D
import features as F
import metrics as M
import protocol as P
import runner as R


def main() -> int:
    t0 = time.time()
    db = D.verify_db(verbose=True)
    assert db["sha256_matches_frozen"], "DB hash mismatch"
    panel = D.build_panel("attr59", P.HEADLINE_FEATURE_LAG, mode="v1like")
    panel = F.build_features(panel)
    print(f"[panel] rows={len(panel)} tracks={panel['track_id'].nunique()} "
          f"labelled={panel['y'].notna().sum()} pos={int(np.nansum(panel['y']))} "
          f"prev={np.nanmean(panel['y']):.6f}  ({time.time()-t0:.1f}s)")

    res, oof = R.run_config(panel, f"y_{P.PRIMARY_TARGET}", "v1_naive", 0,
                            arms=("M0_prevalence", "M1_persistence", "M4_h8_growth"))
    print(f"[wf] n={res['n']} n_pos={res['n_pos']} prevalence={res['prevalence']:.6f} "
          f"tracks={res['n_tracks']} folds={len(res['folds'])}")
    for arm in ("M0_prevalence", "M1_persistence", "M4_h8_growth"):
        a = res["arms"][arm]
        print(f"  {arm:16s} AP={a['ap']:.4f} CI={[round(v,4) for v in a['ap_ci95']]}")
    c = res["contrasts"]["M4_h8_growth - M1_persistence"]
    print(f"  dAP={c['diff']:+.4f} CI=[{c['lo']:+.4f},{c['hi']:+.4f}] p={c['p']:.4f} "
          f"n={c['n']} n_pos={c['n_pos']}")
    pub = {"B1_ap": 0.1234, "H8_ap": 0.1613, "dap": 0.0379, "lo": 0.0115, "hi": 0.0618,
           "p": 0.0040, "n": 2443, "n_pos": 155}
    print("[published]", json.dumps(pub))
    out = {"reproduced": {
        "B1_ap": res["arms"]["M1_persistence"]["ap"],
        "H8_ap": res["arms"]["M4_h8_growth"]["ap"],
        "dap": c["diff"], "lo": c["lo"], "hi": c["hi"], "p": c["p"],
        "n": res["n"], "n_pos": res["n_pos"], "prevalence": res["prevalence"]},
        "maturity_v1_naive_L000": res["maturity"]["total_violating_share"],
        "elapsed_sec": round(time.time() - t0, 1)}
    print(json.dumps(out, indent=2))
    ok = (abs(c["diff"] - 0.0379) < 0.004 and abs(res["arms"]["M1_persistence"]["ap"] - 0.1234) < 0.004)
    print("[replication_within_tolerance]", ok)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
