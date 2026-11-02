"""Build the formatted, drop-down-validated Excel workbook for human review.

The CSV is the portable form; this workbook is the one a person actually edits. It adds what a CSV cannot:

  * frozen header row and an auto-filter, so the reviewer keeps their place through 69 rows;
  * column widths and wrapped text, so dates and evidence are readable instead of `####`;
  * a data-validation drop-down listing exactly the five human labels, so an invalid label cannot be typed;
  * the human columns shaded, so it is obvious which cells are the reviewer's and which are evidence;
  * an INSTRUCTIONS sheet with the label definitions, the independence rule and the submit commands.

    python experiments/b097/build_review_xlsx.py
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

STUDY = Path("research/studies/early_signal_5firms")
LABELS = ["Confirmed Shift", "Routine Iteration", "False Signal / No Confirmed Shift",
          "Uncertain", "Insufficient Observation"]
HUMAN_COLUMNS = ["human_label", "human_reason", "independent_confirmation", "reviewer", "reviewed_at"]
WIDTHS = {
    "packet_id": 12, "origin": 12, "priority": 8, "company": 14, "technology_track": 20, "stratum": 12,
    "event_or_trial_date": 18, "clearance_or_record": 34, "product_code": 12, "mapped_track": 16,
    "third_source_status": 18, "third_source_lead_days": 14, "evidence_summary": 46,
    "agent_preliminary_label": 34, "rule_fired": 40,
    "human_label": 30, "human_reason": 42, "independent_confirmation": 34, "reviewer": 16, "reviewed_at": 20,
}

INSTRUCTIONS = [
    ("HUMAN REVIEW — 69 packets, 69 decisions", ""),
    ("", ""),
    ("What you decide", "One of five labels per row, on the REVIEW sheet."),
    ("Confirmed Shift", "Real sustained change in the firm's technology positioning in that track, AND a confirmation "
                        "independent of the source that raised the packet."),
    ("Routine Iteration", "Ordinary product update within an existing direction."),
    ("False Signal / No Confirmed Shift", "Packet does not correspond to a real change (wrong firm/track/artefact)."),
    ("Uncertain", "Real case, but evidence conflicts or is insufficient to decide."),
    ("Insufficient Observation", "Not enough time or coverage after the event to judge. Censored, not a negative."),
    ("", ""),
    ("Independence rule", "A Confirmed Shift needs a DIFFERENT source family: regulatory-raised packets confirm with a "
                          "trial, publication, 8-K or documented launch; trial-raised packets confirm with a clearance, "
                          "publication or commercial milestone. No independent source -> Uncertain."),
    ("", ""),
    ("What to fill", "human_label (choose from the drop-down), human_reason (one sentence), "
                     "independent_confirmation (required for Confirmed Shift), reviewer (your name), reviewed_at."),
    ("", ""),
    ("Submitting", "Save this workbook, then run:"),
    ("", "python experiments/b098/ingest_human_review.py --in research/studies/early_signal_5firms/"
         "HUMAN_REVIEW_WORKSHEET.xlsx --dry-run"),
    ("", "python experiments/b098/ingest_human_review.py --in research/studies/early_signal_5firms/"
         "HUMAN_REVIEW_WORKSHEET.xlsx"),
    ("", ""),
    ("What the ingester enforces", "Every row needs a valid label, a reviewer and a reason; Confirmed Shift needs an "
                                   "independent confirmation; duplicate packet ids are rejected. Nothing is written "
                                   "until all 69 rows pass."),
    ("", ""),
    ("Evidence columns are pre-filled", "Firm, track, stratum, dates, product code and its mapped track, Europe PMC "
                                        "status and lead, a one-line summary. The agent's preliminary rubric label is "
                                        "shown for contrast only — it is not a label and carries no authority."),
    ("", ""),
    ("Recommended order", "1) LT-07 (only near-term prior publication). 2) LT-05/08/09 (decades-old third-source hits). "
                          "3) novel-entry with consistent mapping. 4) routine controls (should mostly be Routine "
                          "Iteration). 5) unassessable packets."),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=str(STUDY / "HUMAN_REVIEW_WORKSHEET.csv"))
    parser.add_argument("--out", default=str(STUDY / "HUMAN_REVIEW_WORKSHEET.xlsx"))
    args = parser.parse_args(argv)

    with Path(args.csv).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print("no rows to convert")
        return 1
    columns = list(rows[0].keys())

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "REVIEW"
    header_fill = PatternFill("solid", fgColor="1F3864")
    human_fill = PatternFill("solid", fgColor="FFF2CC")
    header_font = Font(bold=True, color="FFFFFF")

    sheet.append(columns)
    for index, column in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(index)].width = WIDTHS.get(column, 18)
        if column in HUMAN_COLUMNS:
            sheet.cell(row=1, column=index).fill = PatternFill("solid", fgColor="BF8F00")

    for row_index, row in enumerate(rows, start=2):
        for column_index, column in enumerate(columns, start=1):
            cell = sheet.cell(row=row_index, column=column_index, value=row.get(column, ""))
            cell.alignment = Alignment(vertical="top", wrap_text=column in
                                       ("evidence_summary", "clearance_or_record", "rule_fired",
                                        "agent_preliminary_label", "human_reason",
                                        "independent_confirmation"))
            if column in HUMAN_COLUMNS:
                cell.fill = human_fill

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"

    label_column = columns.index("human_label") + 1
    label_letter = get_column_letter(label_column)
    validation = DataValidation(type="list", formula1='"' + ",".join(LABELS) + '"', allow_blank=True,
                                showDropDown=False)
    validation.error = "Choose one of the five labels from the drop-down."
    validation.errorTitle = "Not a valid label"
    validation.prompt = "Confirmed Shift / Routine Iteration / False Signal / Uncertain / Insufficient Observation"
    validation.promptTitle = "Human label"
    sheet.add_data_validation(validation)
    validation.add(f"{label_letter}2:{label_letter}{len(rows) + 1}")

    notes = workbook.create_sheet("INSTRUCTIONS")
    notes.column_dimensions["A"].width = 34
    notes.column_dimensions["B"].width = 118
    notes["A1"] = INSTRUCTIONS[0][0]
    notes["A1"].font = Font(bold=True, size=14)
    for row_index, (left, right) in enumerate(INSTRUCTIONS[1:], start=2):
        notes.cell(row=row_index, column=1, value=left).font = Font(bold=True)
        notes.cell(row=row_index, column=2, value=right).alignment = Alignment(wrap_text=True, vertical="top")

    workbook.save(args.out)
    print(f"wrote {args.out}")
    print(f"  rows: {len(rows)}  columns: {len(columns)}  label drop-down rows: {len(rows)}")
    print(f"  sheets: REVIEW, INSTRUCTIONS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
