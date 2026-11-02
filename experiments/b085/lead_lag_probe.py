"""Phase 1 A2: outcome-blind lead/lag probe on the two confirmatory tracks.

Runs the three scopes frozen in PHASE1_PROTOCOL.md before this script was first executed:

  S1 primary    : trials on the study's device tracks (imaging_us, respiratory) paired to later clearances;
  S2 sensitivity: the assumed crosswalk t_respiratory -> respiratory, labelled as an assumption;
  S3 descriptive: firm level, any trial -> next regulatory event for the same firm.

Reports pair counts, leads in quarters, independent-eligible pairs (lead >= 2 quarters, different source families),
lag sensitivity (+30/60/90 days), late/coincident records, and alias-only flags. A zero result is a result.

    python experiments/b085/lead_lag_probe.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from medradar.studies.coverage import quarter_of  # noqa: E402
from medradar.studies.pairing import (  # noqa: E402
    describe_leads,
    pair_first_subsequent,
)

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
OUT_DIR = Path("research/studies/early_signal_5firms")
WINDOW = ("2018-01-01", "2025-12-31")
FIVE_FIRMS = ("medtronic", "ge_healthcare", "philips", "mindray", "draeger")
CONFIRMATORY = ("imaging_us", "respiratory")
CROSSWALK = {"t_respiratory": "respiratory"}
LAG_VARIANTS = (0, 30, 60, 90)
ELIGIBLE_LEAD_QUARTERS = 2
ALIASES = {
    "medtronic": ("MEDTRONIC",),
    "ge_healthcare": ("GE HEALTHCARE", "GE MEDICAL", "GE HFS", "GEHC"),
    "philips": ("PHILIPS",),
    "draeger": ("DRAGER", "DRAEGERWERK"),
    "mindray": ("MINDRAY",),
}
EXCLUDED_RAW = ("SURGE MEDICAL",)


def connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)


def parse(text: str) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def quarter_index(label: str) -> int:
    year, quarter = label.split("-Q")
    return int(year) * 4 + int(quarter) - 1


def load(con: sqlite3.Connection, kind: str, firm: str, track: str | None
         ) -> list[dict]:
    """Records for one firm, optionally restricted to one track, inside the window."""
    if track is None:
        rows = con.execute(
            "select event_date, track_id, company_key, applicant_raw, event_id, source from events "
            "where kind=? and company_key=? and event_date between ? and ?",
            (kind, firm, *WINDOW)).fetchall()
        resolved = [(row, "company_key") for row in rows]
    else:
        rows = con.execute(
            "select event_date, track_id, company_key, applicant_raw, event_id, source from events "
            "where kind=? and company_key=? and track_id=? and event_date between ? and ?",
            (kind, firm, track, *WINDOW)).fetchall()
        resolved = [(row, "company_key") for row in rows]
    # alias fallback when the roster has no company_key (draeger, mindray)
    if not resolved:
        clause = " or ".join("upper(applicant_raw) like ?" for _ in ALIASES[firm])
        params = [f"%{alias}%" for alias in ALIASES[firm]]
        sql = (f"select event_date, track_id, company_key, applicant_raw, event_id, source from events "
               f"where kind=? and ({clause}) and event_date between ? and ?")
        extra = []
        if track is not None:
            sql += " and track_id=?"
            extra = [track]
        rows = con.execute(sql, [kind, *params, *WINDOW, *extra]).fetchall()
        resolved = [(row, "applicant_alias") for row in rows]
    out = []
    for (event_date, track_id, company, applicant, event_id, source), how in resolved:
        if any(token in (applicant or "").upper() for token in EXCLUDED_RAW):
            continue
        when = parse(event_date)
        if when is None:
            continue
        out.append({"date": when, "track": track_id, "event_id": event_id, "source": source,
                    "resolved_by": how})
    return out


def pair(earlier: list[dict], later: list[dict], lag_days: int) -> dict:
    """Delegate to the tested module; keep the historical keyword name used in this probe."""
    return pair_first_subsequent(earlier, later, lag_days=lag_days,
                                 min_lead_quarters=ELIGIBLE_LEAD_QUARTERS)


def describe(block: dict) -> dict:
    """Distribution summary plus the ambiguity counts the probe reports."""
    summary = describe_leads(block["pairs"])
    return {"n_pairs": block["n_pairs"], "n_below_threshold": block["n_below_threshold"],
            "multiplicity_skipped": block["multiplicity_skipped"],
            "median_lead_quarters": summary["median"],
            "min_lead_quarters": summary["min"],
            "max_lead_quarters": summary["max"],
            "firms_with_eligible_pairs": sorted({entry["resolved_by"] for entry in block["pairs"]})}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args(argv)

    con = connect()
    scope_s1 = {}
    scope_s2 = {}
    scope_s3 = {}
    for firm in FIVE_FIRMS:
        for track in CONFIRMATORY:
            trials = load(con, "trial", firm, track)
            regulatory = load(con, "510k", firm, track) + load(con, "pma", firm, track)
            scope_s1[f"{firm}|{track}"] = {
                "trials": len(trials), "regulatory_events": len(regulatory),
                "by_lag": {str(lag): describe(pair(trials, regulatory, lag)) for lag in LAG_VARIANTS}}
            scope_s1[f"{firm}|{track}"]["pairs_at_zero_lag"] = pair(trials, regulatory, 0)["pairs"][:8]

        for trial_track, device_track in CROSSWALK.items():
            if device_track not in CONFIRMATORY:
                continue
            trials = load(con, "trial", firm, trial_track)
            regulatory = load(con, "510k", firm, device_track) + load(con, "pma", firm, device_track)
            scope_s2[f"{firm}|{trial_track}->{device_track}"] = {
                "trials": len(trials), "regulatory_events": len(regulatory),
                "by_lag": {str(lag): describe(pair(trials, regulatory, lag)) for lag in LAG_VARIANTS}}

        trials_any = load(con, "trial", firm, None)
        regulatory_any = load(con, "510k", firm, None) + load(con, "pma", firm, None)
        scope_s3[firm] = {"trials": len(trials_any), "regulatory_events": len(regulatory_any),
                          "by_lag": {str(lag): describe(pair(trials_any, regulatory_any, lag))
                                     for lag in LAG_VARIANTS}}

    # 8-K: only S3 is meaningful (no track attribution)
    eightk_s3 = {}
    for firm in FIVE_FIRMS:
        earlier = load(con, "8k_catalyst", firm, None)
        regulatory = load(con, "510k", firm, None) + load(con, "pma", firm, None)
        eightk_s3[firm] = {"records": len(earlier), "regulatory_events": len(regulatory),
                           "by_lag": {str(lag): describe(pair(earlier, regulatory, lag))
                                      for lag in LAG_VARIANTS}}
    con.close()

    def eligible_totals(scope: dict) -> dict:
        totals = {}
        for lag in LAG_VARIANTS:
            totals[str(lag)] = sum(scope[key]["by_lag"][str(lag)]["n_pairs"] for key in scope
                                   if "by_lag" in scope[key] and str(lag) in scope[key]["by_lag"])
        return totals

    s1_totals = eligible_totals(scope_s1)
    s2_totals = eligible_totals(scope_s2)
    s3_totals = eligible_totals(scope_s3)

    def firms_with_pairs(scope: dict, lag: int) -> list[str]:
        return sorted({key.split("|")[0] for key, block in scope.items()
                       if block["by_lag"][str(lag)]["n_pairs"] > 0})

    g1 = {
        "criteria": {"min_eligible_pairs": 10, "min_firms": 2, "max_violations": 0},
        "scope_s1": {"eligible_pairs_by_lag": s1_totals,
                     "firms_with_pairs": {str(lag): firms_with_pairs(scope_s1, lag)
                                          for lag in LAG_VARIANTS}},
        "scope_s2_assumed_crosswalk": {"eligible_pairs_by_lag": s2_totals,
                                       "firms_with_pairs": {str(lag): firms_with_pairs(scope_s2, lag)
                                                            for lag in LAG_VARIANTS}},
        "scope_s3_descriptive": {"eligible_pairs_by_lag": s3_totals,
                                 "firms_with_pairs": {str(lag): firms_with_pairs(scope_s3, lag)
                                                      for lag in LAG_VARIANTS}},
        "eightk_scope_s3": {firm: {"records": block["records"],
                                   "eligible_pairs_by_lag": {lag: block["by_lag"][str(lag)]["n_pairs"]
                                                             for lag in LAG_VARIANTS}}
                            for firm, block in eightk_s3.items()},
    }
    best_scope = max((("S1", s1_totals), ("S2", s2_totals)), key=lambda item: item[1]["0"])
    zero_pairs, firms_at_zero = best_scope[1]["0"], len(firms_with_pairs(
        scope_s1 if best_scope[0] == "S1" else scope_s2, 0))
    if zero_pairs >= 10 and firms_at_zero >= 2:
        verdict = f"G1 = GO via {best_scope[0]} ({zero_pairs} eligible pairs, {firms_at_zero} firms)"
    elif zero_pairs == 0:
        verdict = ("G1 = NOT_EVALUABLE for lead time: no eligible pair can be constructed in S1 or S2, because the "
                   "trial lane uses therapy-area tracks and only one crosswalk candidate touches a confirmatory "
                   "track, where it carries too few records")
    else:
        verdict = (f"G1 = NO-GO: best scope {best_scope[0]} yields {zero_pairs} eligible pairs across "
                   f"{firms_at_zero} firms, below the frozen floor of 10 pairs / 2 firms")
    g1["best_scope"] = best_scope[0]
    g1["verdict"] = verdict

    payload = {
        "schema": "lead_lag_probe_v1",
        "protocol": "PHASE1_PROTOCOL.md (frozen before this probe ran)",
        "window": list(WINDOW),
        "eligibility": {"min_lead_quarters": ELIGIBLE_LEAD_QUARTERS},
        "scope_s1_primary": scope_s1,
        "scope_s2_assumed_crosswalk": scope_s2,
        "scope_s3_descriptive": scope_s3,
        "eightk_s3": eightk_s3,
        "g1": g1,
        "notes": [
            "a pair requires the later event to be strictly after the earlier record's availability",
            "only the first later event per earlier record counts; skipped multiplicity is reported",
            "pairs with lead < 2 quarters are counted separately as below-threshold, not silently dropped",
            "S2 uses an assumed crosswalk and must never be pooled with S1",
            "no detection model is involved: this probe measures whether pairing is possible at all",
        ],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "LEAD_LAG_PROBE.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    lines = ["# LEAD/LAG PROBE — can trials be paired to later regulatory events?", "",
             f"Window {WINDOW[0]} … {WINDOW[1]}. Protocol frozen first in `PHASE1_PROTOCOL.md`.", "",
             "## Verdict (frozen G1 criteria: ≥10 eligible pairs, ≥2 firms)", "",
             f"**{verdict}**", "",
             "## S1 primary — trials on device tracks", "",
             "| firm | track | trials | regulatory events | eligible pairs (lag 0 / 30 / 60 / 90 d) |",
             "|---|---|---:|---:|---|"]
    for key, block in scope_s1.items():
        firm, track = key.split("|")
        by_lag = " / ".join(str(block["by_lag"][str(lag)]["n_pairs"]) for lag in LAG_VARIANTS)
        lines.append(f"| {firm} | {track} | {block['trials']} | {block['regulatory_events']} | {by_lag} |")
    lines += ["", "## S2 sensitivity — assumed crosswalk `t_respiratory` → `respiratory`", "",
              "> Assumed mapping (id-identical after the `t_` prefix). Never pooled with S1.", "",
              "| firm | scope | trials | regulatory events | eligible pairs (0/30/60/90 d) |",
              "|---|---|---:|---:|---|"]
    for key, block in scope_s2.items():
        firm, scope = key.split("|")
        by_lag = " / ".join(str(block["by_lag"][str(lag)]["n_pairs"]) for lag in LAG_VARIANTS)
        lines.append(f"| {firm} | {scope} | {block['trials']} | {block['regulatory_events']} | {by_lag} |")
    lines += ["", "## S3 descriptive — firm level (any trial → next regulatory event)", "",
              "| firm | trials | regulatory events | eligible pairs (0/30/60/90 d) |", "|---|---:|---:|---|"]
    for firm, block in scope_s3.items():
        by_lag = " / ".join(str(block["by_lag"][str(lag)]["n_pairs"]) for lag in LAG_VARIANTS)
        lines.append(f"| {firm} | {block['trials']} | {block['regulatory_events']} | {by_lag} |")
    lines += ["", "## SEC 8-K (no track attribution; descriptive only)", "",
              "| firm | records | regulatory events | eligible pairs (0/30/60/90 d) |", "|---|---:|---:|---|"]
    for firm, block in eightk_s3.items():
        by_lag = " / ".join(str(block["by_lag"][str(lag)]["n_pairs"]) for lag in LAG_VARIANTS)
        lines.append(f"| {firm} | {block['records']} | {block['regulatory_events']} | {by_lag} |")
    lines += ["", "## Notes", ""] + [f"- {note}" for note in payload["notes"]]
    (out_dir / "LEAD_LAG_PROBE.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"S1 eligible pairs by lag: {s1_totals}")
    print(f"S2 (assumed crosswalk) by lag: {s2_totals}")
    print(f"S3 descriptive by lag: {s3_totals}")
    print(f"verdict: {verdict}")
    print(f"wrote {out_dir}/LEAD_LAG_PROBE.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
