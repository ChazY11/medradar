"""Read-only structural inspection of the existing MedRadar evidence database.

Phase 4 needs to link candidate hiring signals to *independent* evidence that the
programme already holds. This script answers only: what tables exist, how many rows,
and which columns could identify (a) a company and (b) a technology direction.
It opens the database with mode=ro and writes nothing.
"""
from __future__ import annotations

import sqlite3
import sys


def main(path: str) -> int:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]
    print(f"{path}: {len(tables)} tables")
    for t in tables:
        try:
            n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
        except Exception as exc:  # noqa: BLE001
            print(f"  {t}: unreadable ({exc})")
            continue
        cols = [c[1] for c in con.execute(f'pragma table_info("{t}")')]
        print(f"  {t}: {n} rows | {', '.join(cols[:16])}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
