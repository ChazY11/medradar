
from lxml import html as LH
import sys, json
p = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\filer-manual-index-old.html"
doc = LH.parse(p)
links = []
for a in doc.iter("a"):
    h = a.get("href") or ""
    t = " ".join(a.text_content().split())
    if ".pdf" in h.lower() or "filermanual" in h.lower():
        links.append((t[:90], h))
for t,h in links[:120]:
    print(t, "->", h)
print("TOTAL", len(links))
