"""S1-crosswalk: re-run the G1 lead/lag gate with trials assigned to device tracks by the keyword crosswalk.

The owner authorised building the crosswalk (STUDY_DECISIONS S-019), so this is a NEW pre-registered scope:

  * a trial is assigned to at most one device track by `medradar.studies.crosswalk` (keyword text match, unique winner,
    ties left unassigned);
  * a pair is a trial assigned to device track T for firm F, and the first 510(k)/PMA for F in T after the trial's
    posting date;
  * eligible pair = lead >= 2 quarters; availability = event_date for both (Tier B, both are publication dates);
  * the frozen G1 criterion applies unchanged: >= 10 eligible pairs across >= 2 firms.

Emits CROSSWALK.json (assignment coverage) and LEAD_LAG_PROBE_CROSSWALK.json/md (pairing + verdict). Read-only.

    python experiments/b092/crosswalk_g1.py
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

from medradar.studies.crosswalk import assign_device_track, coverage, load_keywords  # noqa: E402
from medradar.studies.pairing import describe_leads, pair_first_subsequent  # noqa: E402

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
OUT_DIR = Path("research/studies/early_signal_5firms")
WINDOW = ("2017-01-01", "2025-12-31")
LAG_DAYS = 30
MIN_LEAD_QUARTERS = 2
FIVE_FIRMS = ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")
FLOOR_PAIRS, FLOOR_FIRMS = 10, 2


def parse(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    keywords = load_keywords(con.execute(
        "select id, keywords from tracks where id not like 't\\_%' escape '\\'").fetchall())

    trials = con.execute(
        "select event_id, company_key, event_date, payload from events "
        "where kind='trial' and event_date between ? and ?", WINDOW).fetchall()
    assignments = []
    assigned_rows = []
    for event_id, company, event_date, payload in trials:
        data = json.loads(payload or "{}")
        conditions = data.get("conditions") or []
        text = " ".join([str(item) for item in conditions] + [str(data.get("brief_title") or ""),
                                                             str(data.get("brief_summary") or "")])
        result = assign_device_track(text, keywords)
        assignments.append(result)
        if result["status"] == "assigned" and company in FIVE_FIRMS:
            assigned_rows.append({"event_id": event_id, "company": company, "track": result["track"],
                                  "date": parse(event_date), "matched": result["matched"],
                                  "therapy_track": None})

    coverage_summary = coverage(assignments)
    # per firm x track counts
    by_cell: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in assigned_rows:
        if row["date"] is not None:
            by_cell[(row["company"], row["track"])].append(row)

    pair_results = {}
    all_pairs = []
    for (company, track), rows in sorted(by_cell.items()):
        regulatory = []
        for kind in ("510k", "pma"):
            for (event_date,) in con.execute(
                    "select event_date from events where kind=? and company_key=? and track_id=? "
                    "and event_date between ? and ?", (kind, company, track, WINDOW[0], WINDOW[1])):
                when = parse(event_date)
                if when is not None:
                    regulatory.append({"date": when, "event_id": f"{kind}:{event_date}"})
        paired = pair_first_subsequent([{"date": row["date"], "event_id": row["event_id"],
                                        "resolved_by": "crosswalk"} for row in rows],
                                       regulatory, lag_days=LAG_DAYS,
                                       min_lead_quarters=MIN_LEAD_QUARTERS)
        pair_results[f"{company}|{track}"] = {
            "trials_assigned": len(rows), "regulatory_events": len(regulatory),
            "eligible_pairs": paired["n_pairs"], "below_threshold": paired["n_below_threshold"],
            "unpaired": paired["n_unpaired"],
            "leads": describe_leads(paired["pairs"]),
        }
        all_pairs.extend({**pair, "company": company, "track": track} for pair in paired["pairs"])

    con.close()

    firms_with_pairs = sorted({pair["company"] for pair in all_pairs})
    distinct_later = len({pair["later_id"] for pair in all_pairs})
    verdict_frozen = ("GO" if len(all_pairs) >= FLOOR_PAIRS and len(firms_with_pairs) >= FLOOR_FIRMS
                      else "NO-GO")
    # independence check: several trials can pair to the same later clearance, which is one piece of evidence, not many
    verdict_effective = ("GO" if distinct_later >= FLOOR_PAIRS and len(firms_with_pairs) >= FLOOR_FIRMS
                         else "NO-GO")
    if verdict_frozen == "GO" and verdict_effective == "NO-GO":
        verdict = "GO (frozen count) / FRAGILE (independence check)"
        note = (f"the frozen criterion counts pairs and is met ({len(all_pairs)} pairs, {len(firms_with_pairs)} firms), "
                f"but those pairs reuse only {distinct_later} distinct later clearances, so the independent evidence "
                f"is below the floor of {FLOOR_PAIRS}. The gate passes formally and is fragile in substance.")
    elif verdict_frozen == "GO":
        verdict = "GO"
        note = f"the crosswalk changes the G1 answer ({len(all_pairs)} pairs over {distinct_later} distinct events)"
    else:
        verdict = "NO-GO"
        note = ("the crosswalk does not rescue the G1 gate: the eligible-pair count is still below the frozen floor, so "
                "the NO-GO from PHASE1_SHRINKAGE.md stands")
    payload = {
        "schema": "crosswalk_g1_v1",
        "authorisation": "STUDY_DECISIONS.md S-019 (owner sign-off for the crosswalk)",
        "window": list(WINDOW), "lag_days": LAG_DAYS, "min_lead_quarters": MIN_LEAD_QUARTERS,
        "criteria": {"min_pairs": FLOOR_PAIRS, "min_firms": FLOOR_FIRMS},
        "crosswalk": {
            "method": "deterministic keyword match of trial condition/title against each device track's own keywords; "
                      "unique winner only, ties left unassigned",
            "device_tracks_with_keywords": len(keywords),
            "coverage": coverage_summary,
            "assigned_to_five_firms": len(assigned_rows),
        },
        "pairs_by_cell": pair_results,
        "pairs": all_pairs,
        "eligible_pairs_total": len(all_pairs),
        "distinct_later_events": distinct_later,
        "independence_ratio": round(distinct_later / len(all_pairs), 3) if all_pairs else None,
        "firms_with_pairs": firms_with_pairs,
        "verdict_frozen_count": verdict_frozen,
        "verdict_effective_independence": verdict_effective,
        "verdict": verdict,
        "verdict_note": note,
        "not_claimed": [
            "the crosswalk is a text heuristic, not a validated mapping; its coverage and ambiguity are reported",
            "no lead-time statement is made in either direction unless the gate returns GO",
        ],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CROSSWALK.json").write_text(
        json.dumps({k: payload[k] for k in ("schema", "authorisation", "crosswalk")}, indent=2,
                   ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "LEAD_LAG_PROBE_CROSSWALK.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# G1 RE-RUN WITH THE KEYWORD CROSSWALK (scope S1-crosswalk)", "",
             f"Authorised by S-019. Window {WINDOW[0]} … {WINDOW[1]}; eligible pair = trial → later clearance in the same "
             f"device track with lead ≥ {MIN_LEAD_QUARTERS} quarters; frozen floor {FLOOR_PAIRS} pairs / "
             f"{FLOOR_FIRMS} firms.", "",
             f"**Verdict: {verdict}** — {payload['verdict_note']}", "",
             "## Crosswalk coverage", "",
             f"- device tracks with usable keywords: {len(keywords)}",
             f"- trials in window: {coverage_summary['total']}",
             f"- assigned: {coverage_summary['assigned']} ({coverage_summary['assigned_share']}), "
             f"ambiguous: {coverage_summary['ambiguous']}, no match: {coverage_summary['no_match']}",
             f"- assigned trials belonging to the five study firms: {len(assigned_rows)}", "",
             "## Pairing by cell", "",
             "| cell | trials assigned | regulatory events | eligible pairs | below threshold | median lead (q) |",
             "|---|---:|---:|---:|---:|---:|"]
    for key, block in pair_results.items():
        lines.append(f"| {key} | {block['trials_assigned']} | {block['regulatory_events']} | "
                     f"{block['eligible_pairs']} | {block['below_threshold']} | "
                     f"{block['leads']['median']} |")
    lines += ["", "## Not claimed", ""] + [f"- {item}" for item in payload["not_claimed"]]
    (out_dir / "LEAD_LAG_PROBE_CROSSWALK.md").write_text("\n".join(lines) + "\n",
                                                         encoding="utf-8", newline="\n")

    print(f"crosswalk: {coverage_summary}")
    print(f"assigned trials for the five firms: {len(assigned_rows)}")
    print(f"eligible pairs: {len(all_pairs)} across {len(firms_with_pairs)} firm(s); verdict {verdict}")
    print(f"wrote {out_dir}/CROSSWALK.json and LEAD_LAG_PROBE_CROSSWALK.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
