"""S-028 audit 10: provenance / frozen-input verification.

Verifies the claimed size + sha256 of the frozen research input, inventories tables
and row counts across the three stores, and records file mtimes (evidence that the
research DB predates the product DB work).
"""
from __future__ import annotations

import os
import sqlite3

from audit_common import RESEARCH, PRODUCT, OBS, ro, sha256_of, now_iso, dump

CLAIMED_RESEARCH_SHA = "dd241bfec138d7977d7eb8f4c1db25119d59b6fe7ff573060b24d14eeeb71e0d"
CLAIMED_RESEARCH_SIZE = 289443840


def table_stats(path):
    c = ro(path)
    out = {}
    for (t,) in c.execute("select name from sqlite_master where type='table' order by name"):
        try:
            n = c.execute(f'select count(*) from "{t}"').fetchone()[0]
        except Exception as e:  # noqa: BLE001
            n = f"ERR {e}"
        out[t] = n
    c.close()
    return out


def main():
    dbs = {"research": RESEARCH, "product": PRODUCT, "observatory": OBS}
    prov = {"generated_at": now_iso(), "stores": {}}
    for name, path in dbs.items():
        st = os.stat(path)
        rec = {
            "path": path,
            "bytes": st.st_size,
            "mtime_local": __import__("datetime").datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds"),
            "tables": table_stats(path),
        }
        if name == "research":
            sha = sha256_of(path)
            rec["sha256"] = sha
            rec["claimed_sha256"] = CLAIMED_RESEARCH_SHA
            rec["claimed_bytes"] = CLAIMED_RESEARCH_SIZE
            rec["size_verified"] = st.st_size == CLAIMED_RESEARCH_SIZE
            rec["sha256_verified"] = sha == CLAIMED_RESEARCH_SHA
        rec["n_tables"] = len(rec["tables"])
        prov["stores"][name] = rec
        print(f"{name:12s} {st.st_size:>12,d} bytes  tables={len(rec['tables'])}")
        if name == "research":
            print(f"  sha256 match: {rec['sha256_verified']}   size match: {rec['size_verified']}")

    # regression guard: the frozen input must not contain any table that could
    # carry live/prospective state (it should be a pure historical snapshot).
    live_tables = [t for t in prov["stores"]["research"]["tables"]
                   if t in ("live_alerts", "live_equity", "live_pending", "live_skips", "signals",
                            "positions", "paper_trades", "paper_orders", "llm_verdicts")]
    prov["frozen_input_live_state_tables"] = {
        t: prov["stores"]["research"]["tables"][t] for t in live_tables}
    prov["n_live_state_tables_checked"] = len(prov["frozen_input_live_state_tables"])
    print("\nfrozen input live-state tables (all zero = no live state leaked in):")
    for t, n in prov["frozen_input_live_state_tables"].items():
        print(f"  {t}: {n}")

    dump("10_provenance", prov)


if __name__ == "__main__":
    main()
