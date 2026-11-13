
import json, re
from datetime import datetime, timezone
jp = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\submissions-json-CIK0000064670.json"
ap = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\atom-cik-0000064670-8K.xml"
d = json.load(open(jp, encoding="utf-8"))
rec = d["filings"]["recent"]
jsonmap = dict(zip(rec["accessionNumber"], rec["acceptanceDateTime"]))
s = open(ap, encoding="utf-8", errors="replace").read()
entries = re.findall(r"<entry>.*?</entry>", s, re.S)
ok = bad = miss = 0
for e in entries:
    a = re.search(r"<accession-number>([^<]+)</accession-number>", e).group(1)
    u = re.search(r"<updated>([^<]+)</updated>", e).group(1)
    if a not in jsonmap:
        miss += 1
        continue
    atom_utc = datetime.fromisoformat(u).astimezone(timezone.utc)
    j = jsonmap[a].replace("Z", "+00:00")
    j_utc = datetime.fromisoformat(j)
    same = atom_utc == j_utc
    if same:
        ok += 1
    else:
        bad += 1
        print("MISMATCH", a, "atom:", u, "->", atom_utc.isoformat(), "json:", jsonmap[a])
print("matched-equal:", ok, "mismatched:", bad, "not-in-json:", miss)
