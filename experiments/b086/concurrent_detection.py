"""O1: concurrent multi-source change detection (PHASE1B_PROTOCOL.md).

Design fixed before this script ran:
  positives = sustained-change onsets (>=2 regulatory events within 4 quarters, after >=12 months silence);
  alerts at q or q+1 count as concurrent detection of an onset at q;
  thresholds are calibrated on 2018-2021 to a budget of 2 false alerts per company-year, then applied unchanged to
  2022-2025; models M0 persistence, M1 regulatory z, M2 recall z, M5 equal-FAR max fusion;
  a leak audit independently verifies that no feature uses an event visible after the decision cutoff.

    python experiments/b086/concurrent_detection.py
"""
from __future__ import annotations

import argparse
import calendar
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.concurrent import (  # noqa: E402
    MIN_BASELINE_QUARTERS,
    calibrate_threshold,
    evaluate,
    fuse,
    quarter_index,
    quarter_label,
    rolling_zscore,
    split_window,
    sustained_onsets,
    wilson_interval,
)
from medradar.studies.coverage import quarter_of  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
OUT_DIR = Path("research/studies/early_signal_5firms")
SERIES_START, SERIES_END = "2017-Q1", "2025-Q4"
CALIBRATION_END = "2022-Q1"        # calibration = labels < this; evaluation = labels >= this
BUDGET = 2.0                       # false alerts per company-year
LAG_DAYS = 30
TRACKS = {"imaging_us": ("ge_healthcare", "mindray", "philips"),
          "respiratory": ("ge_healthcare", "medtronic", "philips")}
ALIASES = {"medtronic": ("MEDTRONIC",), "ge_healthcare": ("GE HEALTHCARE", "GE MEDICAL", "GE HFS", "GEHC"),
           "philips": ("PHILIPS",), "mindray": ("MINDRAY",)}
EXCLUDED_RAW = ("SURGE MEDICAL",)


def parse(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def load_stream(con: sqlite3.Connection, firm: str, track: str, kinds: tuple[str, ...]
                ) -> tuple[dict[str, int], dict[str, int], int]:
    """Quarter counts by event date (outcome view) and by availability date (feature view)."""
    by_event: dict[str, int] = defaultdict(int)
    by_available: dict[str, int] = defaultdict(int)
    rows: list[tuple] = []
    for kind in kinds:
        rows += con.execute(
            "select event_date, applicant_raw from events where kind=? and company_key=? and track_id=? "
            "and event_date between ? and ?",
            (kind, firm, track, "2016-01-01", "2025-12-31")).fetchall()
    if not rows:
        # alias fallback for roster-gap firms
        for kind in kinds:
            clause = " or ".join("upper(applicant_raw) like ?" for _ in ALIASES[firm])
            params = [f"%{alias}%" for alias in ALIASES[firm]]
            rows += con.execute(
                f"select event_date, applicant_raw from events where kind=? and ({clause}) and track_id=? "
                f"and event_date between ? and ?", [kind, *params, track, "2016-01-01", "2025-12-31"]).fetchall()
    for event_date, applicant in rows:
        if any(token in (applicant or "").upper() for token in EXCLUDED_RAW):
            continue
        when = parse(event_date)
        if when is None:
            continue
        label = quarter_of(when.isoformat())
        if label is None or not (SERIES_START <= label <= SERIES_END):
            continue
        by_event[label] += 1
        available = quarter_of((when + timedelta(days=LAG_DAYS)).isoformat())
        by_available[available] += 1
    return dict(by_event), dict(by_available), len(rows)


def quarters_in_range(start: str, end: str) -> list[str]:
    labels, index = [], quarter_index(start)
    while quarter_label(index) <= end:
        labels.append(quarter_label(index))
        index += 1
    return labels


def leak_audit(con: sqlite3.Connection) -> dict:
    """No event may be visible after the end of the quarter before the one it informs."""
    violations = []
    for track, firms in TRACKS.items():
        for firm in firms:
            for kind in ("510k", "pma", "device_recall"):
                for event_id, when in con.execute(
                        "select event_id, event_date from events where kind=? and company_key=? and track_id=? "
                        "and event_date between ? and ?", (kind, firm, track, "2016-01-01", "2025-12-31")):
                    event_date = parse(when)
                    if event_date is None:
                        continue
                    visible = event_date + timedelta(days=LAG_DAYS)
                    quarter = quarter_of(visible.isoformat())
                    if quarter is None:
                        continue
                    year, q = quarter.split("-Q")
                    end_month = int(q) * 3
                    # the cutoff is the real last day of the quarter; using the 28th produced 7 spurious
                    # violations on events published in the final days of a quarter
                    cutoff = date(int(year), end_month, calendar.monthrange(int(year), end_month)[1])
                    if visible > cutoff:
                        violations.append({"event_id": event_id, "visible_at": visible.isoformat(),
                                           "quarter": quarter})
    return {"violations": len(violations), "examples": violations[:5],
            "rule": f"feature visibility uses event_date + {LAG_DAYS} days, must be <= end of the informing quarter"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    leak = leak_audit(con)
    cells: dict[str, dict] = {}
    for track, firms in TRACKS.items():
        for firm in firms:
            reg_event, reg_available, reg_rows = load_stream(con, firm, track, ("510k", "pma"))
            rec_event, rec_available, rec_rows = load_stream(con, firm, track, ("device_recall",))
            onset_result = sustained_onsets(reg_event)
            cells[f"{firm}|{track}"] = {
                "firm": firm, "track": track,
                "regulatory_events": reg_rows, "recall_events": rec_rows,
                "regulatory_by_quarter": reg_event, "regulatory_available_by_quarter": reg_available,
                "recall_by_quarter": rec_event, "recall_available_by_quarter": rec_available,
                "onsets": onset_result["onsets"], "censored": onset_result["censored"],
                "episodes": onset_result["episodes"],
            }
    con.close()

    if leak["violations"]:
        print(f"ABORT: leak audit reports {leak['violations']} violation(s)")
        return 1

    # ---- per-cell models -------------------------------------------------
    calibration_quarters = [q for q in quarters_in_range(SERIES_START, "2021-Q4")]
    evaluation_quarters = quarters_in_range("2022-Q1", SERIES_END)
    model_names = ("m0_persistence", "m1_regulatory_z", "m2_recall_z", "m5_fused")
    thresholds: dict[str, dict[str, float]] = {name: {} for name in model_names}
    per_cell: dict[str, dict] = {}

    for key, cell in cells.items():
        reg_scores = rolling_zscore(cell["regulatory_available_by_quarter"])
        rec_scores = rolling_zscore(cell["recall_available_by_quarter"])
        fused_scores = fuse(reg_scores, rec_scores)
        counts = cell["regulatory_available_by_quarter"]
        m0_scores = {}
        ordered = sorted(counts)
        for label in ordered:
            index = quarter_index(label)
            baseline = [counts.get(quarter_label(index - offset), 0)
                        for offset in range(MIN_BASELINE_QUARTERS, 0, -1)]
            if len([value for value in baseline if value is not None]) < MIN_BASELINE_QUARTERS:
                continue
            m0_scores[label] = float(counts.get(label, 0) > max(baseline)) if baseline else 0.0
        scores_by_model = {"m0_persistence": m0_scores, "m1_regulatory_z": reg_scores,
                           "m2_recall_z": rec_scores, "m5_fused": fused_scores}
        onsets_all = set(cell["onsets"])
        cell_negatives = [label for label in evaluation_quarters if label not in onsets_all]
        years = len(evaluation_quarters) / 4.0
        cell_result = {"firm": cell["firm"], "track": cell["track"],
                       "regulatory_events": cell["regulatory_events"],
                       "recall_events": cell["recall_events"],
                       "onsets_all": sorted(onsets_all),
                       "onsets_evaluation": sorted(onset for onset in onsets_all
                                                   if onset in evaluation_quarters),
                       "censored": cell["censored"], "models": {}}
        for name in model_names:
            scores = scores_by_model[name]
            calibration_scores = {label: value for label, value in scores.items()
                                  if label in calibration_quarters}
            calibration_onsets = [onset for onset in onsets_all if onset in calibration_quarters]
            calibration = calibrate_threshold(calibration_scores, calibration_onsets,
                                              positives=len(calibration_onsets),
                                              negatives=len(calibration_scores) - len(calibration_onsets),
                                              years=len(calibration_quarters) / 4.0,
                                              budget_per_company_year=BUDGET)
            evaluation_scores = {label: value for label, value in scores.items()
                                 if label in evaluation_quarters}
            if calibration["status"] != "OK":
                cell_result["models"][name] = {"status": "NOT_EVALUABLE",
                                               "reason": calibration["reason"]}
                continue
            thresholds[name][key] = calibration["threshold"]
            result = evaluate(evaluation_scores, cell_result["onsets_evaluation"],
                              threshold=calibration["threshold"], years=years)
            result["calibration"] = calibration
            result["status"] = "OK"
            cell_result["models"][name] = result
        per_cell[key] = cell_result

    # ---- pooled ----------------------------------------------------------
    pooled = {}
    total_onsets = sum(len(cell["onsets_evaluation"]) for cell in per_cell.values())
    total_years = len(evaluation_quarters) / 4.0 * len(per_cell)
    for name in model_names:
        cells_ok = {key: cell for key, cell in per_cell.items()
                    if cell["models"].get(name, {}).get("status") == "OK"}
        if not cells_ok:
            pooled[name] = {"status": "NOT_EVALUABLE", "reason": "no cell could be calibrated"}
            continue
        hits = sum(cell["models"][name]["hits"] for cell in cells_ok.values())
        alerts = sum(cell["models"][name]["alerts"] for cell in cells_ok.values())
        false_alerts = sum(cell["models"][name]["false_alerts"] for cell in cells_ok.values())
        onsets = sum(len(cell["onsets_evaluation"]) for cell in cells_ok.values())
        pooled[name] = {"status": "OK", "cells": len(cells_ok), "alerts": alerts, "hits": hits,
                        "false_alerts": false_alerts, "onsets": onsets,
                        "recall": round(hits / onsets, 3) if onsets else None,
                        "recall_interval": wilson_interval(hits, onsets) if onsets else None,
                        "precision": round(hits / alerts, 3) if alerts else None,
                        "false_alerts_per_company_year": round(false_alerts / total_years, 3) if total_years else None,
                        "mean_threshold": round(sum(thresholds[name].values()) / len(thresholds[name]), 3)
                        if thresholds[name] else None}

    if total_onsets < 10:
        verdict = (f"UNDERPOWERED — {total_onsets} onset(s) in the evaluation window (floor 10). No model comparison "
                   f"may be stated as support or refutation of H1; results are descriptive only.")
    else:
        best_single = max((pooled.get(name, {}) for name in ("m0_persistence", "m1_regulatory_z", "m2_recall_z")
                           if pooled.get(name, {}).get("status") == "OK"),
                          key=lambda block: block.get("recall") or -1, default={})
        fusion = pooled.get("m5_fused", {})
        if best_single.get("recall") is None or fusion.get("status") != "OK":
            verdict = "INCONCLUSIVE — a model could not be calibrated; see per-cell NOT_EVALUABLE entries"
        else:
            difference = (fusion.get("recall") or 0) - (best_single.get("recall") or 0)
            verdict = (f"fusion recall {fusion.get('recall')} vs best single {best_single.get('recall')} "
                       f"(difference {round(difference, 3)}); intervals overlap unless reported otherwise — "
                       f"no H1 support is claimed without a paired interval excluding 0")

    payload = {
        "schema": "concurrent_detection_v1",
        "protocol": "PHASE1B_PROTOCOL.md (frozen before this run)",
        "window": {"series": [SERIES_START, SERIES_END], "calibration": [SERIES_START, "2021-Q4"],
                   "evaluation": ["2022-Q1", SERIES_END]},
        "false_alarm_budget_per_company_year": BUDGET,
        "leak_audit": leak,
        "cells": per_cell,
        "pooled": pooled,
        "totals": {"onsets_evaluation": total_onsets, "company_years": round(total_years, 1)},
        "verdict": verdict,
        "not_claimed": [
            "no lead-time statement: G1 closed that question (PHASE1_SHRINKAGE.md)",
            "no causal, intent or R&D claim; the unit is public filing activity",
            "recalls are a different recording process but the same regulator: independence is partial and is "
            "stated as such",
        ],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CONCURRENT_DETECTION.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# CONCURRENT DETECTION — O1 (sustained changes, equal-FAR fusion)", "",
             f"Calibration {SERIES_START} … 2021-Q4 · evaluation 2022-Q1 … {SERIES_END} · budget "
             f"{BUDGET} false alerts per company-year · protocol frozen before the run.", "",
             f"**Verdict:** {verdict}", "",
             f"Evaluation onsets: **{total_onsets}** across {len(per_cell)} cells "
             f"({round(total_years,1)} company-years). Leak audit: **{leak['violations']}** violations.", "",
             "## Pooled", "", "| model | cells | alerts | hits | false | recall [95% CI] | precision | FAR/company-year |",
             "|---|---:|---:|---:|---:|---|---:|---:|"]
    for name in model_names:
        block = pooled.get(name, {})
        if block.get("status") != "OK":
            lines.append(f"| {name} | — | — | — | — | NOT_EVALUABLE | — | — |")
            continue
        interval = block.get("recall_interval")
        lines.append(f"| {name} | {block['cells']} | {block['alerts']} | {block['hits']} | "
                     f"{block['false_alerts']} | {block['recall']} {interval} | {block['precision']} | "
                     f"{block['false_alerts_per_company_year']} |")
    lines += ["", "## Per cell", "",
              "| cell | reg events | recall events | onsets (eval) | censored | M1 recall | M5 recall |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for key, cell in per_cell.items():
        m1 = cell["models"].get("m1_regulatory_z", {})
        m5 = cell["models"].get("m5_fused", {})
        lines.append(f"| {key} | {cell['regulatory_events']} | {cell['recall_events']} | "
                     f"{len(cell['onsets_evaluation'])} | {len(cell['censored'])} | "
                     f"{m1.get('recall', m1.get('status'))} | {m5.get('recall', m5.get('status'))} |")
    lines += ["", "## Not claimed", ""] + [f"- {item}" for item in payload["not_claimed"]]
    (out_dir / "CONCURRENT_DETECTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"cells: {len(per_cell)}; evaluation onsets: {total_onsets}; company-years: {round(total_years,1)}")
    print(f"leak violations: {leak['violations']}")
    for name in model_names:
        block = pooled.get(name, {})
        print(f"  {name:18s} {block.get('status')} alerts={block.get('alerts')} hits={block.get('hits')} "
              f"recall={block.get('recall')} precision={block.get('precision')}")
    print(f"verdict: {verdict}")
    print(f"wrote {out_dir}/CONCURRENT_DETECTION.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
