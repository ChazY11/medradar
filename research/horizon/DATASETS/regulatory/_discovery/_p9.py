import re, json
h = open("agudid_download_page.html", encoding="utf-8", errors="replace").read()
print("=== GUDID download links ===")
for m in sorted(set(re.findall(r'href=["\']([^"\']+)["\']', h))):
    if any(k in m.lower() for k in (".zip",".json",".csv","download","release")):
        print(" ", m)
print()
txt = re.sub(r"<[^>]+>", "\n", re.sub(r"<script.*?</script>"," ",h,flags=re.S|re.I))
txt = re.sub(r"\n\s*\n+","\n",txt)
i = txt.lower().find("download")
print("=== visible snippet ===")
print(txt[i:i+2000])
print()
d = json.loads(open("hc_ckan_mdall.json",encoding="utf-8").read())
r = d.get("result", {})
print("=== CKAN MDALL package ===")
print("title:", r.get("title"))
print("notes:", (r.get("notes") or "")[:600])
print("licence:", r.get("license_title"), r.get("license_url"))
for res in r.get("resources", []):
    print(" -", res.get("name"), "|", res.get("format"), "|", res.get("url"))
