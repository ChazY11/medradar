import re
h = open("hc_mdall_api_doc.html", encoding="utf-8", errors="replace").read()
h = re.sub(r"<script.*?</script>", " ", h, flags=re.S|re.I)
t = re.sub(r"<[^>]+>", "\n", h)
t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t)
i = t.find("Device Identifier")
j = t.find("Licence Type", i)
print(t[i:i+4000])
