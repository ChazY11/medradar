
import json, random, sqlite3, hashlib, textwrap
random.seed(20261118)
DB="file:D:/DEPPSKK/data004-baseline/perf-v2.db?mode=ro"
con=sqlite3.connect(DB,uri=True); con.row_factory=sqlite3.Row
facets={}
for r in con.execute("select observation_id, kind, value from observation_facet"):
    facets.setdefault(r["observation_id"],{}).setdefault(r["kind"],[]).append(r["value"])
def row_dict(r):
    p=json.loads(r["payload"] or "{}")
    f=facets.get(r["observation_id"],{})
    return {"observation_id":r["observation_id"],"source":r["source"],"record_type":r["record_type"],
            "title":r["title"],"published_at":r["published_at"],"event_at":r["event_at"],
            "published_at_precision":r["published_at_precision"],"event_at_precision":r["event_at_precision"],
            "first_observed_at":r["first_observed_at"],"payload":p,
            "mapped_topics":f.get("topic",[]),"mapped_products":f.get("product",[]),
            "engine_decision":r["decision"],"engine_tier":r["tier"],"engine_category":r["category"],
            "engine_dims":json.loads(r["dimensions"] or "{}")}
base = """select o.observation_id,o.source,o.record_type,o.title,o.published_at,o.event_at,
   o.published_at_precision,o.event_at_precision,o.first_observed_at,v.payload,c.decision,c.tier,c.category,c.dimensions
   from observation o join observation_version v on v.version_id=o.latest_version_id
   join admission_current c using(observation_id) """
feed=[row_dict(r) for r in con.execute(base+" where c.decision='FEED' and substr(coalesce(o.published_at,o.event_at),1,10)>='2026-10-19' order by coalesce(o.published_at,o.event_at) desc")]
A_ids={x["observation_id"] for x in feed}
others=[row_dict(r) for r in con.execute(base+" where c.decision!='FEED'") ]
allrows=[row_dict(r) for r in con.execute(base)]
byid={x["observation_id"]:x for x in allrows}
def take(pool,n,exclude):
    p=[x for x in pool if x["observation_id"] not in exclude]
    random.shuffle(p)
    return p[:n]
B=take([x for x in others if x["source"]=="crossref"],42,A_ids)
C=take([x for x in others if x["source"]=="pubmed"],32,A_ids|{x["observation_id"] for x in B})
D=take([x for x in allrows if x["source"]=="openfda_device"],20,A_ids|{x["observation_id"] for x in B+C})
E=[byid[x["observation_id"]] for x in others if x["source"] in ("draeger_official","philips_official")]
E=take(E,5,A_ids|{x["observation_id"] for x in B+C+D})
sample=feed+[{**x,"stratum":"feed"} for x in []]+B+C+D+E
for x in feed: x["stratum"]="A_feed_30d"
for x in B: x["stratum"]="B_crossref_noneed"
for x in C: x["stratum"]="C_pubmed_noneed"
for x in D: x["stratum"]="D_openfda_random"
for x in E: x["stratum"]="E_official_vendor"
print("sizes:", len(feed), len(B), len(C), len(D), len(E), "total", len(sample))
# dedupe
seen=set(); final=[]
for x in sample:
    if x["observation_id"] in seen: continue
    seen.add(x["observation_id"]); final.append(x)
print("deduped:", len(final))
for x in final:
    ab=(x["payload"].get("abstract") or "")[:600]
    x["abstract"]=ab
json.dump(final, open(r"D:\DEPPSKK\_fp001\sample120.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("by source:", {s:sum(1 for x in final if x["source"]==s) for s in {x["source"] for x in final}})
print("by engine decision:", {d:sum(1 for x in final if x["engine_decision"]==d) for d in {x["engine_decision"] for x in final}})
