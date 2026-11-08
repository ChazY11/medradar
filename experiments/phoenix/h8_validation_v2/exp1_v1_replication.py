"""Experiment 1 — full reproduction of PHOENIX-001 T-TRACK/H8 from a clean cache.

Runs the *frozen PHOENIX-001 code itself* (build_panel -> entrants_hhi -> run_track)
with every output directory redirected into a temporary workspace, so no PHOENIX-001
artifact is modified.  Then compares the produced numbers with the published values.

Run:  python exp1_v1_replication.py [--out results/exp1_v1_replication]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

import protocol as P

HERE = Path(__file__).resolve().parent
V1_TRACK = (HERE.parent / "hypotheses" / "track").resolve()

# Published PHOENIX-001 numbers, transcribed from
# docs/phoenix/EXPERIMENTS_TRACK_H3_H6_H7_H8_H9.md (section 6) and PHOENIX_GAP_AND_OPPORTUNITY.md.
PUBLISHED = {
    "B1_ap": 0.1234,
    "H8_ap": 0.1613,
    "dap": 0.0379,
    "ci95": [0.0115, 0.0618],
    "p": 0.0040,
    "n": 2443,
    "n_pos": 155,
    "prevalence": 0.0634465820712239,
    "holdout_2022_n": 590,
    "holdout_2022_n_pos": 31,
}


def _sanitize(o):
    if isinstance(o, dict):
        return {str(k): _sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sanitize(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def run(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="phoenix002_exp1_"))
    cache, results, evidence = tmp / "cache", tmp / "results", tmp / "evidence"
    for d in (cache, results, evidence):
        d.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(V1_TRACK))
    import track_common as tc          # noqa: E402
    import build_panel as v1_build     # noqa: E402
    import entrants_hhi as v1_ent      # noqa: E402
    import run_track as v1_run         # noqa: E402

    tc.CACHE_DIR = cache
    tc.RESULTS_DIR = results
    tc.EVIDENCE_DIR = evidence

    t0 = time.time()
    rc1 = tc.run_script("v1_01_build_panel_clean_cache", lambda log: v1_build.main(log, True))
    rc2 = tc.run_script("v1_02_entrants_hhi_clean_cache", v1_ent.main)
    rc3 = tc.run_script("v1_03_run_track_clean_cache", v1_run.main)
    elapsed = time.time() - t0

    # collect the v1 outputs we need
    keep = ["panel_facts.json", "primary_tests.json", "h8_scitrends.json",
            "track_all_metrics.json", "h3h6_descriptive.json"]
    for name in keep:
        src = results / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
    for name in ("v1_01_build_panel_clean_cache", "v1_02_entrants_hhi_clean_cache",
                 "v1_03_run_track_clean_cache"):
        src = evidence / f"{name}.log"
        if src.exists():
            shutil.copy2(src, out_dir / f"{name}.log")

    prim = json.loads((results / "primary_tests.json").read_text(encoding="utf-8"))
    h8 = json.loads((results / "h8_scitrends.json").read_text(encoding="utf-8"))
    allm = json.loads((results / "track_all_metrics.json").read_text(encoding="utf-8"))
    panel_facts = json.loads((results / "panel_facts.json").read_text(encoding="utf-8"))
    l090 = prim["by_lag"]["L090"]["H8"]
    summary = {
        "experiment": "EXP1_V1_FULL_REPRODUCTION_CLEAN_CACHE",
        "protocol_version": P.PROTOCOL_VERSION,
        "db_sha256": P.DB_SHA256,
        "v1_code": {
            "track_common": str(V1_TRACK / "track_common.py"),
            "harness_protocol": prim.get("protocol_version"),
        },
        "exit_codes": {"build_panel": rc1, "entrants_hhi": rc2, "run_track": rc3},
        "elapsed_sec": round(elapsed, 1),
        "panel": {"n": panel_facts["n"], "n_pos": panel_facts["n_pos"],
                  "prevalence": panel_facts["prevalence"],
                  "frozen_reference_match": panel_facts["frozen_reference_check"]["match"]},
        "walk_forward": {"n": prim["n"], "n_pos": prim["n_pos"],
                         "prevalence": prim["prevalence"]},
        "H8_contrast_reproduced": {
            "dap": l090["diff"], "ci95": [l090["lo"], l090["hi"]], "p": l090["p"],
            "ap_a": l090["ap_a"], "ap_b": l090["ap_b"]},
        "arms_reproduced": {
            "B1_persistence_ap": h8["arms_ap"]["B1_persistence"],
            "H8_growth_ap": h8["arms_ap"]["H8_growth"],
        },
        "by_lag": {tag: {"dap": v["H8"]["diff"], "ci95": [v["H8"]["lo"], v["H8"]["hi"]],
                         "p": v["H8"]["p"]}
                   for tag, v in prim["by_lag"].items()},
        "published": PUBLISHED,
        "deltas_vs_published": {
            "dap": l090["diff"] - PUBLISHED["dap"],
            "ap_b": l090["ap_b"] - PUBLISHED["B1_ap"],
            "ap_a": l090["ap_a"] - PUBLISHED["H8_ap"],
            "p": l090["p"] - PUBLISHED["p"],
            "n": prim["n"] - PUBLISHED["n"],
            "n_pos": prim["n_pos"] - PUBLISHED["n_pos"],
        },
        "reproduction_verdict": (
            "EXACT_MATCH_TO_PUBLISHED_ROUNDING"
            if abs(l090["diff"] - PUBLISHED["dap"]) < 5e-5
            and abs(l090["ap_a"] - PUBLISHED["H8_ap"]) < 5e-5
            and abs(l090["ap_b"] - PUBLISHED["B1_ap"]) < 5e-5
            and abs(l090["lo"] - PUBLISHED["ci95"][0]) < 5e-5
            and abs(l090["hi"] - PUBLISHED["ci95"][1]) < 5e-5
            and prim["n"] == PUBLISHED["n"] and prim["n_pos"] == PUBLISHED["n_pos"]
            else ("WITHIN_TOLERANCE" if abs(l090["diff"] - PUBLISHED["dap"]) < 0.002
                  else "MISMATCH")),
        "notes": [
            "The frozen PHOENIX-001 code was executed unmodified; only its output "
            "directories were redirected to a temporary workspace, which was deleted.",
            "Cache was empty at start, so this is a clean-cache end-to-end reproduction.",
        ],
    }
    summary = _sanitize(summary)
    (out_dir / "exp1_replication.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({k: summary[k] for k in
                      ("reproduction_verdict", "H8_contrast_reproduced", "walk_forward",
                       "elapsed_sec", "exit_codes")}, indent=2))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "results" / "exp1_v1_replication"))
    a = ap.parse_args()
    run(Path(a.out))
