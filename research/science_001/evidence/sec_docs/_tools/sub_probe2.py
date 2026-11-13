
import json
from datetime import datetime, timezone, timedelta
p = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\submissions-json-CIK0000064670.json"
d = json.load(open(p, encoding="utf-8"))
rec = d["filings"]["recent"]
accs = rec["accessionNumber"]; acc_dt = rec["acceptanceDateTime"]; fdate = rec["filingDate"]; forms = rec["form"]
targets = {"0000064670-15-000002","0000064670-14-000008","0000064670-13-000009",
           "0000064670-14-000014","0000064670-14-000002","0000064670-13-000021",
           "0000064670-14-000025","0000064670-13-000021"}
print("%-24s %-10s %-26s %s" % ("accession","filed","acceptanceDateTime(json)","form"))
for i,a in enumerate(accs):
    if a in targets:
        print("%-24s %-10s %-26s %s" % (a, fdate[i], acc_dt[i], forms[i]))
# For each, also compute what the value would be if the wall clock were Eastern
print()
print("Underlying header ACCEPTANCE-DATETIME digits we fetched:")
print(" 2015-02-17 07:18:53 (EST, -05) -> 2015-02-17T12:18:53Z")
print(" 2014-05-20 07:20:54 (EDT, -04) -> 2014-05-20T11:20:54Z")
print(" 2013-08-20 07:33:33 (EDT, -04) -> 2013-08-20T11:33:33Z")
