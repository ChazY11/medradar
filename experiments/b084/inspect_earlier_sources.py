"""Phase 1 A1 helper: what do ctgov and SEC 8-K records actually carry?

Read-only. Before any pairing, the audit must know the semantics: which date fields exist, what they mean, whether a
trial start can precede a clearance by construction, and how many records exist per firm/track in the window.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

STORE = Path("D:/DEPPSKK/medradar/data/medradar.sqlite")
KEYS = ("medtronic", "ge_healthcare", "philips", "mindray", "draeger")
KINDS = ("trial", "8k_catalyst")

con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)

print("== counts by kind ==")
for kind in KINDS:
    total = con.execute("select count(*) from events where kind = ?", (kind,)).fetchone()[0]
    with_key = con.execute("select count(*) from events where kind = ? and company_key is not null", (kind,)).fetchone()[0]
    print(f"  {kind:14s} total={total:>7}  with company_key={with_key:>7}")

print("\n== sample payload keys for a trial row ==")
row = con.execute("select event_id, company_key, track_id, event_date, published_at, available_at, "
                  "timestamp_quality, payload from events where kind = 'trial' limit 1").fetchone()
if row:
    event_id, company, track, event_date, published, available, quality, payload = row
    print(f"  event_id={event_id} company={company} track={track}")
    print(f"  event_date={event_date} published_at={published} available_at={available} quality={quality}")
    data = json.loads(payload) if payload else {}
    print(f"  payload keys: {sorted(data)}")
    for key in ("start_date", "primary_completion_date", "completion_date", "study_first_posted",
                "last_update_posted", "results_first_posted", "phase", "status", "sponsor"):
        if key in data:
            print(f"    {key}: {data[key]!r}"[:160])

print("\n== sample payload keys for an 8-K row ==")
row = con.execute("select event_id, company_key, track_id, event_date, available_at, payload from events "
                  "where kind = '8k_catalyst' limit 1").fetchone()
if row:
    event_id, company, track, event_date, available, payload = row
    print(f"  event_id={event_id} company={company} track={track} event_date={event_date} available_at={available}")
    data = json.loads(payload) if payload else {}
    print(f"  payload keys: {sorted(data)}")
    for key in list(sorted(data))[:12]:
        print(f"    {key}: {str(data[key])[:120]}")

print("\n== trials per firm x track (top 12 each) ==")
for key in KEYS:
    rows = con.execute("select track_id, count(*) from events where kind='trial' and company_key=? "
                       "group by track_id order by count(*) desc limit 12", (key,)).fetchall()
    print(f"  {key:14s} {rows}")

print("\n== 8-K per firm x track ==")
for key in KEYS:
    rows = con.execute("select track_id, count(*) from events where kind='8k_catalyst' and company_key=? "
                       "group by track_id order by count(*) desc limit 8", (key,)).fetchall()
    print(f"  {key:14s} {rows}")

print("\n== trial date fields: how many have a usable start date in payload? ==")
total = sampled = with_start = 0
for (payload,) in con.execute("select payload from events where kind='trial' limit 4000"):
    total += 1
    data = json.loads(payload) if payload else {}
    if data.get("start_date") or data.get("study_first_posted"):
        with_start += 1
print(f"  sampled={total} with start_date or study_first_posted={with_start}")

print("\n== timestamp_quality distribution by kind ==")
for kind in KINDS:
    rows = con.execute("select timestamp_quality, count(*) from events where kind=? group by 1", (kind,)).fetchall()
    print(f"  {kind:14s} {rows}")
con.close()
