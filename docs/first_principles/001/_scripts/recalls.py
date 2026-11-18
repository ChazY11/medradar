
import json, urllib.parse, urllib.request, time
UA={"User-Agent":"MedRadar-FP001/1.0"}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=45) as r:
        return json.loads(r.read().decode("utf-8","replace"))
codes=["MHX","MWI","MSX","DPS","DSI","DQA","DXN","DRS","BZQ","CAP","DRT","DRG","CCK"]
hits=[]
for c in codes:
    u="https://api.fda.gov/device/recall.json?search=product_code:%22"+c+"%22&limit=100&sort=event_date_initiated:desc"
    try:
        d=get(u)
    except Exception as e:
        print(c,"ERR",e if isinstance(e,str) else type(e).__name__); time.sleep(0.4); continue
    res=d.get("results",[])
    print(f"{c}: {len(res)} (latest {res[0]['event_date_initiated'] if res else '-'})")
    for r in res:
        hits.append({"code":c,"date":r.get("event_date_initiated"),"product":r.get("product_description","")[:140],
                     "firm":r.get("recalling_firm",""),"reason":r.get("reason_for_recall","")[:200],"id":r.get("res_event_number"),"k":r.get("k_numbers")})
    time.sleep(0.4)
json.dump(hits, open(r"D:\DEPPSKK\_fp001\recalls.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("total",len(hits))
for h in sorted(hits,key=lambda x:x["date"] or "",reverse=True)[:20]:
    print(" ", h["date"], h["code"], "|", h["firm"][:26], "|", h["product"][:60], "|", h["reason"][:60])
