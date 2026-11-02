"""Real-data application of the change detectors, with FDR control and an objective
"new direction" signature.

Two things are deliberately kept separate:

1. **Alerts.** Each calibrated detector is run on every eligible real cell; we record the
   first alert per cell and how many alerts survive a Benjamini-Hochberg control across a
   single pre-declared hypothesis test per cell (recent rate vs earlier rate). This is the
   operating load an analyst would actually face.

2. **Is the alerted activity qualitatively different?** Confirmation by a second regulatory
   pathway is weak here because both pathways come from the same filing system. Instead the
   objective signature is *novelty*: among the product codes exercised in the 12 months
   after an alert, what fraction had not been used by that cell in the previous 36 months?
   Elevated activity mechanically produces more new codes, so the comparison is on the
   novelty *share* (new codes per event), and it is reported as descriptive evidence with
   that circularity stated, never as proof that a technology change occurred.

Usage:
    python experiments/detect_v1/realdetect.py --db data/research.sqlite
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.intelligence import changepoint  # noqa: E402
from medradar.intelligence.universe import entity_key, normalise_applicant  # noqa: E402
from experiments.cycle2_coverage.panel import load_regulatory_events, write_json  # noqa: E402
from experiments.detect_v1.benchmark import (  # noqa: E402
    KNOB_GRIDS,
    make_detector,
    split_cells,
)
from experiments.detect_v1.streams import (  # noqa: E402
    WINDOW_MONTHS,
    month_index,
    track_domains,
)

#: Single pre-declared per-cell test used for FDR control.
TEST_RECENT_MONTHS = 24
TEST_BASELINE_MONTHS = 48
BH_Q = 0.10
#: Novelty comparison windows.
NOVELTY_POST_MONTHS = 12
NOVELTY_HISTORY_MONTHS = 36


# ------------------------------------------------------------------ exact Poisson
def poisson_upper_tail(k: int, lam: float) -> float:
    """P(X >= k) for X ~ Poisson(lam); exact summation, stable for small lam."""
    if k <= 0:
        return 1.0
    if lam <= 0:
        return 0.0
    term = math.exp(-lam)
    cumulative = term
    for value in range(1, k):
        term *= lam / value
        cumulative += term
        if cumulative > 1.0:
            return 1.0
    return max(0.0, min(1.0, 1.0 - cumulative))


def benjamini_hochberg(pvalues: list[tuple[str, float]], q: float = BH_Q) -> dict[str, Any]:
    """BH step-up; returns rejected set and adjusted thresholds kept explicit."""
    ordered = sorted(pvalues, key=lambda item: item[1])
    m = len(ordered)
    rejected: list[str] = []
    cutoff_rank = 0
    cutoff_p = None
    for rank, (key, pvalue) in enumerate(ordered, start=1):
        if pvalue <= rank / m * q:
            cutoff_rank = rank
            cutoff_p = pvalue
    if cutoff_rank:
        rejected = [key for key, pvalue in ordered[:cutoff_rank]]
    return {
        "q": q,
        "tests": m,
        "rejected": len(rejected),
        "cutoff_rank": cutoff_rank,
        "cutoff_pvalue": cutoff_p,
        "rejected_keys": rejected,
        "smallest_pvalue": ordered[0][1] if ordered else None,
        "median_pvalue": ordered[m // 2][1] if ordered else None,
    }


# ----------------------------------------------------------------------- data prep
def load_event_index(db_path: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """(entity, track) -> list of events with month index and product code."""
    events = load_regulatory_events(db_path)
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        normalised = normalise_applicant(event.get("applicant_raw"))
        if not normalised:
            continue
        track = event.get("track_id")
        offset = month_index(event["day"])
        if not track or offset is None:
            continue
        index[(entity_key(normalised), track)].append({
            "month": offset,
            "date": event["day"].isoformat(),
            "kind": event["kind"],
            "product_code": str(event.get("product_code") or ""),
            "event_id": event.get("event_id"),
        })
    for rows in index.values():
        rows.sort(key=lambda row: (row["month"], row["date"]))
    return index


def cell_test(cell: dict[str, Any]) -> dict[str, Any]:
    """Pre-declared per-cell test: recent 24-month rate vs preceding 48-month rate."""
    series = cell["series"]
    recent = series[-TEST_RECENT_MONTHS:]
    baseline = series[-(TEST_RECENT_MONTHS + TEST_BASELINE_MONTHS):-TEST_RECENT_MONTHS]
    observed = sum(recent)
    baseline_rate = (sum(baseline) / len(baseline)) if baseline else 0.0
    expected = baseline_rate * len(recent)
    pvalue = poisson_upper_tail(observed, expected) if expected > 0 else 1.0
    return {
        "key": f"{cell['entity']}|{cell['track']}",
        "observed_recent": observed,
        "expected_recent": expected,
        "baseline_rate_per_month": baseline_rate,
        "pvalue": pvalue,
    }


def novelty_by_cell(events: list[dict[str, Any]], alert_month: int) -> dict[str, Any]:
    """New-product-code share after the alert vs the preceding history."""
    post = [event for event in events
            if alert_month < event["month"] <= alert_month + NOVELTY_POST_MONTHS]
    history = {event["product_code"] for event in events
               if alert_month - NOVELTY_HISTORY_MONTHS <= event["month"] <= alert_month}
    codes = {event["product_code"] for event in post if event["product_code"]}
    novel = codes - history
    return {
        "post_events": len(post),
        "post_codes": len(codes),
        "novel_codes": len(novel),
        "novelty_share_per_event": (len(novel) / len(post)) if post else None,
        "novel_codes_sample": sorted(novel)[:8],
    }


# --------------------------------------------------------------------------- driver
def choose_operating_knob(name: str, calibration_cells: list[dict[str, Any]],
                          labels: list[str], target_fpr: float = 0.02) -> dict[str, Any]:
    """Pick one operating point per detector for the real-data alert inventory.

    This is a pre-declared operating choice, not an evaluation: the most sensitive knob
    whose false-alarm rate on the *calibration half* of the cells stays inside
    ``target_fpr``. The real-data alert count is then reported as an inventory, and the
    benchmark (not this function) is what licenses any claim about detector quality.
    """
    _kwarg, grid = KNOB_GRIDS[name]
    rows = []
    for knob in grid:
        detector = make_detector(name, knob)
        alarmed = sum(1 for cell in calibration_cells
                      if detector(list(zip(labels, cell["series"]))))
        rate = alarmed / len(calibration_cells) if calibration_cells else None
        rows.append({"knob": knob, "alarmed_cells": alarmed, "false_alarm_rate": rate})
    inside = [row for row in rows
              if row["false_alarm_rate"] is not None and row["false_alarm_rate"] <= target_fpr]
    if inside:
        chosen = min(inside, key=lambda row: row["knob"])
        rule = f"most sensitive knob with calibration false-alarm rate <= {target_fpr}"
    else:
        chosen = min(rows, key=lambda row: row["false_alarm_rate"])
        rule = "no knob met the budget; least false-alarming knob"
    return {"detector": name, "chosen_knob": chosen["knob"],
            "chosen_false_alarm_rate": chosen["false_alarm_rate"],
            "target_false_alarm_rate": target_fpr, "rule": rule,
            "grid": rows, "budget_met": bool(inside)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/research.sqlite")
    parser.add_argument("--streams", default="experiments/detect_v1/streams.json")
    parser.add_argument("--out", default="experiments/detect_v1/realdetect.json")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.streams).read_text(encoding="utf-8"))
    labels = payload["labels"]
    cells = payload["track_cells"]
    calibration_cells, _evaluation = split_cells(cells)
    event_index = load_event_index(Path(args.db))
    domains = track_domains()
    # domain-level cell -> its track-level event lists, for novelty when a domain fires
    domain_events: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (entity, track), rows in event_index.items():
        domain = domains.get(track)
        if domain:
            domain_events[(entity, domain)].extend(rows)
    for rows in domain_events.values():
        rows.sort(key=lambda row: (row["month"], row["date"]))

    # FDR control on the pre-declared per-cell test over ALL eligible cells
    tests = [cell_test(cell) for cell in cells]
    bh = benjamini_hochberg([(row["key"], row["pvalue"]) for row in tests])
    rejected = set(bh["rejected_keys"])

    output: dict[str, Any] = {
        "design": {
            "cells_tested": len(cells),
            "test": (f"recent {TEST_RECENT_MONTHS} months vs preceding {TEST_BASELINE_MONTHS} "
                     f"months, exact one-sided Poisson upper tail"),
            "fdr": {"method": "Benjamini-Hochberg", "q": BH_Q},
            "novelty": (f"product codes in the {NOVELTY_POST_MONTHS} months after an alert that "
                        f"were unused in the previous {NOVELTY_HISTORY_MONTHS} months, reported as "
                        f"a share of post-alert events; elevated activity mechanically yields more "
                        f"new codes, so this is descriptive, not proof of a technology change"),
            "caveat": ("alerts are statements about the rate of public regulatory activity in a "
                       "cell, not about intent, capability or internal R&D"),
        },
        "hypothesis_test": {
            "bh": bh,
            "smallest_pvalues": sorted(
                ({"key": row["key"], "pvalue": row["pvalue"],
                  "observed_recent": row["observed_recent"],
                  "expected_recent": row["expected_recent"]} for row in tests),
                key=lambda row: row["pvalue"])[:15],
        },
        "detectors": {},
    }
    print(f"cells={len(cells)}  BH rejected={bh['rejected']} of {bh['tests']} "
          f"(cutoff p={bh['cutoff_pvalue']})")

    for name in KNOB_GRIDS:
        if name not in getattr(changepoint, "DETECTORS", {}):
            output["detectors"][name] = {"error": "detector not exported"}
            continue
        calibration = choose_operating_knob(name, calibration_cells, labels)
        detector = make_detector(name, calibration["chosen_knob"])
        alerts = []
        for cell in cells:
            detections = detector(list(zip(labels, cell["series"])))
            if not detections:
                continue
            first = detections[0]
            key = f"{cell['entity']}|{cell['track']}"
            events = event_index.get((cell["entity"], cell["track"]), [])
            alerts.append({
                "key": key,
                "entity": cell["entity"],
                "entity_name": cell["entity_name"],
                "track": cell["track"],
                "alert_month_index": first["index"],
                "alert_month": first["date"],
                "statistic": round(float(first["statistic"]), 6),
                "baseline_rate": round(float(first["baseline_rate"]), 6),
                "observed_rate": round(float(first["observed_rate"]), 6),
                "cell_events": cell["total_events"],
                "survives_bh": key in rejected,
                "novelty": novelty_by_cell(events, first["index"]),
                "example_events": [
                    {"date": row["date"], "kind": row["kind"],
                     "product_code": row["product_code"]}
                    for row in events
                    if first["index"] <= row["month"] <= first["index"] + NOVELTY_POST_MONTHS
                ][:8],
            })
        alerts.sort(key=lambda row: -row["statistic"])

        # descriptive novelty comparison: alerted vs never-alerted cells, last 12 months
        alerted = [row for row in alerts if row["novelty"]["post_events"]]
        alert_share = ([row["novelty"]["novelty_share_per_event"] for row in alerted
                        if row["novelty"]["novelty_share_per_event"] is not None])
        alerted_keys = {row["key"] for row in alerts}
        control_shares = []
        for cell in cells:
            key = f"{cell['entity']}|{cell['track']}"
            if key in alerted_keys:
                continue
            events = event_index.get((cell["entity"], cell["track"]), [])
            if not events:
                continue
            novelty = novelty_by_cell(events, WINDOW_MONTHS - NOVELTY_POST_MONTHS)
            if novelty["novelty_share_per_event"] is not None:
                control_shares.append(novelty["novelty_share_per_event"])

        def mean(values: list[float]) -> float | None:
            return sum(values) / len(values) if values else None

        output["detectors"][name] = {
            "calibration": calibration,
            "alerts_total": len(alerts),
            "alerts_surviving_bh": sum(1 for row in alerts if row["survives_bh"]),
            "alert_rate_per_cell": len(alerts) / len(cells) if cells else None,
            "novelty_comparison": {
                "alerted_cells_with_post_activity": len(alert_share),
                "mean_novelty_share_alerted": mean(alert_share),
                "control_cells": len(control_shares),
                "mean_novelty_share_control": mean(control_shares),
                "difference": (mean(alert_share) - mean(control_shares))
                if alert_share and control_shares else None,
            },
            "alerts": alerts,
        }
        print(f"{name}: alerts={len(alerts)} stale-bh={output['detectors'][name]['alerts_surviving_bh']} "
              f"novelty(alerted)={output['detectors'][name]['novelty_comparison']['mean_novelty_share_alerted']} "
              f"novelty(control)={output['detectors'][name]['novelty_comparison']['mean_novelty_share_control']}")
        for row in alerts[:5]:
            print(f"    {row['alert_month']} {row['entity_name'][:34]:34s} {row['track']:22s} "
                  f"stat={row['statistic']:.2f} bh={row['survives_bh']}")

    write_json(Path(args.out), output)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


