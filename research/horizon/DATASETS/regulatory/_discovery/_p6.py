import re
def text(p):
    h = open(p, encoding="utf-8", errors="replace").read()
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S|re.I)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S|re.I)
    t = re.sub(r"<[^>]+>", "\n", h)
    t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t)
    return t
t = text("hc_mdall_api_doc.html")
print("=== MDALL API DOC (first 6000 chars) ===")
print(t[:6000])
