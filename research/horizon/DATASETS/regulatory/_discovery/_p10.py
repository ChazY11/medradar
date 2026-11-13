import json
d = json.load(open("round1.json", encoding="utf-8"))
for t in d["targets"]:
    if "fda" in t["name"] or "agudid" in t["name"]:
        print(t["name"], "|", t.get("status"), "|", t.get("content_type"))
        print("   rl:", t.get("rate_limit_headers"))
print()
print("--- fda_510k saved body head ---")
import os
p = "fda_510k.txt"
print(open(p, encoding="utf-8", errors="replace").read()[:1200])
