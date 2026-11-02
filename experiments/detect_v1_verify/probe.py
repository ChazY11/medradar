"""Scratch probe: timings + split/trial counts (independent re-implementation)."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from medradar.intelligence import changepoint  # noqa: E402


def stable_fraction(key: str, salt: str = "") -> float:
    digest = hashlib.sha256(f"{salt}|{key}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(1 << 48)


def main() -> int:
    payload = json.loads((ROOT / "experiments/detect_v1/streams.json").read_text(encoding="utf-8"))
    labels = payload["labels"]
    for level, cells in (("track", payload["track_cells"]),
                         ("track_clean", payload["track_cells_clean"]),
                         ("domain", payload["domain_cells"])):
        ev = [c for c in cells if stable_fraction(str(c["entity"]), "detect-v1") >= 0.5]
        print(level, "total", len(cells), "eval", len(ev),
              "entities", len({c["entity"] for c in ev}),
              "trials", len(ev) * 4 * 3)
    ser = payload["track_cells"][0]["series"]
    stream = list(zip(labels, ser))
    for name, fn, kw in (
            ("naive", changepoint.detect_naive_threshold, {"multiplier": 6.0}),
            ("z", changepoint.detect_rolling_zscore, {"threshold": 4.0}),
            ("cusum", changepoint.detect_poisson_cusum, {"threshold": 20.0}),
            ("bayes", changepoint.detect_poisson_bayes_factor, {"threshold": 20.0})):
        t = time.perf_counter()
        for _ in range(30):
            out = fn(stream, **kw)
        dt = (time.perf_counter() - t) / 30
        print(name, f"{dt * 1000:.2f} ms", out[:1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
