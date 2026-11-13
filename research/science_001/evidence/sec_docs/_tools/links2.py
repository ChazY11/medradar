
from lxml import html as LH
p = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\accessing-edgar-data.html"
doc = LH.parse(p)
for a in doc.iter("a"):
    h = a.get("href") or ""
    t = " ".join(a.text_content().split())
    if any(k in (t+h).lower() for k in ("pds","dissemin","filer manual","edmanuals","specification")):
        print(repr(t)[:110], "->", h)
