
import sys, sqlite3
sys.path.insert(0, r"D:\DEPPSKK\worktrees\rf004")
from medradar.radar.adapter import clamp_future_watermark
from medradar.radar.adapters.crossref import CrossrefAdapter, QUERIES
from medradar.radar.taxonomy import load_taxonomy
from datetime import date

con = sqlite3.connect("file:D:/DEPPSKK/data004-baseline/perf-v2.db?mode=ro", uri=True)
con.row_factory = sqlite3.Row
wm = con.execute("select watermark from source_state where source_id='crossref'").fetchone()["watermark"]
print("stored crossref watermark :", wm)
adapter = CrossrefAdapter(load_taxonomy(__import__("pathlib").Path(r"D:\DEPPSKK\worktrees\rf004\config\radar")))

class Ctx:
    watermark = None
ctx = Ctx()
ctx.watermark = wm
# what the deployed engine asks for, before the fix
adapter_scope = CrossrefAdapter._since.__get__(adapter)
print("BEFORE fix  from-created-date:", adapter_scope(ctx))
usable, clamped_from = clamp_future_watermark(wm)
ctx.watermark = usable
print("AFTER  fix  from-created-date:", adapter_scope(ctx), "| clamped_from =", clamped_from)
print("meaning: a query window that starts in the future returns nothing; the clamped one starts today-ish")
