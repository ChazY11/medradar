
import json
p = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\submissions-json-CIK0000064670.json"
d = json.load(open(p, encoding="utf-8"))
print("top-level keys:", list(d.keys())[:20])
rec = d["filings"]["recent"]
print("recent keys:", list(rec.keys()))
i = rec["accessionNumber"].index("0000064670-15-000002")
for k in ("accessionNumber","filingDate","reportDate","acceptanceDateTime","act","form","fileNumber","items"):
    print(k, "=", rec.get(k, ["<missing>"])[i] if isinstance(rec.get(k), list) else rec.get(k))
# count format variants of acceptanceDateTime
import re
vals = rec.get("acceptanceDateTime", [])
print("n rows:", len(vals))
print("suffix set:", sorted(set(v[-1:] for v in vals)))
print("sample:", vals[:5])
print("any +offset:", any("+" in v for v in vals))
