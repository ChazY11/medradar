
import re, collections
p = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\atom-cik-0000064670-8K.xml"
s = open(p, encoding="utf-8", errors="replace").read()
ups = re.findall(r"<updated>([^<]+)</updated>", s)
print("count updated:", len(ups))
offs = collections.Counter(u[-6:] for u in ups)
print("offset histogram:", dict(offs))
for u in sorted(ups):
    print(u)
print("--- filing-date count:", len(re.findall(r"<filing-date>", s)))
print("--- published elems:", len(re.findall(r"<published>", s)))
