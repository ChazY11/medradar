"""Compare naive rate-ratio flags with calibrated momentum detections across the frozen snapshot.

This quantifies what the calibration bought: how many companies a ratio threshold would have called
"rising" or "falling", versus how many survive an exact binomial test at alpha=0.05.
"""
from __future__ import annotations

import json
from pathlib import Path

SNAPSHOT = Path("experiments/b027/snapshots/2026-11-02/profiles.json")
NAIVE_RATIO = 1.25


def main() -> int:
    profiles = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["profiles"]
    rows = []
    for key, profile in profiles.items():
        momentum = profile["momentum"]
        ratio = momentum.get("ratio")
        rows.append({
            "company": key,
            "recent": momentum.get("recent"),
            "prior": momentum.get("prior"),
            "ratio": ratio,
            "p": momentum.get("p_value"),
            "mde": momentum.get("mde_ratio"),
            "detected": momentum.get("detected", False),
            "direction": momentum.get("direction", momentum.get("status")),
            "naive_flag": bool(ratio is not None
                               and (ratio >= NAIVE_RATIO or ratio <= 1 / NAIVE_RATIO)),
        })
    naive = [row for row in rows if row["naive_flag"]]
    detected = [row for row in rows if row["detected"]]
    print(f"companies: {len(rows)}")
    print(f"naive ratio >= {NAIVE_RATIO} or <= {1 / NAIVE_RATIO:.2f}: {len(naive)}")
    print(f"calibrated detections (exact binomial p<0.05): {len(detected)}")
    print(f"naive-only (would have been false claims): {len(naive) - len(detected)}")
    print("\ndetected:")
    for row in sorted(detected, key=lambda item: item["p"] or 1):
        print(f"  {row['company']:20s} {row['recent']:4d} vs {row['prior']:4d} "
              f"ratio {row['ratio']:.2f} p={row['p']:.4f} mde {row['mde']:.2f}")
    print("\nlargest naive flags that do NOT survive the test:")
    for row in sorted((row for row in naive if not row["detected"]),
                      key=lambda item: -(abs((item["ratio"] or 1) - 1)))[:8]:
        print(f"  {row['company']:20s} {row['recent']:4d} vs {row['prior']:4d} "
              f"ratio {row['ratio']:.2f} p={row['p']:.3f} mde {row['mde']:.2f}")
    payload = {"naive_ratio_threshold": NAIVE_RATIO, "companies": len(rows),
               "naive_flags": len(naive), "calibrated_detections": len(detected),
               "rows": rows}
    out = Path("experiments/b027/momentum_calibration.json")
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
