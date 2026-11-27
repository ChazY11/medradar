import re, os, json
def read(p):
    return open(p, encoding="utf-8", errors="replace").read()

print("=== hc_api_root ===")
print(read("hc_api_root.html"))

print("=== datagov_devices titles ===")
d = json.loads(read("datagov_devices.json"))
for r in d.get("result", {}).get("results", []):
    print("-", r.get("title"), "|", r.get("name"))
    for res in r.get("resources", [])[:6]:
        print("    ", res.get("format"), res.get("url"))

print("=== datagov_artg2 titles ===")
d = json.loads(read("datagov_artg2.json"))
for r in d.get("result", {}).get("results", []):
    print("-", r.get("title"), "|", r.get("name"))
    for res in r.get("resources", [])[:8]:
        print("    ", res.get("format"), res.get("url"))
