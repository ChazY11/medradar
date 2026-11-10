"""Scratch: inspect the successful import state (read-only)."""
import sqlite3

P = r"D:\DEPPSKK\worktrees\convergence-001\research\convergence\staging\convergence.sqlite"


def main():
    con = sqlite3.connect("file:" + P.replace("\\", "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    print("runs:", [dict(r) for r in con.execute(
        "SELECT run_id,status,records_seen,converted,degraded,rejected,evidence_inserted,evidence_noop "
        "FROM conv_runs")])
    print("evidence", con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
          "head", con.execute("SELECT COUNT(*) FROM evidence_head").fetchone()[0],
          "versions>1", con.execute("SELECT COUNT(*) FROM evidence WHERE version>1").fetchone()[0])
    print("relations:", dict(con.execute(
        "SELECT relation_type,COUNT(*) FROM entity_relations GROUP BY 1").fetchall()))
    print("--- evidence row ---")
    r = con.execute("SELECT * FROM evidence WHERE source_id='accessgudid' LIMIT 1").fetchone()
    for k in r.keys():
        print("  %-22s %s" % (k, str(r[k])[:240]))
    print("--- conversions row ---")
    c = con.execute("SELECT * FROM conv_conversions WHERE source_id='accessgudid' LIMIT 1").fetchone()
    for k in c.keys():
        print("  %-24s %s" % (k, str(c[k])[:300]))
    print("--- distributions ---")
    for sql in ("SELECT status,COUNT(*) FROM conv_conversions GROUP BY 1",
                "SELECT identity_status,COUNT(*) FROM evidence GROUP BY 1",
                "SELECT relation_status,COUNT(*) FROM evidence GROUP BY 1",
                "SELECT time_quality,COUNT(*) FROM evidence GROUP BY 1",
                "SELECT licence_status,COUNT(*) FROM evidence GROUP BY 1",
                "SELECT quality_flags,COUNT(*) FROM evidence GROUP BY 1"):
        print(sql, "->", con.execute(sql).fetchall())
    print("--- evidence_identifiers schemes ---")
    print(con.execute("SELECT scheme,COUNT(*) FROM evidence_identifiers GROUP BY 1 ORDER BY 2 DESC").fetchall())


if __name__ == "__main__":
    main()
