import re
h = open("anvisa_consultas_index.html", encoding="utf-8", errors="replace").read()
print("=== CONSULTAS links ===")
for m in re.findall(r'href=["\']([^"\']+)["\']', h):
    if m.startswith("?"): continue
    print(" ", m)
