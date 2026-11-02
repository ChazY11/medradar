"""Controlled-truth benchmark for the OBSERVE-layer change detectors.

Design (pre-registered in research/DECISIONS.md D-013, D-014, D-015, D-016):

* Streams are real monthly activity series (entity x technology track, primary;
  entity x domain and a deterministic-track-only variant, secondary). Real monthly
  shape is preserved.
* Cells are split deterministically by entity hash into a CALIBRATION half and an
  EVALUATION half; no entity appears in both. All reported numbers come from the
  evaluation half.
* Injections: a sustained level shift (rate x multiplier from a pre-declared grid at
  pre-declared onsets) and a single-month spike. Post-onset counts are re-drawn from a
  Poisson law so injected streams are exactly as noisy as real ones.
* The injection seed depends only on (cell, onset, multiplier) — never on the detector —
  so every detector is scored on the **identical** injected series. That is common
  random numbers, and it makes detector comparisons *paired*.
* Sensitivity knobs are not chosen by a single hidden calibration decision (that turned
  out to be unstable on ~50 cells). Instead the **entire FPR-detection frontier** is
  reported for every detector: for each knob, the false-alarm rate on uninjected
  evaluation cells and the detection probability / median delay on injected trials.
  A detector is better only if it dominates at comparable false-alarm rates.

A detection is a statement about the rate of public regulatory activity in a cell. It is
not evidence of intent, capability or internal R&D.

Usage:
    python experiments/detect_v1/benchmark.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence import changepoint  # noqa: E402
from experiments.cycle2_coverage.panel import write_json  # noqa: E402
from experiments.detect_v1 import paired  # noqa: E402

# ---------------------------------------------------------------- pre-registered
MULTIPLIERS = (2.0, 3.0, 5.0)
ONSETS = (36, 54, 72, 84)
#: A detection is credited from one month BEFORE the injected onset: some detectors report
#: their estimated change point, which can legitimately land just before the true onset.
#: The tolerance is applied identically to every detector.
ONSET_TOLERANCE_MONTHS = 1
HORIZON_MONTHS = 12
MIN_BASELINE_MONTHS = 24
#: False-alarm rates at which the frontier is read out for the headline comparison.
FRONTIER_FARS = (0.01, 0.02, 0.03, 0.05)

KNOB_GRIDS: dict[str, tuple[str, tuple[float, ...]]] = {
    "naive_multiplier": ("multiplier", (1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 10.0, 16.0, 25.0)),
    "rolling_zscore": ("threshold", (2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 7.0, 10.0, 15.0)),
    "poisson_cusum": ("threshold", (2.0, 3.0, 4.0, 5.0, 8.0, 12.0, 20.0, 40.0, 80.0)),
    "poisson_bayes_factor": ("threshold", (2.0, 3.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0)),
}
DETECTOR_ORDER = ("naive_multiplier", "rolling_zscore", "poisson_cusum",
                  "poisson_bayes_factor")


# ---------------------------------------------------------------------- utilities
def stable_fraction(key: str, salt: str = "") -> float:
    digest = hashlib.sha256(f"{salt}|{key}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(1 << 48)


def split_cells(cells: Sequence[dict[str, Any]], salt: str = "detect-v1") -> tuple[list, list]:
    calibration, evaluation = [], []
    for cell in cells:
        (calibration if stable_fraction(str(cell["entity"]), salt) < 0.5
         else evaluation).append(cell)
    return calibration, evaluation


def poisson_draw(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    product = 1.0
    count = 0
    while True:
        product *= rng.random()
        if product <= limit:
            return count
        count += 1
        if count > 200:
            return count


def baseline_rates(series: Sequence[int], onset: int, window: int = 12) -> tuple[list[float], float]:
    pre = series[max(0, onset - window):onset]
    level = (sum(pre) / len(pre)) if pre else 0.0
    floor = 0.05
    rates = []
    for index in range(len(series)):
        window_slice = series[max(0, index - window):index]
        rate = (sum(window_slice) / len(window_slice)) if window_slice else level
        rates.append(max(rate, floor))
    return rates, max(level, floor)


def inject_shift(series: Sequence[int], onset: int, multiplier: float, seed: int) -> list[int]:
    rng = random.Random(seed)
    rates, _ = baseline_rates(series, onset)
    return [value if index < onset else poisson_draw(rng, multiplier * rates[index])
            for index, value in enumerate(series)]


def inject_spike(series: Sequence[int], onset: int, multiplier: float, seed: int) -> list[int]:
    rng = random.Random(seed)
    rates, _ = baseline_rates(series, onset)
    out = list(series)
    out[onset] = poisson_draw(rng, multiplier * rates[onset])
    return out


def make_detector(name: str, knob_value: float, bin_months: int = 1) -> Callable[[list], list[dict]]:
    """Bind a detector's sensitivity knob (and calendar-matched memory) to concrete values.

    The detectors express their memory windows in *bins*. Leaving them fixed while bin
    width grows would silently give a coarse panel a much longer calendar memory (at
    6-month bins a 24-bin baseline is 144 months, longer than the panel). To keep the
    comparison about aggregation rather than about memory, the exposed window parameters
    are rescaled so their calendar length stays at the monthly default: 12 months for the
    z-score window and 24 months for the CUSUM / Bayes baseline.

    The naive comparator exposes no window parameter, so its internal trailing-window and
    minimum-event guards cannot be rescaled; this is recorded as a limitation of the sweep.
    """
    function = changepoint.DETECTORS[name]
    kwarg = KNOB_GRIDS[name][0]
    extra: dict[str, float] = {}
    if bin_months > 1:
        if name == "rolling_zscore":
            extra["window"] = max(2, 12 // bin_months)
        elif name in ("poisson_cusum", "poisson_bayes_factor"):
            extra["baseline_window"] = max(2, 24 // bin_months)

    def run(stream: list) -> list[dict]:
        return function(stream, **{kwarg: knob_value, **extra})

    run.calendar_memory = extra  # type: ignore[attr-defined]
    return run


def as_stream(series: Sequence[int], labels: Sequence[str]) -> list[tuple[str, int]]:
    return list(zip(labels, series))


def group_of(cell: dict[str, Any]) -> str:
    return str(cell.get("track") or cell.get("domain") or "")


# ------------------------------------------------------------------------ trials
def build_trials(cells: Sequence[dict[str, Any]], labels: Sequence[str],
                 onsets: Sequence[int] = ONSETS,
                 horizon: int = HORIZON_MONTHS,
                 min_baseline: int = MIN_BASELINE_MONTHS
                 ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build every injected trial ONCE, so all detectors see identical series."""
    months = len(labels)
    shifts: list[dict[str, Any]] = []
    spikes: list[dict[str, Any]] = []
    for cell in cells:
        for onset in onsets:
            if onset < min_baseline or onset + horizon > months:
                continue
            for multiplier in MULTIPLIERS:
                base = f"{cell['entity']}|{group_of(cell)}|{onset}|{multiplier}"
                shift_seed = int(stable_fraction(base, "inject-shift") * 2**31)
                spike_seed = int(stable_fraction(base, "inject-spike") * 2**31)
                shifts.append({
                    "entity": cell["entity"], "group": group_of(cell),
                    "onset": onset, "multiplier": multiplier,
                    "stream": as_stream(inject_shift(cell["series"], onset, multiplier, shift_seed),
                                        labels),
                })
                spikes.append({
                    "entity": cell["entity"], "group": group_of(cell),
                    "onset": onset, "multiplier": multiplier,
                    "stream": as_stream(inject_spike(cell["series"], onset, multiplier, spike_seed),
                                        labels),
                })
    return shifts, spikes


def score_detector(detector: Callable[[list], list[dict]], shifts: list[dict[str, Any]],
                   spikes: list[dict[str, Any]], control_cells: Sequence[dict[str, Any]],
                   labels: Sequence[str], horizon: int = HORIZON_MONTHS,
                   tolerance: int = ONSET_TOLERANCE_MONTHS) -> dict[str, Any]:
    """Return per-trial rows plus the uninjected false-alarm rate.

    ``tolerance`` is expressed in *bins*. At a 1-month bin it is one month; at coarser
    bins it is set to 0 so a detector cannot be credited for firing before the change,
    which would otherwise let a 6-month bin be credited for a 6-month-early alarm.
    """
    shift_rows = []
    for trial in shifts:
        detections = detector(trial["stream"])
        window = [d for d in detections
                  if trial["onset"] - tolerance <= d["index"] <= trial["onset"] + horizon
                  and d.get("direction", "up") == "up"]
        shift_rows.append({
            "entity": trial["entity"], "group": trial["group"],
            "onset": trial["onset"], "multiplier": trial["multiplier"],
            "detected": bool(window),
            "delay": (min(d["index"] for d in window) - trial["onset"]) if window else None,
        })
    spike_rows = []
    for trial in spikes:
        detections = detector(trial["stream"])
        declared = any(trial["onset"] - tolerance <= d["index"] <= trial["onset"] + horizon
                       and d.get("direction", "up") == "up" for d in detections)
        spike_rows.append({"entity": trial["entity"], "group": trial["group"],
                           "multiplier": trial["multiplier"], "declared": bool(declared)})
    alarm_cells = 0
    for cell in control_cells:
        if detector(as_stream(cell["series"], labels)):
            alarm_cells += 1
    false_alarm_rate = alarm_cells / len(control_cells) if control_cells else None

    n = len(shift_rows)
    delays = [row["delay"] for row in shift_rows if row["detected"] and row["delay"] is not None]
    by_multiplier: dict[str, Any] = {}
    for multiplier in MULTIPLIERS:
        subset = [row for row in shift_rows if row["multiplier"] == multiplier]
        hits = [row for row in subset if row["detected"]]
        subset_delays = [row["delay"] for row in hits if row["delay"] is not None]
        by_multiplier[str(multiplier)] = {
            "trials": len(subset),
            "detected": len(hits),
            "detection_probability": (len(hits) / len(subset)) if subset else None,
            "median_delay_months": (sorted(subset_delays)[len(subset_delays) // 2]
                                    if subset_delays else None),
        }
    spike_rate = {}
    for multiplier in MULTIPLIERS:
        subset = [row for row in spike_rows if row["multiplier"] == multiplier]
        spike_rate[str(multiplier)] = (
            sum(1 for row in subset if row["declared"]) / len(subset) if subset else None)
    return {
        "false_alarm_rate": false_alarm_rate,
        "false_alarm_cells": alarm_cells,
        "control_cells": len(control_cells),
        "shift_trials": n,
        "detection_probability": (sum(1 for row in shift_rows if row["detected"]) / n) if n else None,
        "median_delay_months": (sorted(delays)[len(delays) // 2] if delays else None),
        "mean_delay_months": (sum(delays) / len(delays) if delays else None),
        "by_multiplier": by_multiplier,
        "spike_false_change_rate": spike_rate,
        "trials": shift_rows,
    }


def frontier_entry(score: dict[str, Any]) -> dict[str, Any]:
    clustered = paired.cluster_bootstrap_rate(score["trials"], "detected")
    return {
        "false_alarm_rate": score["false_alarm_rate"],
        "detection_probability": score["detection_probability"],
        "detection_probability_ci": [clustered["ci_low"], clustered["ci_high"]],
        "median_delay_months": score["median_delay_months"],
        "by_multiplier": score["by_multiplier"],
        "spike_false_change_rate": score["spike_false_change_rate"],
    }


def best_under(entries: list[dict[str, Any]], far_budget: float) -> dict[str, Any] | None:
    eligible = [entry for entry in entries
                if entry["false_alarm_rate"] is not None
                and entry["false_alarm_rate"] <= far_budget
                and entry["detection_probability"] is not None]
    if not eligible:
        return None
    return max(eligible, key=lambda entry: entry["detection_probability"])


# ------------------------------------------------------------------------- driver
def run_level(level_key: str, cells: list[dict[str, Any]], labels: list[str], *,
              bin_months: int = 1) -> dict[str, Any]:
    """Score every detector's frontier on one panel.

    ``bin_months`` scales the pre-registered monthly constants to the panel's bin size:
    onsets, horizon and minimum baseline are all divided by it, so a 3-month panel uses
    the same *calendar* onsets and the same 12-month horizon expressed in bins.
    """
    _calibration, evaluation_cells = split_cells(cells)
    onsets = tuple(max(1, onset // bin_months) for onset in ONSETS)
    horizon = max(1, HORIZON_MONTHS // bin_months)
    min_baseline = max(1, MIN_BASELINE_MONTHS // bin_months)
    # One bin of tolerance only at monthly resolution; at coarser bins a one-bin
    # tolerance would credit an alarm up to `bin_months` before the change.
    tolerance = ONSET_TOLERANCE_MONTHS if bin_months == 1 else 0
    shifts, spikes = build_trials(evaluation_cells, labels, onsets=onsets,
                                  horizon=horizon, min_baseline=min_baseline)
    output: dict[str, Any] = {
        "level": level_key,
        "bin_months": bin_months,
        "bins": len(labels),
        "onsets_used": list(onsets),
        "horizon_bins": horizon,
        "min_baseline_bins": min_baseline,
        "onset_tolerance_bins": tolerance,
        "cells_total": len(cells),
        "evaluation_cells": len(evaluation_cells),
        "evaluation_entities": len({cell["entity"] for cell in evaluation_cells}),
        "shift_trials": len(shifts),
        "spike_trials": len(spikes),
        "detectors": {},
        "frontier_readout": {},
    }
    scores: dict[tuple[str, float], dict[str, Any]] = {}
    for name in DETECTOR_ORDER:
        if name not in getattr(changepoint, "DETECTORS", {}):
            output["detectors"][name] = {"error": "not exported"}
            continue
        kwarg, grid = KNOB_GRIDS[name]
        entries = []
        for knob in grid:
            detector = make_detector(name, knob, bin_months)
            score = score_detector(detector, shifts, spikes, evaluation_cells, labels,
                                   horizon=horizon, tolerance=tolerance)
            scores[(name, knob)] = score
            entries.append({"knob": knob, **frontier_entry(score)})
        output["detectors"][name] = {
            "knob_name": kwarg,
            "frontier": entries,
            "calendar_memory_scaling": getattr(detector, "calendar_memory", {}),
        }

    for budget in FRONTIER_FARS:
        readout = {}
        for name, block in output["detectors"].items():
            if "frontier" not in block:
                continue
            chosen = best_under(block["frontier"], budget)
            readout[name] = dict(chosen) if chosen else {"status": "no point within budget"}
        output["frontier_readout"][str(budget)] = readout

    # Paired comparison inside a common realised false-alarm budget.
    reference_budget = 0.02
    picks = {}
    for name, block in output["detectors"].items():
        if "frontier" not in block:
            continue
        chosen = best_under(block["frontier"], reference_budget)
        if chosen:
            picks[name] = chosen["knob"]
    output["paired_comparison"] = {
        "budget": reference_budget,
        "picked_knobs": picks,
        "note": ("each detector is represented by its best point inside the same realised "
                 "false-alarm budget; pairing is exact because every detector scored the "
                 "identical injected series"),
        "comparisons": {},
    }
    if "naive_multiplier" in picks:
        baseline = scores[("naive_multiplier", picks["naive_multiplier"])]
        for name in DETECTOR_ORDER:
            if name == "naive_multiplier" or name not in picks:
                continue
            candidate = scores[(name, picks[name])]
            comparison = paired.cluster_bootstrap_paired_difference(
                candidate["trials"], baseline["trials"])
            comparison["candidate_knob"] = picks[name]
            comparison["baseline_knob"] = picks["naive_multiplier"]
            output["paired_comparison"]["comparisons"][name] = comparison
            print(f"  [{level_key}] {name:24s} vs naive: delta={comparison['difference']:+.3f} "
                  f"CI=[{comparison['ci_low']:+.3f},{comparison['ci_high']:+.3f}] "
                  f"excludes0={comparison['excludes_zero']}")
    for name, block in output["detectors"].items():
        if "frontier" not in block:
            continue
        inside = best_under(block["frontier"], reference_budget)
        top = max(block["frontier"], key=lambda entry: entry["detection_probability"] or 0)
        print(f"  [{level_key}] {name:24s} "
              f"best@2%={inside['detection_probability'] if inside else None} "
              f"| max P={top['detection_probability']:.3f} at FPR={top['false_alarm_rate']:.3f} "
              f"(knob {top['knob']})")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--streams", default="experiments/detect_v1/streams.json")
    parser.add_argument("--out", default="experiments/detect_v1/benchmark.json")
    parser.add_argument("--ext", default="experiments/detect_v1/streams_ext.json")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.streams).read_text(encoding="utf-8"))
    labels = payload["labels"]
    results = {
        "design": {
            "multipliers": list(MULTIPLIERS),
            "onsets": list(ONSETS),
            "horizon_months": HORIZON_MONTHS,
            "min_baseline_months": MIN_BASELINE_MONTHS,
            "onset_tolerance_months": ONSET_TOLERANCE_MONTHS,
            "frontier_fars": list(FRONTIER_FARS),
            "knob_grids": {name: list(grid) for name, (_, grid) in KNOB_GRIDS.items()},
            "split": ("cells split by entity sha256; no entity in both halves; all reported "
                      "numbers come from the evaluation half"),
            "injection": ("post-onset counts re-drawn from a Poisson law at the injected rate; "
                          "pre-onset months kept exactly as observed"),
            "pairing": ("injection seeds depend only on (cell, onset, multiplier), never on the "
                        "detector, so every detector scores the identical injected series"),
            "selection": ("the full frontier is reported and no single threshold is hidden. The "
                          "readout at a false-alarm budget takes the best point inside it, which "
                          "is optimistic in absolute terms but symmetric across detectors"),
            "streams": payload["counts"],
            "eligibility": payload["eligibility"],
        },
        "levels": {},
    }
    level_specs: list[tuple[str, list[dict[str, Any]], list[str], int]] = [
        ("track", payload["track_cells"], labels, 1),
        ("track_clean", payload.get("track_cells_clean", []), labels, 1),
        ("domain", payload["domain_cells"], labels, 1),
    ]
    ext_path = Path(args.ext) if args.ext else Path("experiments/detect_v1/streams_ext.json")
    if ext_path.exists():
        ext = json.loads(ext_path.read_text(encoding="utf-8"))
        quarter_labels = ext["quarter_labels"]
        level_specs.extend([
            ("track_no_special", ext["track_no_special"], labels, 1),
            ("track_stable_codes", ext["track_stable_codes"], labels, 1),
            ("track_quarterly", ext["track_quarterly"], quarter_labels, 3),
        ])
        results["design"]["ext"] = {
            "path": str(ext_path),
            "decision": ext.get("decision"),
            "filters": ext.get("filters"),
            "summaries": {key: ext[key] for key in
                          ("track_no_special_summary", "track_stable_codes_summary",
                           "track_quarterly_summary")},
        }
    for level_key, cells, level_labels, bin_months in level_specs:
        if not cells:
            print(f"level {level_key}: no cells (skipped)")
            continue
        print(f"level {level_key}: {len(cells)} cells, {len(level_labels)} bins "
              f"({bin_months}-month)")
        results["levels"][level_key] = run_level(level_key, cells, level_labels,
                                                 bin_months=bin_months)

    write_json(Path(args.out), results)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())






