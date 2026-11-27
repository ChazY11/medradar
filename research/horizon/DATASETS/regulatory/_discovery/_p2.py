import re, json
def read(p): return open(p, encoding="utf-8", errors="replace").read()

print("=== anvisa index: links ===")
h = read("anvisa_dados_index.html")
for m in re.findall(r'href=["\']([^"\']+)["\']', h):
    print(" ", m)

print()
print("=== eudamed api-details page text (trimmed) ===")
h2 = read("eudamed_api_portal.html")
txt = re.sub(r"<script.*?</script>", " ", h2, flags=re.S|re.I)
txt = re.sub(r"<style.*?</style>", " ", txt, flags=re.S|re.I)
txt = re.sub(r"<[^>]+>", " ", txt)
txt = re.sub(r"\s+", " ", txt)
print(txt[:1800])

print()
print("=== mdall root: script/api hints ===")
h3 = read("hc_mdall_root.html")
for pat in [r'src=["\']([^"\']+)', r'api[^"\'\s]{0,80}', r'action=["\']([^"\']+)']:
    print("--", pat)
    for m in re.findall(pat, h3, flags=re.I)[:25]:
        print("   ", m)
