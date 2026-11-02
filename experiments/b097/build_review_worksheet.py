"""Build the human review worksheet: 69 packets, evidence pre-filled, human columns empty, priority sorted.

Ordering (most likely to yield a decision first):

  1. small-sample packets with a NEAR third-source publication (only one exists);
  2. small-sample packets with DISTANT third-source support (needs a decision: is a decade-old paper relevant?);
  3. novel-entry candidates whose product code maps to the packet's track (evidence-consistent);
  4. routine-stratum candidates (controls: should mostly be Routine Iteration);
  5. everything the rubric could not assess.

Emits HUMAN_REVIEW_WORKSHEET.csv (UTF-8 with BOM, opens cleanly in Excel) and .md.
No label is written; human columns are empty strings.

    python experiments/b097/build_review_worksheet.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

STUDY = Path("research/studies/early_signal_5firms")
STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")

HUMAN_COLUMNS = ["human_label", "human_reason", "independent_confirmation", "reviewer", "reviewed_at"]
EVIDENCE_COLUMNS = ["packet_id", "origin", "priority", "company", "technology_track", "stratum",
                    "event_or_trial_date", "clearance_or_record", "product_code", "mapped_track",
                    "third_source_status", "third_source_lead_days", "evidence_summary",
                    "agent_preliminary_label", "rule_fired"]


def trial_summary(con: sqlite3.Connection, event_id: str | None) -> str:
    if not event_id:
        return ""
    row = con.execute("select payload from events where event_id = ?", (event_id,)).fetchone()
    if not row or not row[0]:
        return ""
    data = json.loads(row[0])
    conditions = ", ".join(str(item) for item in (data.get("conditions") or [])[:3])
    title = str(data.get("brief_title") or "")[:110]
    return f"{title} | conditions: {conditions}".strip(" |")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(STUDY))
    args = parser.parse_args(argv)

    adjudication = json.loads((STUDY / "ADJUDICATION_AGENT_V1.json").read_text(encoding="utf-8"))
    rows = {row["packet_id"]: row for row in adjudication["rows"]}
    candidates = {case["case_id"]: case
                  for case in json.loads((STUDY / "CASE_CANDIDATES.json").read_text(encoding="utf-8"))["cases"]}
    small = {packet["event_id"]: packet for packet in json.loads(
        (STUDY / "CASE_PACKETS_SMALL_SAMPLE_V2.json").read_text(encoding="utf-8"))["packets"]}

    con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    worksheet = []
    for packet_id, row in rows.items():
        origin = row["origin"]
        third = row["rules"].get("R3_third_source")
        if origin == "small_sample":
            packet = small[packet_id]
            third_source = packet.get("third_source") or {}
            priority = (1 if third == "NEAR_SUPPORT" else
                        2 if third == "DISTANT_SUPPORT" else 3)
            record = f"clearance {packet['later_clearance']['date']} ({packet['later_clearance']['kind']})"
            summary = trial_summary(con, (packet.get("representative_trial") or {}).get("id"))
            date_value = (packet.get("representative_trial") or {}).get("date")
            product_code = ""
            mapped = ""
            third_status = third_source.get("status")
            third_lead = third_source.get("lead_days")
        else:
            case = candidates[packet_id]
            priority = (3 if case.get("stratum_by_gap_rule") == "novel_entry" else
                        4 if case.get("stratum_by_gap_rule") == "routine" else 5)
            evidence = case.get("evidence") or {}
            record = (f"{evidence.get('kind')} {case['candidate_alert']['event_date']} "
                      f"({evidence.get('applicant_raw')})")
            summary = f"gap-days={case['candidate_alert'].get('days_since_previous_same_track')}"
            date_value = case["candidate_alert"]["event_date"]
            product_code = str(evidence.get("product_code") or "")
            mapped_row = con.execute("select track_id from product_codes where product_code = ?",
                                     (product_code,)).fetchone() if product_code else None
            mapped = mapped_row[0] if mapped_row else ""
            third_status = "NOT_CHECKED"
            third_lead = ""
        worksheet.append({
            "packet_id": packet_id, "origin": origin, "priority": priority,
            "company": row["company"], "technology_track": row["track"], "stratum": row.get("stratum") or "",
            "event_or_trial_date": date_value or "",
            "clearance_or_record": record, "product_code": product_code, "mapped_track": mapped,
            "third_source_status": third_status or "", "third_source_lead_days": third_lead,
            "evidence_summary": summary,
            "agent_preliminary_label": row["agent_preliminary_label"],
            "rule_fired": row["rule_fired"],
            **{column: "" for column in HUMAN_COLUMNS},
        })
    con.close()

    worksheet.sort(key=lambda item: (item["priority"], str(item["company"]), str(item["technology_track"])))
    out_dir = Path(args.out_dir)
    csv_path = out_dir / "HUMAN_REVIEW_WORKSHEET.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVIDENCE_COLUMNS + HUMAN_COLUMNS)
        writer.writeheader()
        for row in worksheet:
            writer.writerow(row)

    lines = ["# HUMAN REVIEW WORKSHEET — 69 packets, 69 decisions", "",
             "Fill `HUMAN_REVIEW_WORKSHEET.csv` (one row per packet), then run:", "",
             "```bash",
             "python experiments/b098/ingest_human_review.py --in research/studies/early_signal_5firms/HUMAN_REVIEW_WORKSHEET.csv",
             "```", "",
             "**Allowed labels (exact):** `Confirmed Shift`, `Routine Iteration`, `False Signal / No Confirmed Shift`,",
             "`Uncertain`, `Insufficient Observation`. A `Confirmed Shift` additionally needs an independent confirmation.",
             "Every row needs a reviewer name and a reason; the ingest script refuses to write anything otherwise.", "",
             "## Priority order (why this order)", "",
             "1. small-sample packets with a **NEAR** third-source publication — the only ones where an independent",
             "   prior record exists (1 packet);",
             "2. small-sample packets with **DISTANT** support — decide whether a decade-old paper counts (3 packets);",
             "3. novel-entry candidates with a **consistent** product-code mapping (evidence consistent);",
             "4. routine-stratum candidates — the **controls**: these should mostly be `Routine Iteration`;",
             "5. packets the rubric could not assess (no product code / no mapping).", "",
             "## Rows", "",
             "| # | packet | firm | track | stratum | date | third source | agent preliminary |",
             "|---|---|---|---|---|---|---|---|"]
    for index, row in enumerate(worksheet, start=1):
        lines.append(f"| {index} | {row['packet_id']} | {row['company']} | {row['technology_track']} | "
                     f"{row['stratum'] or '—'} | {row['event_or_trial_date']} | "
                     f"{row['third_source_status'] or '—'} | {row['agent_preliminary_label']} |")
    lines += ["", "Evidence columns are pre-filled so no database query is needed; the five human columns are empty.",
              "The agent's preliminary label is **not** a label — it is a rubric output shown for contrast only."]
    (out_dir / "HUMAN_REVIEW_WORKSHEET.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(f"worksheet rows: {len(worksheet)}")
    for index, row in enumerate(worksheet[:10], start=1):
        print(f"  {index:2d}. {row['packet_id']:10s} {row['company']:14s} {row['technology_track']:20s} "
              f"{row['third_source_status'] or '—':16s} {row['agent_preliminary_label']}")
    print(f"wrote {csv_path.name} and HUMAN_REVIEW_WORKSHEET.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
