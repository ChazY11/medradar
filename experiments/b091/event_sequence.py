"""Phase 1D: event-level point-process detection vs quarterly counting, under controlled truth.

Frozen design in PHASE1D_PROTOCOL.md. For each of the 16 cells:
  * null runs (no injection) measure each detector's empirical false-alarm rate per run;
  * injected runs (rate x2 and x3 at 60% of the sequence) measure power and detection delay in days.

Detector A: exponential rate-change profile likelihood, threshold calibrated by parametric null simulation to 0.10
false alarms per run (and additionally to detector B's measured null rate, for an equal-budget comparison).
Detector B: the deployed quarterly count z-score (8-quarter baseline, threshold 3.5).

    python experiments/b091/event_sequence.py
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.pointprocess import (  # noqa: E402
    calibrate_null,
    detect_first_after,
    empirical_threshold,
    inject_rate_change,
    max_prefix_lr,
    paired_bootstrap_median,
    quarterly_counts,
    quarterly_max_z,
    rate_above,
    quarterly_zscore_detector,
    rate_change_lr,
    times_from_intervals,
)

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
INVENTORY = Path("research/studies/early_signal_5firms/CELL_INVENTORY.json")
OUT_DIR = Path("research/studies/early_signal_5firms")
WINDOW = ("2017-01-01", "2025-12-31")
LAG_DAYS = 30
CHANGE_FRACTION = 0.60
MULTIPLIERS = (2.0, 3.0)
REPLICATIONS = 200
SEED = 4242
FAR_TARGET = 0.10
MIN_EVENTS = 20
QUARTER_DAYS = 365.25 / 4


def parse(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def load_times(con: sqlite3.Connection, firm: str, track: str) -> list[float]:
    rows = con.execute(
        "select event_date from events where kind in ('510k','pma') and company_key=? and track_id=? "
        "and event_date between ? and ? order by event_date", (firm, track, *WINDOW)).fetchall()
    dates = [parse(row[0]) for row in rows]
    dates = [value for value in dates]
    if not dates:
        return []
    origin = dates[0]
    return [(value - origin).days + LAG_DAYS for value in dates]


def rotate(intervals: list[float], offset: int) -> list[float]:
    if not intervals:
        return []
    offset %= len(intervals)
    return intervals[offset:] + intervals[:offset]


def run_cell(times: list[float], rng: random.Random) -> dict:
    intervals = [times[index] - times[index - 1] for index in range(1, len(times))]
    if not intervals:
        return {"status": "INSUFFICIENT_EVENTS"}
    total = times[-1] if times else 0.0
    n = len(times)

    # --- empirical calibration to an equal null rate (0.10 per run) ------
    # A parametric Poisson null is badly miscalibrated on real, overdispersed filing sequences (measured false-alarm
    # rates were 0.22-1.0 against a 0.10 target), so both detectors are calibrated to the same *empirical* null rate:
    # thresholds are the 90th percentile of the null statistic distribution obtained by rotating the real sequence
    # with no injection.
    null_runs = 200
    null_lr, null_z = [], []
    for _ in range(null_runs):
        offset = rng.randrange(len(intervals)) if intervals else 0
        sequence = times_from_intervals(rotate(intervals, offset))
        if len(sequence) < 4:
            continue
        null_lr.append(max_prefix_lr(sequence))
        bins = max(4, int(len(sequence) / 2))
        null_z.append(quarterly_max_z(quarterly_counts(sequence, sequence[-1], quarters=bins)))

    threshold_a = empirical_threshold(null_lr, false_alarm_per_run=FAR_TARGET)
    threshold_b = empirical_threshold(null_z, false_alarm_per_run=FAR_TARGET)
    far_a = rate_above(null_lr, threshold_a)
    far_b = rate_above(null_z, threshold_b)

    # --- injected runs ----------------------------------------------------
    per_multiplier = {}
    for multiplier in MULTIPLIERS:
        change_index = int(len(intervals) * CHANGE_FRACTION)
        before = change_index
        after = len(intervals) - change_index
        if before < 8 or after < 5:
            per_multiplier[str(multiplier)] = {"status": "INSUFFICIENT_EVENTS",
                                               "events_before": before, "events_after": after}
            continue
        delays_a, delays_b, detected_a, detected_b = [], [], 0, 0
        for _ in range(REPLICATIONS):
            offset = rng.randrange(len(intervals))
            rotated = rotate(intervals, offset)
            # keep the injected change at the frozen fraction of the rotated sequence
            injected = inject_rate_change(rotated, change_index=change_index, multiplier=multiplier)
            sequence = times_from_intervals(injected)
            change_time = sequence[change_index - 1] if change_index >= 1 else 0.0
            detection = detect_first_after(sequence, threshold=threshold_a) if threshold_a else None
            if detection is not None:
                detected_a += 1
                if detection > change_time:
                    delays_a.append(detection - change_time)
            counts = quarterly_counts(sequence, sequence[-1],
                                      quarters=max(4, int(len(sequence) / 2)))
            bin_index = quarterly_zscore_detector(counts, threshold=threshold_b or 3.5)["alert_bin"]
            if bin_index is not None:
                detected_b += 1
                bin_end = sequence[-1] * (bin_index + 1) / len(counts)
                if bin_end > change_time:
                    delays_b.append(bin_end - change_time)
        per_multiplier[str(multiplier)] = {
            "status": "OK", "events_before": before, "events_after": after,
            "replications": REPLICATIONS,
            "power_a": round(detected_a / REPLICATIONS, 3),
            "power_b": round(detected_b / REPLICATIONS, 3),
            "median_delay_days_a": round(sorted(delays_a)[len(delays_a) // 2], 1) if delays_a else None,
            "median_delay_days_b": round(sorted(delays_b)[len(delays_b) // 2], 1) if delays_b else None,
        }
    return {"status": "OK", "events": n, "span_days": round(total, 1),
            "threshold_a": round(threshold_a, 3) if threshold_a else None,
            "threshold_b": round(threshold_b, 3) if threshold_b is not None else None,
            "far_a": round(far_a, 3) if far_a is not None else None,
            "far_b": round(far_b, 3) if far_b is not None else None,
            "by_multiplier": per_multiplier}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=str(INVENTORY))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    cells = [{"company": entry["company"], "track": entry["track"], "set": "primary"}
             for entry in inventory["both_streams"]]
    cells += [{"company": entry["company"], "track": entry["track"], "set": "secondary"}
              for entry in inventory["regulatory_only"]]

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    rng = random.Random(SEED)
    results = {}
    for cell in cells:
        times = load_times(con, cell["company"], cell["track"])
        key = f"{cell['company']}|{cell['track']}"
        if len(times) < MIN_EVENTS:
            results[key] = {"set": cell["set"], "status": "INSUFFICIENT_EVENTS", "events": len(times)}
            continue
        results[key] = {"set": cell["set"], **run_cell(times, rng)}
    con.close()

    # --- pooled comparison ------------------------------------------------
    pooled = {}
    for multiplier in MULTIPLIERS:
        label = str(multiplier)
        usable = {key: cell for key, cell in results.items()
                  if cell.get("by_multiplier", {}).get(label, {}).get("status") == "OK"}
        if not usable:
            pooled[label] = {"cells": 0, "status": "NOT_EVALUABLE"}
            continue
        delays_a = {key: cell["by_multiplier"][label]["median_delay_days_a"] for key, cell in usable.items()
                    if cell["by_multiplier"][label]["median_delay_days_a"] is not None}
        delays_b = {key: cell["by_multiplier"][label]["median_delay_days_b"] for key, cell in usable.items()
                    if cell["by_multiplier"][label]["median_delay_days_b"] is not None}
        power_a = sum(cell["by_multiplier"][label]["power_a"] for cell in usable.values()) / len(usable)
        power_b = sum(cell["by_multiplier"][label]["power_b"] for cell in usable.values()) / len(usable)
        pooled[label] = {
            "status": "OK", "cells": len(usable),
            "mean_power_a": round(power_a, 3), "mean_power_b": round(power_b, 3),
            "median_delay_a": round(sorted(delays_a.values())[len(delays_a) // 2], 1) if delays_a else None,
            "median_delay_b": round(sorted(delays_b.values())[len(delays_b) // 2], 1) if delays_b else None,
            "paired_bootstrap": paired_bootstrap_median(delays_a, delays_b, resamples=2000, seed=7),
        }

    evaluable = {label: pooled.get(label, {}).get("cells", 0) for label in map(str, MULTIPLIERS)}
    underpowered = any(count < 8 for count in evaluable.values())
    if underpowered:
        verdict = f"UNDERPOWERED — evaluable cells {evaluable} (floor 8 per multiplier); comparison is descriptive"
    else:
        parts = []
        for label, block in pooled.items():
            if block.get("status") != "OK":
                continue
            bootstrap = block["paired_bootstrap"]
            difference = bootstrap["median_difference"]
            low, high = bootstrap["interval"]
            if difference is not None and low is not None and high is not None:
                if high < 0:
                    direction = "A earlier than B (fine unit advantage)"
                elif low > 0:
                    direction = "B earlier than A (fine unit is slower)"
                else:
                    direction = "no clear difference"
            else:
                direction = "not comparable"
            parts.append(f"m={label}: A {block['median_delay_a']} d vs B {block['median_delay_b']} d, "
                         f"power {block['mean_power_a']} vs {block['mean_power_b']}, "
                         f"paired median difference {difference} {bootstrap['interval']} ({direction})")
        verdict = "; ".join(parts) if parts else "NOT_EVALUABLE"

    payload = {
        "schema": "event_sequence_detection_v1",
        "protocol": "PHASE1D_PROTOCOL.md (frozen before this run)",
        "window": list(WINDOW), "lag_days": LAG_DAYS,
        "injection": {"change_fraction": CHANGE_FRACTION, "multipliers": list(MULTIPLIERS),
                      "replications": REPLICATIONS, "seed": SEED},
        "budget": {"far_target_a": FAR_TARGET},
        "cells": results, "pooled": pooled, "verdict": verdict,
        "not_claimed": [
            "the truth is synthetic: this measures detector geometry, not whether real technology shifts exist",
            "no lead-time claim relative to real milestones (G1)",
            "no causal, intent or R&D claim",
        ],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "EVENT_SEQUENCE_DETECTION.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# EVENT-SEQUENCE DETECTION — Phase 1D (controlled truth)", "",
             f"Cells: {len(results)} · multipliers {MULTIPLIERS} · {REPLICATIONS} replications each · "
             f"change at {int(CHANGE_FRACTION*100)}% of the sequence · seed {SEED}.", "",
             f"**Verdict:** {verdict}", "",
             "## Pooled", "",
             "| multiplier | cells | power A (interval LR) | power B (quarterly z) | median delay A (d) | median delay B (d) | paired median diff [95% CI] |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for label, block in pooled.items():
        if block.get("status") != "OK":
            lines.append(f"| {label} | 0 | — | — | — | — | NOT_EVALUABLE |")
            continue
        bootstrap = block["paired_bootstrap"]
        lines.append(f"| {label} | {block['cells']} | {block['mean_power_a']} | {block['mean_power_b']} | "
                     f"{block['median_delay_a']} | {block['median_delay_b']} | "
                     f"{bootstrap['median_difference']} {bootstrap['interval']} |")
    lines += ["", "## Per cell (m = 2)", "",
              "| cell | events | power A | power B | delay A (d) | delay B (d) | FAR A | FAR B |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key, cell in results.items():
        block = cell.get("by_multiplier", {}).get("2.0", {})
        if block.get("status") != "OK":
            lines.append(f"| {key} | {cell.get('events')} | — | — | — | — | {cell.get('far_a')} | {cell.get('far_b')} |")
            continue
        lines.append(f"| {key} | {cell['events']} | {block['power_a']} | {block['power_b']} | "
                     f"{block['median_delay_days_a']} | {block['median_delay_days_b']} | "
                     f"{cell['far_a']} | {cell['far_b']} |")
    lines += ["", "## Not claimed", ""] + [f"- {item}" for item in payload["not_claimed"]]
    (out_dir / "EVENT_SEQUENCE_DETECTION.md").write_text("\n".join(lines) + "\n",
                                                         encoding="utf-8", newline="\n")

    print(f"cells: {len(results)}; evaluable per multiplier: {evaluable}")
    for label, block in pooled.items():
        if block.get("status") == "OK":
            print(f"  m={label}: A delay {block['median_delay_a']} d, B {block['median_delay_b']} d, "
                  f"power {block['mean_power_a']}/{block['mean_power_b']}, "
                  f"diff {block['paired_bootstrap']['median_difference']} {block['paired_bootstrap']['interval']}")
    print(f"verdict: {verdict}")
    print(f"wrote {out_dir}/EVENT_SEQUENCE_DETECTION.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
