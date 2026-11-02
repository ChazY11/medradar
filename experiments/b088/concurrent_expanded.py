"""A3: expanded concurrent detection with pre-registered multiplicity control (PHASE1C_PROTOCOL.md).

Cell set is taken verbatim from CELL_INVENTORY.json (coverage only), never from outcomes. Runs the same models as O1
on the 5 both-stream cells (primary) and the 11 regulatory-only cells (secondary), then applies the frozen
sign-test + Holm procedure to the three fusion-vs-single comparisons.

    python experiments/b088/concurrent_expanded.py
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
    holm,
    quarter_index,
    quarter_label,
    rolling_zscore,
    sign_test_p,
    sustained_onsets,
    wilson_interval,
)
from medradar.studies.coverage import quarter_of  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
INVENTORY = Path("research/studies/early_signal_5firms/CELL_INVENTORY.json")
OUT_DIR = Path("research/studies/early_signal_5firms")
SERIES_START, SERIES_END = "2017-Q1", "2025-Q4"
CALIBRATION_END = "2022-Q1"
BUDGET = 2.0
LAG_DAYS = 30
MODEL_NAMES = ("m0_persistence", "m1_regulatory_z", "m2_recall_z", "m5_fused")
FUSION, SINGLES = "m5_fused", ("m0_persistence", "m1_regulatory_z", "m2_recall_z")
ALIASES = {"medtronic": ("MEDTRONIC",), "ge_healthcare": ("GE HEALTHCARE", "GE MEDICAL", "GE HFS", "GEHC"),
           "philips": ("PHILIPS",), "mindray": ("MINDRAY",)}
EXCLUDED_RAW = ("SURGE MEDICAL",)


def parse(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def load_stream(con: sqlite3.Connection, firm: str, track: str, kinds: tuple[str, ...]) -> dict[str, int]:
    rows = []
    for kind in kinds:
        rows += con.execute(
            "select event_date, applicant_raw from events where kind=? and company_key=? and track_id=? "
            "and event_date between ? and ?", (kind, firm, track, "2016-01-01", "2025-12-31")).fetchall()
    if not rows:
        for kind in kinds:
            clause = " or ".join("upper(applicant_raw) like ?" for _ in ALIASES.get(firm, (firm.upper(),)))
            params = [f"%{alias}%" for alias in ALIASES.get(firm, (firm.upper(),))]
            rows += con.execute(
                f"select event_date, applicant_raw from events where kind=? and ({clause}) and track_id=? "
                f"and event_date between ? and ?", [kind, *params, track, "2016-01-01", "2025-12-31"]).fetchall()
    available: dict[str, int] = defaultdict(int)
    for event_date, applicant in rows:
        if any(token in (applicant or "").upper() for token in EXCLUDED_RAW):
            continue
        when = parse(event_date)
        if when is None:
            continue
        label = quarter_of((when + timedelta(days=LAG_DAYS)).isoformat())
        if label and SERIES_START <= label <= SERIES_END:
            available[label] += 1
    return dict(available)


def quarters_between(start: str, end: str) -> list[str]:
    labels, index = [], quarter_index(start)
    while quarter_label(index) <= end:
        labels.append(quarter_label(index))
        index += 1
    return labels


def quarter_end(label: str) -> date:
    year, quarter = label.split("-Q")
    month = int(quarter) * 3
    return date(int(year), month, calendar.monthrange(int(year), month)[1])


def leak_audit(con: sqlite3.Connection, cells: list[dict]) -> dict:
    violations, checked = [], 0
    for cell in cells:
        for kind in ("510k", "pma", "device_recall"):
            rows = con.execute(
                "select event_id, event_date from events where kind=? and company_key=? and track_id=? "
                "and event_date between ? and ?",
                (kind, cell["company"], cell["track"], "2016-01-01", "2025-12-31"))
            for event_id, when in rows:
                event_date = parse(when)
                if event_date is None:
                    continue
                visible = event_date + timedelta(days=LAG_DAYS)
                label = quarter_of(visible.isoformat())
                if label is None:
                    continue
                checked += 1
                if visible > quarter_end(label):
                    violations.append({"event_id": event_id, "visible_at": visible.isoformat(),
                                       "quarter": label})
    return {"events_checked": checked, "violations": len(violations), "examples": violations[:5],
            "rule": f"visibility = event_date + {LAG_DAYS} days, must be <= the real last day of its quarter"}


def run_cell(con: sqlite3.Connection, cell: dict) -> dict:
    reg = load_stream(con, cell["company"], cell["track"], ("510k", "pma"))
    recalls = load_stream(con, cell["company"], cell["track"], ("device_recall",))
    reg_scores = rolling_zscore(reg)
    recall_scores = rolling_zscore(recalls)
    fused = fuse(reg_scores, recall_scores)
    m0 = {}
    for label in sorted(reg):
        index = quarter_index(label)
        baseline = [reg.get(quarter_label(index - offset), 0)
                    for offset in range(MIN_BASELINE_QUARTERS, 0, -1)]
        if len(baseline) < MIN_BASELINE_QUARTERS:
            continue
        m0[label] = float(reg.get(label, 0) > max(baseline)) if baseline else 0.0
    onset_result = sustained_onsets(reg)
    scores = {"m0_persistence": m0, "m1_regulatory_z": reg_scores,
              "m2_recall_z": recall_scores, "m5_fused": fused}
    calibration_quarters = quarters_between(SERIES_START, "2021-Q4")
    evaluation_quarters = quarters_between("2022-Q1", SERIES_END)
    years = len(evaluation_quarters) / 4.0
    onsets_all = set(onset_result["onsets"])
    evaluation_onsets = sorted(onset for onset in onsets_all if onset in evaluation_quarters)
    result = {"company": cell["company"], "track": cell["track"],
              "set": cell.get("set", "primary"),
              "onsets_evaluation": evaluation_onsets,
              "onsets_all": sorted(onsets_all), "censored": onset_result["censored"],
              "models": {}}
    for name in MODEL_NAMES:
        calibration_scores = {label: value for label, value in scores[name].items()
                              if label in calibration_quarters}
        calibration_onsets = [onset for onset in onsets_all if onset in calibration_quarters]
        calibration = calibrate_threshold(calibration_scores, calibration_onsets,
                                          positives=len(calibration_onsets),
                                          negatives=len(calibration_scores) - len(calibration_onsets),
                                          years=len(calibration_quarters) / 4.0,
                                          budget_per_company_year=BUDGET)
        evaluation_scores = {label: value for label, value in scores[name].items()
                             if label in evaluation_quarters}
        if calibration["status"] != "OK":
            result["models"][name] = {"status": "NOT_EVALUABLE", "reason": calibration["reason"]}
            continue
        scored = evaluate(evaluation_scores, evaluation_onsets,
                          threshold=calibration["threshold"], years=years)
        scored["calibration"] = calibration
        scored["status"] = "OK"
        result["models"][name] = scored
    return result


def compare(cells: list[dict], fusion: str, single: str) -> dict:
    pairs = []
    for cell in cells:
        f_block, s_block = cell["models"].get(fusion, {}), cell["models"].get(single, {})
        if f_block.get("status") != "OK" or s_block.get("status") != "OK":
            continue
        f_recall = f_block.get("recall")
        s_recall = s_block.get("recall")
        if f_recall is None or s_recall is None:
            continue
        pairs.append({"cell": f"{cell['company']}|{cell['track']}",
                      "fusion": f_recall, "single": s_recall,
                      "difference": round(f_recall - s_recall, 3)})
    positive = sum(1 for pair in pairs if pair["difference"] > 0)
    negative = sum(1 for pair in pairs if pair["difference"] < 0)
    ties = len(pairs) - positive - negative
    return {"single": single, "cells_compared": len(pairs), "ties_dropped": ties,
            "pairs": pairs, "positive": positive, "negative": negative,
            "sign_test_p": sign_test_p(positive, negative)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=str(INVENTORY))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    primary_cells = [{"company": entry["company"], "track": entry["track"], "set": "primary"}
                     for entry in inventory["both_streams"]]
    secondary_cells = [{"company": entry["company"], "track": entry["track"], "set": "secondary"}
                       for entry in inventory["regulatory_only"]]

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    leak = leak_audit(con, primary_cells)
    if leak["violations"]:
        print(f"ABORT: leak audit reports {leak['violations']} violation(s)")
        return 1

    primary = [run_cell(con, cell) for cell in primary_cells]
    secondary = [run_cell(con, cell) for cell in secondary_cells]
    con.close()

    total_onsets = sum(len(cell["onsets_evaluation"]) for cell in primary)

    def pooled(cells: list[dict], model: str) -> dict:
        usable = [cell for cell in cells if cell["models"].get(model, {}).get("status") == "OK"]
        if not usable:
            return {"status": "NOT_EVALUABLE"}
        hits = sum(cell["models"][model]["hits"] for cell in usable)
        alerts = sum(cell["models"][model]["alerts"] for cell in usable)
        false_alerts = sum(cell["models"][model]["false_alerts"] for cell in usable)
        onsets = sum(len(cell["onsets_evaluation"]) for cell in usable)
        years = 4.0 * len(usable)
        return {"status": "OK", "cells": len(usable), "alerts": alerts, "hits": hits,
                "false_alerts": false_alerts, "onsets": onsets,
                "recall": round(hits / onsets, 3) if onsets else None,
                "recall_interval": wilson_interval(hits, onsets) if onsets else None,
                "precision": round(hits / alerts, 3) if alerts else None,
                "false_alerts_per_company_year": round(false_alerts / years, 3) if years else None}

    pooled_primary = {name: pooled(primary, name) for name in MODEL_NAMES}
    pooled_secondary = {name: pooled(secondary, name) for name in MODEL_NAMES}

    comparisons = {single: compare(primary, FUSION, single) for single in SINGLES}
    pvalues = {single: block["sign_test_p"] for single, block in comparisons.items()}
    adjusted = holm(pvalues)

    underpowered = total_onsets < 10
    best_single = max((pooled_primary[name] for name in SINGLES
                       if pooled_primary[name].get("status") == "OK"),
                      key=lambda block: block.get("recall") or -1, default={})
    fusion = pooled_primary.get(FUSION, {})
    difference = None
    if fusion.get("recall") is not None and best_single.get("recall") is not None:
        difference = round(fusion["recall"] - best_single["recall"], 3)
    steps = {
        "underpowered_clause_satisfied": not underpowered,
        "pooled_difference_at_least_0.10": bool(difference is not None and difference >= 0.10),
        "any_comparison_passes_holm": any(entry["reject"] for entry in adjusted.values()),
    }
    passes = all(steps.values())
    if underpowered:
        verdict = (f"UNDERPOWERED — {total_onsets} onset(s) in the primary evaluation set (floor 10). "
                   f"H1 is neither supported nor refuted; results are descriptive.")
    elif passes:
        verdict = ("H1 SUPPORTED by the pre-registered procedure (underpowered clause satisfied, pooled difference "
                   "≥0.10, and at least one fusion-vs-single comparison survives Holm)")
    else:
        verdict = ("H1 NOT SUPPORTED by this data — the pre-registered steps were not all met; this is not the same "
                   "as refutation")

    payload = {
        "schema": "concurrent_detection_expanded_v1",
        "protocol": "PHASE1C_PROTOCOL.md (frozen before this run)",
        "cell_selection": "CELL_INVENTORY.json (coverage only; contains no outcome quantities)",
        "window": {"calibration": [SERIES_START, "2021-Q4"], "evaluation": ["2022-Q1", SERIES_END]},
        "budget": BUDGET, "leak_audit": leak,
        "primary": primary, "secondary": secondary,
        "pooled_primary": pooled_primary, "pooled_secondary": pooled_secondary,
        "comparisons": comparisons, "holm": adjusted,
        "decision_steps": steps, "pooled_difference_fusion_vs_best_single": difference,
        "totals": {"primary_onsets": total_onsets, "primary_cells": len(primary),
                   "secondary_cells": len(secondary)},
        "verdict": verdict,
        "not_claimed": [
            "no lead-time statement (G1 closed it)",
            "recalls share the regulator with clearances: independence is partial",
            "no causal, intent or R&D claim",
            "H2-H4 untested",
        ],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CONCURRENT_DETECTION_EXPANDED.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# CONCURRENT DETECTION (EXPANDED) — pre-registered multiplicity control", "",
             f"Primary set: **{len(primary)}** both-stream cells · secondary: {len(secondary)} regulatory-only cells · "
             f"budget {BUDGET} false alerts/company-year · leak audit **{leak['violations']}** violations.", "",
             f"**Verdict:** {verdict}", "",
             f"Primary evaluation onsets: **{total_onsets}**", "",
             "## Pooled, primary set", "",
             "| model | cells | alerts | hits | false | recall [95% CI] | precision | FAR/cy |",
             "|---|---:|---:|---:|---:|---|---:|---:|"]
    for name in MODEL_NAMES:
        block = pooled_primary[name]
        if block.get("status") != "OK":
            lines.append(f"| {name} | — | — | — | — | NOT_EVALUABLE | — | — |")
            continue
        lines.append(f"| {name} | {block['cells']} | {block['alerts']} | {block['hits']} | "
                     f"{block['false_alerts']} | {block['recall']} {block['recall_interval']} | "
                     f"{block['precision']} | {block['false_alerts_per_company_year']} |")
    lines += ["", "## Fusion vs single (pre-registered sign test + Holm)", "",
              "| comparison | cells | + | − | ties | sign-test p | Holm p | reject |",
              "|---|---:|---:|---:|---:|---:|---:|---|"]
    for single, block in comparisons.items():
        entry = adjusted[single]
        lines.append(f"| M5 vs {single} | {block['cells_compared']} | {block['positive']} | {block['negative']} | "
                     f"{block['ties_dropped']} | {block['sign_test_p']} | {entry['adjusted_p']} | "
                     f"{'yes' if entry['reject'] else 'no'} |")
    lines += ["", "## Per cell (primary)", "",
              "| cell | onsets (eval) | censored | M1 recall | M2 recall | M5 recall |", "|---|---:|---:|---:|---:|---:|"]
    for cell in primary:
        m1 = cell["models"].get("m1_regulatory_z", {})
        m2 = cell["models"].get("m2_recall_z", {})
        m5 = cell["models"].get("m5_fused", {})
        lines.append(f"| {cell['company']}\\|{cell['track']} | {len(cell['onsets_evaluation'])} | "
                     f"{len(cell['censored'])} | {m1.get('recall', m1.get('status'))} | "
                     f"{m2.get('recall', m2.get('status'))} | {m5.get('recall', m5.get('status'))} |")
    lines += ["", "## Decision steps", ""] + [f"- {name}: {value}" for name, value in steps.items()]
    lines += ["", "## Not claimed", ""] + [f"- {item}" for item in payload["not_claimed"]]
    (out_dir / "CONCURRENT_DETECTION_EXPANDED.md").write_text("\n".join(lines) + "\n",
                                                             encoding="utf-8", newline="\n")

    print(f"primary cells {len(primary)}; secondary {len(secondary)}; primary onsets {total_onsets}; "
          f"leak {leak['violations']}")
    for name in MODEL_NAMES:
        block = pooled_primary[name]
        print(f"  {name:18s} {block.get('status')} recall={block.get('recall')} alerts={block.get('alerts')}")
    print(f"comparisons: " + ", ".join(f"{single}:p={block['sign_test_p']}" for single, block in comparisons.items()))
    print(f"steps: {steps}")
    print(f"verdict: {verdict}")
    print(f"wrote {out_dir}/CONCURRENT_DETECTION_EXPANDED.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
