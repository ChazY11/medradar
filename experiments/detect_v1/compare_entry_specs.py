"""Compare the four entry-specification runs side by side."""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path("experiments/detect_v1")
RUNS = [
    ("all events", "entries.json"),
    ("churn controlled", "entries_churn.json"),
    ("prior-filer required", "entries_priorfiler.json"),
    ("prior-filer + churn", "entries_priorfiler_churn.json"),
]
WATCH = ("ivd_immuno", "ivd_molecular", "aesthetics", "medical_ai", "cardiac_rhythm",
         "structural_heart", "wearable_remote")


def main() -> int:
    print(f"{'specification':24s} {'entries':>8s} {'tracks rejected':>16s} {'firms rejected':>15s}")
    rows = []
    for label, filename in RUNS:
        data = json.loads((BASE / filename).read_text(encoding="utf-8"))
        tests = {row["unit"]: row for row in data["industry_clustering"]["tests"]}
        fdr = data["industry_clustering"]["fdr"]
        firm = data["firm_clustering"]["fdr"]
        rows.append((label, data, tests))
        print(f"{label:24s} {data['counts']['entries']:8d} "
              f"{fdr['rejected']:>3d}/{fdr['tests']:<3d} {str(fdr['rejected_keys'])[:22]:22s} "
              f"{firm['rejected']:>3d}/{firm['tests']:<3d}")
    print("\nper-track p-values across specifications:")
    header = "track".ljust(20) + "".join(label[:14].rjust(16) for label, _ in RUNS)
    print(header)
    for track in WATCH:
        cells = []
        for _, _, tests in rows:
            row = tests.get(track)
            cells.append("n/a".rjust(16) if not row else
                         f"n={row['entries']},p={row['pvalue_one_sided']:.4f}".rjust(16))
        print(track.ljust(20) + "".join(cells))
    print("\nsmallest p per specification:")
    for label, data, tests in rows:
        best = min(tests.values(), key=lambda row: row["pvalue_one_sided"])
        threshold = 0.10 / len(tests)
        print(f"  {label:24s} {best['unit']:20s} n={best['entries']:4d} "
              f"p={best['pvalue_one_sided']:.4f}  (BH rank-1 threshold {threshold:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
