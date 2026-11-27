import re
h = open("hc_mdall_api_doc.html", encoding="utf-8", errors="replace").read()
h = re.sub(r"<script.*?</script>", " ", h, flags=re.S|re.I)
h = re.sub(r"<style.*?</style>", " ", h, flags=re.S|re.I)
t = re.sub(r"<[^>]+>", "\n", h)
t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t)
print("total len", len(t))
# find all parameter table rows mentioning api/medical-devices
for m in re.finditer(r"api/medical-devices/[a-z\-/_?=&0-9%A-Za-z ]+", t):
    print("URI:", m.group(0)[:120])
