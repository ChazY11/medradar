
"""Isolated synthetic verification of the continuous-discovery mechanisms.

Not real intelligence: this proves the machinery (new record, updated record, dedup,
watermark advance, failure does not advance), never that a real new event was discovered.
"""
import sys, tempfile, os, json
sys.path.insert(0, r"D:\DEPPSKK\worktrees\rf004")
from medradar.radar.adapter import CollectContext, run_source
from medradar.radar.ledger import ObservationLedger
from medradar.radar.records import MappingResult, Page, RawRecord, Scope

class Fetcher:
    stats={"requests":0,"bytes":0,"retries":0,"refusals":0,"rate_limited":0,"not_found":0,"failures":0}
    @property
    def requests_remaining(self): return 100

class Stub:
    source_id="stub"; label="Stub"; adapter_version="stub-1"; declared_cadence_hours=1.0
    record_types=("publication",); enabled=True; access_state="ENABLED"; access_reason=None
    def __init__(self, records, watermark, fail=False):
        self.records=records; self.watermark=watermark; self.fail=fail
    def plan(self, ctx): return [Scope("s1")]
    def fetch_page(self, ctx, scope, cursor):
        if self.fail: raise RuntimeError("source unavailable")
        return Page(records=list(self.records), next_cursor=None, watermark=self.watermark)
    def map_record(self, record, ctx): return MappingResult()

def rec(rid, title, doi=None, published="2026-11-01"):
    payload={"title":title,"abstract":"ECG monitoring algorithm validation in intensive care"}
    if doi: payload["doi"]=doi
    return RawRecord(source="stub", source_record_id=rid, official_identifier=(f"DOI:{doi}" if doi else f"ID:{rid}"),
        record_type="publication", title=title, url=f"https://example.test/{rid}",
        published_at=published, published_at_precision="date", payload=payload, text=title)

def run(adapter, ledger):
    ctx=CollectContext(fetcher=Fetcher(), ledger=ledger, adapter_version=adapter.adapter_version, log=lambda m: None)
    return run_source(adapter, ctx)

tmp=tempfile.mkdtemp(prefix="fp001-")
db=os.path.join(tmp,"radar.db")
L=ObservationLedger(db)
print("cycle 1 (2 new records, watermark 2026-11-02)")
r1=run(Stub([rec("a","ECG algorithm A"), rec("b","ECG algorithm B", doi="10.1/x")], "2026-11-02"), L)
print("   outcome:", r1["outcome"], "| new:", r1["counters"].get("records_new"), "| wm:", r1["watermark_after"])
print("cycle 2 (same A, B updated with a new version, C new)")
same=[rec("a","ECG algorithm A"), rec("b","ECG algorithm B revised", doi="10.1/x"), rec("c","ECG algorithm C")]
r2=run(Stub(same,"2026-11-03"), L)
print("   outcome:", r2["outcome"], "| new:", r2["counters"].get("records_new"), "| updated:", r2["counters"].get("records_updated"), "| wm:", r2["watermark_after"])
print("cycle 3 (source fails)")
r3=run(Stub([],"2026-11-04", fail=True), L)
print("   outcome:", r3["outcome"], "| wm after:", r3["watermark_after"], "| failures recorded:", L.ensure_source("stub", label="Stub", adapter_version="stub-1", cadence_hours=1.0)["consecutive_failures"])
con=L.con
print("observations:", con.execute("select count(*) from observation").fetchone()[0])
print("versions:", con.execute("select observation_id, count(*) n from observation_version group by 1").fetchall())
print("change states:", con.execute("select change_state, count(*) from observation_change group by 1").fetchall())
print("discovery phases:", con.execute("select discovery_phase, count(*) from observation group by 1").fetchall())
print("work_key / identifiers:", con.execute("select observation_id, official_identifier from observation").fetchall())
print("duplicate DOI test: two different source rows pointing at the same DOI")
rL=ObservationLedger(os.path.join(tmp,"d2.db"))
run(Stub([rec("x","Paper one", doi="10.9/same")], "2026-11-02"), rL)
run(Stub([rec("y","Paper one (preprint)", doi="10.9/same")], "2026-11-03"), rL)
print("   observations:", rL.con.execute("select count(*) from observation").fetchone()[0],
      "| identifiers:", rL.con.execute("select official_identifier from observation").fetchall())
L.close(); rL.close()
print("done; tmp =", tmp)
