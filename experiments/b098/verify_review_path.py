"""Prove the whole human-review path works: fill a TEMP copy, dry-run it, and check the refusal cases.

Writes only to a temporary file under the system temp directory; never writes ADJUDICATION_HUMAN_V1.json, so no
synthetic label can leak into the study.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook

STUDY = Path("research/studies/early_signal_5firms")
SOURCE = STUDY / "HUMAN_REVIEW_WORKSHEET.xlsx"
LABELS = ["Confirmed Shift", "Routine Iteration", "False Signal / No Confirmed Shift", "Uncertain",
          "Insufficient Observation"]


def fill(path: Path, *, skip_reviewer_on: str | None = None, confirmed_without_independence: bool = False,
         bad_label_on: str | None = None) -> None:
    workbook = load_workbook(path)
    sheet = workbook["REVIEW"]
    header = [cell.value for cell in sheet[1]]
    index = {name: position + 1 for position, name in enumerate(header)}
    for row in range(2, sheet.max_row + 1):
        packet = str(sheet.cell(row=row, column=index["packet_id"]).value)
        label = LABELS[(row - 2) % len(LABELS)]
        if bad_label_on and packet == bad_label_on:
            label = "looks promising"
        sheet.cell(row=row, column=index["human_label"], value=label)
        sheet.cell(row=row, column=index["human_reason"],
                   value="dry-run reason: evidence checked, decision recorded for validation only")
        sheet.cell(row=row, column=index["reviewer"],
                   value="" if packet == skip_reviewer_on else "validation-run")
        sheet.cell(row=row, column=index["reviewed_at"], value="2026-11-04 10:00 +08:00")
        if label == "Confirmed Shift":
            sheet.cell(row=row, column=index["independent_confirmation"],
                       value="" if confirmed_without_independence else "PMID 1234567")
    workbook.save(path)


def run(path: Path) -> tuple[int, str]:
    result = subprocess.run([sys.executable, "experiments/b098/ingest_human_review.py", "--in", str(path),
                             "--out", str(Path(tempfile.gettempdir()) / "should_not_exist.json"), "--dry-run"],
                            capture_output=True, text=True, timeout=600)
    return result.returncode, (result.stdout + result.stderr).strip()


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="medradar-review-"))
    try:
        cases = {}
        complete = temp_dir / "complete.xlsx"
        shutil.copy(SOURCE, complete)
        fill(complete)
        cases["complete->accept"] = run(complete)

        missing_reviewer = temp_dir / "missing_reviewer.xlsx"
        shutil.copy(SOURCE, missing_reviewer)
        fill(missing_reviewer, skip_reviewer_on="LT-07")
        cases["missing reviewer->refuse"] = run(missing_reviewer)

        no_independence = temp_dir / "no_independence.xlsx"
        shutil.copy(SOURCE, no_independence)
        fill(no_independence, confirmed_without_independence=True)
        cases["confirmed without independence->refuse"] = run(no_independence)

        bad_label = temp_dir / "bad_label.xlsx"
        shutil.copy(SOURCE, bad_label)
        fill(bad_label, bad_label_on="LT-05")
        cases["bad label->refuse"] = run(bad_label)

        ok = True
        for name, (code, output) in cases.items():
            expectation = "accept" if "->accept" in name else "refuse"
            passed = (code == 0) if expectation == "accept" else (code == 2)
            ok = ok and passed
            first = output.splitlines()[0] if output else ""
            print(f"{'PASS' if passed else 'FAIL'}  {name:42s} exit={code}  {first[:90]}")
        leaked = Path(tempfile.gettempdir()) / "should_not_exist.json"
        print(f"{'PASS' if not leaked.exists() else 'FAIL'}  no output file written")
        return 0 if ok and not leaked.exists() else 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
