import re
def text(p):
    h = open(p, encoding="utf-8", errors="replace").read()
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S|re.I)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S|re.I)
    t = re.sub(r"<[^>]+>", "\n", h)
    t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t)
    return t
t = text("agudid_v3_implant_download_doc.html")
i = t.find("Download Files")
print("=== IMPLANT DOWNLOAD DOC ===")
print(t[i:i+2500] if i>0 else t[:3000])
print()
print("=== MDALL ROOT VISIBLE TEXT ===")
print(text("hc_mdall_root.html")[-2500:])
