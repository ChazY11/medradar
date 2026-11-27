import re
h = open("openfda_auth_docs.html", encoding="utf-8", errors="replace").read()
t = re.sub(r"<script.*?</script>", " ", h, flags=re.S|re.I)
t = re.sub(r"<style.*?</style>", " ", t, flags=re.S|re.I)
t = re.sub(r"<[^>]+>", " ", t)
t = re.sub(r"&nbsp;"," ",t); t = re.sub(r"&#x27;","'",t); t = re.sub(r"&quot;",'"',t)
t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n\s*\n+", "\n", t)
for kw in ["240", "1,000", "1000", "without an API key", "rate limit", "public domain", "license", "attribution"]:
    for m in re.finditer(kw, t, flags=re.I):
        s=max(0,m.start()-220); print(f"[{kw}] ...{t[s:m.start()+260]}...".replace("\n"," "))
        break
