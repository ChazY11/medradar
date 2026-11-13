#!/usr/bin/env python3
"""Compare a previous results snapshot with the results produced by the clean-cache
re-run, so the "re-runs end to end" claim is checked instead of asserted.

Usage
    python verify_rerun.py <snapshot_dir> <current_dir>
Exit code 0 = identical on every compared number.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cell_common as cc  # noqa: E402
import phoenix_common as pc  # noqa: E402

TOL = 1e-12
FILES = [
    "cell_all_metrics.json", "primary_tests.json", "h1.json", "h2.json", "h4.json",
    "h5.json", "h10.json", "audit_cell.json", "leakage_investigation.json",
    "sensitivity_device_cells.json", "selftest.json",
]
# numeric leaves that should be bit-identical with a fixed seed
SKIP_KEYS = {"elapsed_sec", "elapsed_sec_run_cell", "written_at", "timestamp",
             "command", "fit_predict_sec", "build_elapsed_sec", "cache_bytes",
             "cache_path", "git_head", "db_path"}
VOLATILE = {"per_lag_elapsed_sec"}
# top-level provenance fields that were hoisted out of `meta.provenance` after the
# first snapshot was taken; a missing one on the old side is not a value change
HOISTED = {"protocol_version", "db_sha256", "lag_scenario", "command",
           "n", "n_pos", "prevalence", "elapsed_sec"}


def walk(a, b, path, diffs, n_cmp):
    if isinstance(a, dict) and isinstance(b, dict):
        depth = path.count(".")
        for k in sorted(set(a) | set(b)):
            if k in SKIP_KEYS or k in VOLATILE:
                continue
            if k not in a or k not in b:
                if depth == 1 and k in HOISTED:
                    continue
                diffs.append(f"{path}.{k}: missing on one side")
                continue
            walk(a[k], b[k], f"{path}.{k}", diffs, n_cmp)
        return
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: list length {len(a)} vs {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", diffs, n_cmp)
        return
    if isinstance(a, bool) or isinstance(b, bool):
        n_cmp[0] += 1
        if a != b:
            diffs.append(f"{path}: {a} vs {b}")
        return
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        n_cmp[0] += 1
        fa, fb = float(a), float(b)
        if (np.isnan(fa) and np.isnan(fb)) or (np.isfinite(fa) and np.isfinite(fb)
                                               and abs(fa - fb) <= TOL):
            return
        diffs.append(f"{path}: {fa!r} vs {fb!r}")
        return
    n_cmp[0] += 1
    if a != b:
        diffs.append(f"{path}: {a!r} vs {b!r}")


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python verify_rerun.py <snapshot_dir> <current_dir>")
    snap, cur = Path(sys.argv[1]), Path(sys.argv[2])
    total_cmp = 0
    all_diffs = []
    for fn in FILES:
        p1, p2 = snap / fn, cur / fn
        if not (p1.exists() and p2.exists()):
            all_diffs.append(f"{fn}: missing file")
            continue
        a = pc.json.loads(p1.read_text(encoding="utf-8"))
        b = pc.json.loads(p2.read_text(encoding="utf-8"))
        diffs, n_cmp = [], [0]
        walk(a, b, fn, diffs, n_cmp)
        total_cmp += n_cmp[0]
        status = "IDENTICAL" if not diffs else f"{len(diffs)} DIFFS"
        print(f"{fn:<34} {status:<14} ({n_cmp[0]} values compared)")
        all_diffs.extend(diffs)
    print(f"\ncompared {total_cmp} values across {len(FILES)} files")
    if all_diffs:
        print(f"DIFFERENCES ({len(all_diffs)}):")
        for d in all_diffs[:40]:
            print("  " + d)
        return 1
    print("VERDICT: clean-cache re-run reproduces every compared number identically")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
