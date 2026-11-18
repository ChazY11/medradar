
import json, time, urllib.parse, urllib.request, sqlite3, re

UA={"User-Agent":"MedRadar-FP001/1.0"}
def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=UA), timeout=45) as r:
                return r.read().decode("utf-8","replace")
        except Exception:
            if i==tries-1: raise
            time.sleep(2*(i+1))

probe=json.load(open(r"D:\DEPPSKK\_fp001\pubmed_probe.json",encoding="utf-8"))
con=sqlite3.connect("file:D:/DEPPSKK/data004-baseline/perf-v2.db?mode=ro",uri=True)
ledger_pmids={}
for oid, ident, title, pub, src in con.execute(
    "select observation_id, official_identifier, title, coalesce(published_at,event_at), source from observation where source='pubmed'"):
    if ident and ident.startswith("PMID:"):
        ledger_pmids[ident.split(":")[1]]=(oid,title,pub)
print("ledger pubmed records:", len(ledger_pmids))

def esummary(ids):
    q=urllib.parse.urlencode({"db":"pubmed","id":",".join(ids),"retmode":"json"})
    d=json.loads(get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"+q))
    res=d.get("result",{})
    out=[]
    for uid in res.get("uids",[]):
        it=res.get(uid,{})
        out.append({"pmid":uid,"title":it.get("title",""),"pubdate":it.get("pubdate",""),
                    "journal":it.get("fulljournalname") or it.get("source",""),"sortpubdate":it.get("sortpubdate","")})
    return out

report={}
all_missed=[]
for k,v in probe.items():
    ids=v["ids"]
    if not ids: 
        report[k]={"total":v["count"],"sampled":0,"in_ledger":0}; continue
    meta=[]
    for i in range(0,len(ids),100):
        meta+=esummary(ids[i:i+100]); time.sleep(0.4)
    hit=[m for m in meta if m["pmid"] in ledger_pmids]
    miss=[m for m in meta if m["pmid"] not in ledger_pmids]
    report[k]={"total":v["count"],"sampled":len(meta),"in_ledger":len(hit),"missed":len(miss)}
    print(f'{k}: total={v["count"]} sampled={len(meta)} in_ledger={len(hit)} missed={len(miss)}')
    for m in miss: all_missed.append({**m,"query":k})
    json.dump(meta, open(rf"D:\DEPPSKK\_fp001\pm_{k}.json","w",encoding="utf-8"), ensure_ascii=False)
json.dump(report, open(r"D:\DEPPSKK\_fp001\pm_recall.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(all_missed, open(r"D:\DEPPSKK\_fp001\pm_missed.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("missed total:", len(all_missed))
