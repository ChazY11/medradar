
from lxml import html as LH
p = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\webmaster-faq.html"
doc = LH.parse(p)
for a in doc.iter("a"):
    h = a.get("href") or ""
    t = " ".join(a.text_content().split())
    if "rss" in (h+t).lower() or "atom" in (h+t).lower():
        print(repr(t)[:80], "->", h)
