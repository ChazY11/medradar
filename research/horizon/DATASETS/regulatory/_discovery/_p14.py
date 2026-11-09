import re
h = open("hc_mdall_api_doc.html", encoding="utf-8", errors="replace").read()
h = re.sub(r"<script.*?</script>", " ", h, flags=re.S|re.I)
t = re.sub(r"<[^>]+>", "\n", h)
t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t)
idx = [m.start() for m in re.finditer(r"Device Identifier", t)]
print("occurrences:", idx)
i = idx[-1]
print(t[i:i+3500])
