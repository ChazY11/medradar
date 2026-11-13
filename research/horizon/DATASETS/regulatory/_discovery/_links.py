import re, sys, os
def links(path, filt=None, limit=200):
    h = open(path, encoding="utf-8", errors="replace").read()
    out = []
    for m in re.findall(r'href=["\']([^"\']+)["\']', h):
        if filt and not any(f in m.lower() for f in filt): continue
        if m not in out: out.append(m)
    return out[:limit]
print("=== agudid doc links ===")
for l in links("agudid_parse_api_doc.html", ["api","resource","developer"]): print(l)
print("=== anvisa dirs ===")
for l in links("anvisa_dados.txt")[:60]: print(l)
print("=== pmda links (data-ish) ===")
for l in links("pmda_home.txt", ["data","review","search","db"])[:30] if os.path.exists("pmda_home.txt") else []: print(l)
