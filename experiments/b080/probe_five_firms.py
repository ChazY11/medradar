"""Phase 0: quick coverage probe for the five directive companies in the main store.

Read-only. Answers, per firm: which event sources/kinds exist, the date range, how many tracks are touched, and
whether the firm is resolvable at all (key present, aliases matched).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
KEYS = ("medtronic", "ge_healthcare", "philips", "draeger", "mindray")

con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
print("== companies table lookup ==")
for key in KEYS:
    row = con.execute("select key, name_en, name_zh, ticker, country, aliases from companies "
                      "where key = ?", (key,)).fetchone()
    print(f"  {key:14s} -> {row[1] if row else 'NOT FOUND'}"
          f"  ticker={row[3] if row else '-'}  aliases={(row[5][:80] + '...') if row and row[5] else '-'}")

print("\n== events by company x source/kind ==")
for key in KEYS:
    rows = con.execute(
        "select source, kind, count(*), min(event_date), max(event_date) from events "
        "where company_key = ? group by source, kind order by count(*) desc", (key,)).fetchall()
    total = sum(row[2] for row in rows)
    print(f"\n  {key}  total={total}")
    for source, kind, n, lo, hi in rows:
        print(f"    {source:28s} {kind:14s} {n:>7}  {lo} .. {hi}")

print("\n== available tracks touching each firm (top 12 by event count) ==")
for key in KEYS:
    rows = con.execute(
        "select track_id, count(*) from events where company_key = ? and track_id is not null "
        "group by track_id order by count(*) desc limit 12", (key,)).fetchall()
    print(f"  {key:14s} {rows}")

print("\n== the four candidate domains: which tracks exist? ==")
for pattern, label in (("%patient%", "patient monitoring"), ("%imaging%", "imaging"),
                       ("%respir%", "respiratory"), ("%ai%", "medical AI")):
    rows = con.execute("select id, name_en from tracks where id like ?", (pattern,)).fetchall()
    print(f"  {label:20s} {rows}")
con.close()
