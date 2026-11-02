"""Phase 0 audit helper: characterise the large main store and the frozen research lane side by side.

Read-only. Answers the questions the directive asks before any modelling:
  * which tables and source types exist;
  * how many observations per company and per quarter;
  * what the date columns actually are and how they are distributed;
  * whether records carry a publication/availability timestamp separate from the event date.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

STORES = {
    "research": "data/research.sqlite",
    "main_store": "D:/DEPPSKK/medradar/data/medradar.sqlite",
    "device_trials": "data/b040_device_trials.sqlite",
}


def columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]


def main() -> int:
    report: dict = {}
    for label, location in STORES.items():
        path = Path(location)
        if not path.exists():
            report[label] = {"present": False}
            continue
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        block: dict = {"present": True, "tables": {}}
        tables = [row[0] for row in con.execute(
            "select name from sqlite_master where type='table' order by name")]
        for table in tables:
            try:
                count = con.execute(f'select count(*) from "{table}"').fetchone()[0]
            except sqlite3.Error:
                continue
            if not count:
                continue
            cols = columns(con, table)
            info = {"rows": count, "columns": cols}
            # date-like columns: name + observed min/max, because the audit must know what the timestamps mean
            for col in cols:
                lowered = col.lower()
                if not any(token in lowered for token in ("date", "time", "day", "at", "seen")):
                    continue
                try:
                    lo, hi = con.execute(
                        f'select min("{col}"), max("{col}") from "{table}"').fetchone()
                except sqlite3.Error:
                    continue
                info.setdefault("date_columns", {})[col] = {"min": lo, "max": hi}
            # source/subtype distribution where such a column exists
            for col in cols:
                if col.lower() in ("source", "lane", "type", "kind", "dataset", "event_type"):
                    try:
                        values = Counter(row[0] for row in con.execute(
                            f'select "{col}" from "{table}"'))
                    except sqlite3.Error:
                        continue
                    info.setdefault("value_distributions", {})[col] = dict(values.most_common(12))
            block["tables"][table] = info
        con.close()
        report[label] = block

    out = Path("experiments/b080/store_characterisation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
                   encoding="utf-8", newline="\n")

    for label, block in report.items():
        if not block.get("present"):
            print(f"{label}: ABSENT")
            continue
        print("=" * 78)
        print(label)
        for table, info in sorted(block["tables"].items(), key=lambda item: -item[1]["rows"]):
            print(f"  {table} [{info['rows']}] cols: {', '.join(info['columns'])}")
            for col, span in (info.get("date_columns") or {}).items():
                print(f"      {col}: {span['min']} .. {span['max']}")
            for col, dist in (info.get("value_distributions") or {}).items():
                print(f"      {col}: {dist}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
