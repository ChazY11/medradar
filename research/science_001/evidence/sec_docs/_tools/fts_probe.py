
import json
p = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs\raw\fts-api.json"
d = json.load(open(p, encoding="utf-8"))
print("top keys:", list(d.keys()))
hits = d.get("hits", {})
print("hits keys:", list(hits.keys()))
tot = hits.get("total")
print("total:", tot)
hl = hits.get("hits", [])
print("n hits:", len(hl))
if hl:
    h = hl[0]
    print("hit keys:", list(h.keys()))
    src = h.get("_source", {})
    print("source keys:", list(src.keys()))
    print(json.dumps({k: src.get(k) for k in ("file_date","form_type","display_names","file_num","biz_states","sics","period_ending","items") if k in src}, indent=2)[:800])
    print("sort:", h.get("sort"))
