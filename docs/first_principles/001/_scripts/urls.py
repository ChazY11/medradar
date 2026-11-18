
import sqlite3, json
con=sqlite3.connect("file:D:/DEPPSKK/data004-baseline/perf-v2.db?mode=ro",uri=True); con.row_factory=sqlite3.Row
items=json.load(open(r"D:\DEPPSKK\_fp001\labelled120.json",encoding="utf-8"))
ids=[x["observation_id"] for x in items]
q=",".join("?"*len(ids))
rows={r["observation_id"]:dict(r) for r in con.execute(f"select observation_id,source_url,official_identifier,source from observation where observation_id in ({q})", ids)}
missing=[i for i in ids if not (rows[i]["source_url"] or rows[i]["official_identifier"])]
print("checked",len(ids),"| without url/identifier:",len(missing))
print("sample urls:", [rows[i]["source_url"] for i in ids[:3]])
print("all obs with url:", con.execute("select count(*) from observation where source_url is not null and source_url<>''").fetchone()[0], "/", con.execute("select count(*) from observation").fetchone()[0])
