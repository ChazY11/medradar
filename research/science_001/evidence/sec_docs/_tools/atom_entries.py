
import re
p = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\atom-cik-0000064670-8K.xml"
s = open(p, encoding="utf-8", errors="replace").read()
entries = re.findall(r"<entry>.*?</entry>", s, re.S)
print("entries:", len(entries))
rows = []
for e in entries:
    acc = re.search(r"<accession-number>([^<]+)</accession-number>", e)
    upd = re.search(r"<updated>([^<]+)</updated>", e)
    fd = re.search(r"<filing-date>([^<]+)</filing-date>", e)
    rows.append((upd.group(1) if upd else "", acc.group(1) if acc else "", fd.group(1) if fd else ""))
for u,a,f in rows:
    print(u, "|", a, "| filed:", f)
