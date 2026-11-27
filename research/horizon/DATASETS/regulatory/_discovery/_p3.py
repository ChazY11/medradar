import re
def text(p):
    h = open(p, encoding="utf-8", errors="replace").read()
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S|re.I)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S|re.I)
    t = re.sub(r"<[^>]+>", "\n", h)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t

t = text("agudid_v3_lookup_doc.html")
i = t.lower().find("lookup")
print(t[max(0,i-200):i+6000])
