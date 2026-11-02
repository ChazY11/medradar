"""Phase 0: dump the real schema and row counts of every store the study could use.

Read-only. This runs BEFORE any coverage or point-in-time claim: the study must know which timestamp columns
actually exist, and which lanes exist at all, rather than assuming.

Stores:
  data/research.sqlite               frozen research lane (curated roster + financial/market/publication lanes)
  data/b040_device_trials.sqlite     device trial lane
  data/registry.sqlite               legacy forecast registry
  data/tkg.sqlite                    bitemporal temporal knowledge graph
  D:/DEPPSKK/medradar/data/medradar.sqlite   the large main-clone store (unaudited for this study)

    python tools/dump_store_schema.py [--out experiments/b080/store_schema.json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

STORES = (
    ("research", "data/research.sqlite"),
    ("device_trials", "data/b040_device_trials.sqlite"),
    ("registry", "data/registry.sqlite"),
    ("tkg", "data/tkg.sqlite"),
    ("main_store", "D:/DEPPSKK/medradar/data/medradar.sqlite"),
)


def describe(path: Path) -> dict:
    if not path.exists():
        return {"present": False}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables = {}
    for (name,) in con.execute("select name from sqlite_master where type='table' order by name"):
        columns = [row[1] for row in con.execute(f'PRAGMA table_info("{name}")')]
        try:
            count = con.execute(f'select count(*) from "{name}"').fetchone()[0]
        except sqlite3.Error:
            count = None
        tables[name] = {"rows": count, "columns": columns}
    con.close()
    return {"present": True, "size_mb": round(path.stat().st_size / 1e6, 1), "tables": tables}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiments/b080/store_schema.json")
    args = parser.parse_args(argv)

    payload = {"schema": "store_schema_v1", "stores": {}}
    for label, location in STORES:
        info = describe(Path(location))
        payload["stores"][label] = {"path": location, **info}
        if not info.get("present"):
            print(f"{label:14s} ABSENT      {location}")
            continue
        non_empty = {name: block["rows"] for name, block in info["tables"].items() if block["rows"]}
        print(f"{label:14s} {info['size_mb']:8.1f} MB  {len(non_empty)} non-empty tables")
        for name, rows in sorted(non_empty.items(), key=lambda item: -(item[1] or 0))[:12]:
            print(f"    {name:26s} {rows:>9}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                   newline="\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
