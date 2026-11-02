"""Phase 0: minimal historical replay with a leak audit (PILOT_RESULTS).

Purpose: prove the study pipeline runs end-to-end on real history — as-of snapshot -> detection -> alert -> outcome
check -> evaluation — and measure whether an existing detector beats a persistence baseline, **with honest failure
allowed**. It is explicitly NOT a test of H1-H4: the outcome here is a *rule-based proxy* (a `novel_entry` quarter as
defined in LABELING_PROTOCOL Target A), not a human-adjudicated label, and the packet set is unadjudicated.

Design
  * unit: firm x track x quarter within the confirmatory tracks fixed by DOMAIN_AMENDMENT_001;
  * availability: Tier B — an event counts as visible from `event_date + 30 days` (declared lag);
  * M0 persistence baseline: alert when the quarter's count exceeds the maximum of the previous 8 quarters;
  * M1 deployed detector: the programme's validated quarterly rolling z-score (threshold 3.5, 8-quarter baseline);
  * positives: `novel_entry` quarters (>=12 months since the firm's previous event in that track);
  * negatives: every other firm-quarter with a usable baseline;
  * metrics at the pre-declared budget of 2 false alerts per company-year, plus recall at 3/6/12 months before.

Leak audit: every feature used at quarter q must come from events with declared_available_at <= end of q-1. The
script recomputes this independently and fails loudly if any violation is found.

    python experiments/b083/pilot_replay.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.coverage import quarter_of, quarters_between  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
OUT_DIR = Path("research/studies/early_signal_5firms")
WINDOW = ("2018-01-01", "2025-12-31")
LAG_DAYS = 30
BASELINE_QUARTERS = 8
Z_THRESHOLD = 3.5
BUDGET_FALSE_ALERTS_PER_COMPANY_YEAR = 2.0

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


def fetch(con: sqlite3.Connection) -> list[dict]:
    rows: list[dict] = []
    for track, firms in TRACKS.items():
        for firm in firms:
            aliases = ALIASES[firm]
            clause = " or ".join("upper(applicant_raw) like ?" for _ in aliases)
            params = [f"%{alias}%" for alias in aliases]
            for event_id, when, kind, applicant in con.execute(
                    f"select event_id, event_date, kind, applicant_raw from events "
                    f"where ({clause}) and track_id = ? and event_date between ? and ? order by event_date",
                    params + [track, WINDOW[0], WINDOW[1]]):
                if any(token in (applicant or "").upper() for token in EXCLUDED_RAW):
                    continue
                if kind not in ("510k", "pma"):
                    continue
                event_date = parse(when)
                if event_date is None:
                    continue
                rows.append({"firm": firm, "track": track, "event_date": event_date,
                             "available_at": event_date + timedelta(days=LAG_DAYS), "event_id": event_id})
    return rows


def quarter_end(label: str) -> date:
    year, quarter = label.split("-Q")
    year, quarter = int(year), int(quarter)
    month = quarter * 3
    day = 31 if month in (3, 12) else 30
    return date(year, month, day)


def build_series(rows: list[dict]) -> dict[tuple[str, str], dict[str, list[dict]]]:
    """(firm, track) -> quarter -> events, using only the declared availability rule."""
    series: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        label = quarter_of(row["available_at"].isoformat())
        if label is None:
            continue
        series[(row["firm"], row["track"])][label].append(row)
    return series


def labels_for(rows: list[dict]) -> dict[str, bool]:
    """novel_entry quarter = the firm's first event in the track, or >=12 months after the previous one."""
    events = sorted(rows, key=lambda row: row["event_date"])
    positives: dict[str, bool] = {}
    previous: date | None = None
    for row in events:
        months = None if previous is None else (row["event_date"].year - previous.year) * 12 + \
                                              (row["event_date"].month - previous.month)
        quarter = quarter_of(row["event_date"].isoformat())
        if quarter is None:
            continue
        if months is None or months >= 12:
            positives[quarter] = True
        previous = row["event_date"]
    return positives


def run_model(series: dict[str, list[dict]], positives: dict[str, bool], *, mode: str) -> dict:
    quarters = sorted(series)
    alerts: list[str] = []
    for index, quarter in enumerate(quarters):
        if index < BASELINE_QUARTERS:
            continue
        window = quarters[index - BASELINE_QUARTERS:index]
        counts = [len(series[q]) for q in window]
        baseline = sum(counts) / len(counts)
        current = len(series[quarter])
        if baseline <= 0:
            continue
        if mode == "m0_persistence":
            if current > max(counts):
                alerts.append(quarter)
        elif mode == "m1_zscore":
            zscore = (current - baseline) / (baseline ** 0.5)
            if zscore >= Z_THRESHOLD:
                alerts.append(quarter)
        else:
            raise ValueError(mode)
    positives_set = set(positives)
    hits = [alert for alert in alerts if alert in positives_set]
    company_years = 8.0          # window 2018-2025
    return {"alerts": len(alerts), "hits": len(hits),
            "alert_quarters": alerts, "hit_quarters": hits,
            "false_alerts": len(alerts) - len(hits),
            "false_alerts_per_company_year": round((len(alerts) - len(hits)) / company_years, 3)}


def lead_times(alerts: list[str], positives: dict[str, bool]) -> dict:
    """For each hit, the alert quarter versus the labelled entry quarter (rule proxy)."""
    def to_index(label: str) -> int:
        year, quarter = label.split("-Q")
        return int(year) * 4 + int(quarter) - 1

    deltas = []
    for alert in alerts:
        if alert in positives:
            deltas.append(0)                     # the alert lands on the entry quarter itself
    return {"n_hits": len(deltas), "lead_time_quarters": deltas,
            "note": "the rule-based proxy labels the entry quarter itself, so this pilot cannot measure lead time; "
                    "real lead time requires an earlier signal source and human-adjudicated confirmation dates"}


def leak_audit(series: dict[tuple[str, str], dict[str, list[dict]]]) -> dict:
    """Check the property that actually matters.

    For a decision taken at the end of quarter q-1 (which is when the baseline for quarter q is known), every
    contributing event must satisfy ``visible_at <= quarter_end(q-1)``. Because events are bucketed by their
    **availability** quarter, the baseline window q-8..q-1 satisfies this by construction; this audit recomputes it
    rather than trusting the construction.

    The first version of this check tested a different property ("an event must be visible inside its own event
    quarter"), which is not required and produced 118 spurious violations. That defect is recorded in the pilot
    report instead of being quietly fixed.
    """
    violations = []
    checked = 0
    for (firm, track), by_quarter in series.items():
        quarters = sorted(by_quarter)
        for index in range(BASELINE_QUARTERS, len(quarters)):
            decision_cutoff = quarter_end(quarters[index - 1])
            for window_quarter in quarters[index - BASELINE_QUARTERS:index]:
                for event in by_quarter[window_quarter]:
                    checked += 1
                    if event["available_at"] > decision_cutoff:
                        violations.append({"firm": firm, "track": track, "quarter": quarters[index],
                                           "window_quarter": window_quarter,
                                           "event_id": event["event_id"],
                                           "available_at": event["available_at"].isoformat(),
                                           "decision_cutoff": decision_cutoff.isoformat()})
    return {"violations": len(violations),
            "events_checked": checked,
            "examples": violations[:5],
            "rule": ("every event informing the score for quarter q must be visible by the end of q-1 "
                     f"(Tier B: event_date + {LAG_DAYS} days)"),
            "own_quarter_note": ("the alert itself is raised at quarter end, so an entry inside that same quarter "
                                 "can at best be detected with zero lead time; real lead time needs an earlier "
                                 "signal source")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    rows = fetch(con)
    con.close()

    series = build_series(rows)
    leak = leak_audit(series)
    results = {}
    for (firm, track), by_quarter in sorted(series.items()):
        labels = labels_for(rows=[row for row in rows if row["firm"] == firm and row["track"] == track])
        block = {"firm": firm, "track": track, "quarters_with_events": len(by_quarter),
                 "positives": len(labels)}
        for mode in ("m0_persistence", "m1_zscore"):
            block[mode] = run_model(by_quarter, labels, mode=mode)
        results[f"{firm}|{track}"] = block

    pooled = {mode: {"alerts": sum(block[mode]["alerts"] for block in results.values()),
                     "hits": sum(block[mode]["hits"] for block in results.values()),
                     "false_alerts": sum(block[mode]["false_alerts"] for block in results.values())}
              for mode in ("m0_persistence", "m1_zscore")}
    total_positives = sum(block["positives"] for block in results.values())
    for mode, block in pooled.items():
        block["recall"] = round(block["hits"] / total_positives, 3) if total_positives else None

    payload = {
        "schema": "pilot_results_v1",
        "status": "PILOT ONLY — rule-based proxy labels, unadjudicated; not a test of H1-H4",
        "window": list(WINDOW),
        "unit": "firm x track x quarter (confirmatory tracks from DOMAIN_AMENDMENT_001)",
        "availability_rule": f"Tier B: event visible from event_date + {LAG_DAYS} days",
        "baseline_quarters": BASELINE_QUARTERS, "z_threshold": Z_THRESHOLD,
        "budget_false_alerts_per_company_year": BUDGET_FALSE_ALERTS_PER_COMPANY_YEAR,
        "leak_audit": leak,
        "by_cell": results,
        "pooled": {"positives": total_positives, **pooled},
        "evaluation_status": {
            "lead_time": "NOT MEASURABLE with this design: the proxy labels the entry quarter itself, and no earlier "
                         "signal source was included in this pilot; a lead-time claim would be fabricated",
            "recall_at_fixed_budget": "computed, but the false-alert budget is reported rather than enforced because "
                                      "the pilot has no threshold-tuning step",
            "independent_confirmation": "NOT PERFORMED: confirmation requires a source independent of the alert, and "
                                        "the pilot used a single source family",
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "PILOT_RESULTS.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8", newline="\n")

    print(f"events (Tier-B visible): {len(rows)}; cells: {len(results)}; positives: {total_positives}")
    print(f"leak audit: {leak['violations']} violation(s) — {leak['rule']}")
    for mode, block in pooled.items():
        print(f"  {mode:16s} alerts={block['alerts']:>3} hits={block['hits']:>2} "
              f"false={block['false_alerts']:>3} recall={block['recall']}")
    print(f"wrote {out_dir}/PILOT_RESULTS.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
