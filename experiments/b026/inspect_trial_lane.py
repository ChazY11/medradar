"""Inspect the trial lane for second-domain validation feasibility (company and entity levels)."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

TRIALS = Path("data/b040_device_trials.sqlite")
WINDOW_MONTHS = 119
MIN_HISTORY = 24
MIN_RATE = 0.15

# window starts 2016-11; convert a date to a month index in that window
def month_index(date: str) -> int | None:
    text = str(date)[:10]
    if len(text) < 10:
        return None
    try:
        year, month = int(text[:4]), int(text[5:7])
    except ValueError:
        return None
    index = (year - 2016) * 12 + (month - 11)
    if index < 0:
        index = (year - 2016) * 12 + (month + 1)
    return index if 0 <= index < WINDOW_MONTHS else None


def main() -> int:
    if not TRIALS.exists():
        print("trial database missing")
        return 1
    con = sqlite3.connect(f"file:{TRIALS}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select company_key, track_id, event_date from events where kind='trial'").fetchall()
    con.close()
    cells: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        company = str(row["company_key"] or "")
        track = str(row["track_id"] or "")
        index = month_index(str(row["event_date"] or ""))
        if company and track and index is not None:
            cells[(company, track)].append(index)
    eligible = 0
    for months in cells.values():
        first = sum(1 for month in months if month < MIN_HISTORY)
        if first >= MIN_RATE * MIN_HISTORY:
            eligible += 1
    print(f"trial company-track cells: {len(cells)}; eligible under the same floors: {eligible}")
    print(f"mean events per cell: {sum(len(v) for v in cells.values()) / max(len(cells), 1):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
