"""Create the SQLite fixture used by the REA validation battery.

Writes only inside experiments/phoenix/rea/fixtures/. Harmless data.
"""

import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "sample.sqlite")

if os.path.exists(DB):
    os.remove(DB)

con = sqlite3.connect(DB)
cur = con.cursor()
cur.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score REAL)")
cur.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, firm TEXT, status TEXT)")
cur.executemany(
    "INSERT INTO signals (name, score) VALUES (?, ?)",
    [("phoenix-001", 0.75), ("rea-probe", 0.5), ("canary", -0.25)],
)
cur.executemany(
    "INSERT INTO tracks (firm, status) VALUES (?, ?)",
    [("alpha", "open"), ("beta", "closed")],
)
con.commit()
con.close()

print("wrote", DB, os.path.getsize(DB), "bytes")
