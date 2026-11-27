import re, json
print("=== ANVISA PRODUTOS dir ===")
h = open("anvisa_produtos_index.html", encoding="utf-8", errors="replace").read()
for m in re.findall(r'href=["\']([^"\']+)["\']', h):
    if m.startswith("?") or "_h5ai" in m or ".."in m: continue
    print("  ", m)
print()
print("=== MDALL device JSON structure ===")
d = json.load(open("hc_devices_infusion.json", encoding="utf-8"))
print("type:", type(d).__name__, "len:", len(d) if isinstance(d,list) else "n/a")
print(json.dumps(d[0] if isinstance(d,list) else d, indent=2, ensure_ascii=False)[:1500])
print("... keys union:", sorted({k for r in (d if isinstance(d,list) else [d]) for k in r}))
