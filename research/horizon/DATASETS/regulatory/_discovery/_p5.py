import re
h = open("hc_mdall_root.html", encoding="utf-8", errors="replace").read()
print("=== hrefs ===")
for m in re.findall(r'href=["\']([^"\']+)["\']', h):
    if m.startswith("#") or "canada.ca/etc" in m: continue
    print(" ", m)
