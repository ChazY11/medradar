"""Print the pre-registered decision record and stability tables."""
import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "artifacts" / "statistical_validation.json"
data = json.loads(path.read_text(encoding="utf-8"))


def r(value, digits=5):
    return round(value, digits) if isinstance(value, float) else value


for label, horizon in data["horizons"].items():
    print("=" * 74)
    print(label)
    print("decision:", json.dumps(horizon["decision"], ensure_ascii=False, indent=1))
    print("h2:", json.dumps(horizon["h2"], ensure_ascii=False, indent=1))
    print("G1 vs B2 per-window:")
    for row in horizon["paired"]["G1_graph"]["per_window"]:
        print(f"  {row['window']} rows={row['rows']} pos={row['positives']} "
              f"AP={r(row['ap'])} ref={r(row['ap_reference'])} dAP={r(row['delta'])} "
              f"CI=[{r(row['ci_low'])},{r(row['ci_high'])}] excl0={row['excludes_zero']} "
              f"MDE={r(row['mde_80'])}")
    for unit in ("company", "pair"):
        pooled = horizon["paired"]["G1_graph"]["pooled"][unit]
        keys = ("delta", "ci_low", "ci_high", "mde_80", "p_one_sided", "excludes_zero",
                "clusters", "rows", "positives")
        print(f"G1 pooled {unit}:", {k: r(pooled.get(k)) for k in keys})
    print("stability by_origin:", {k: {"n": v["n"], "pos": v["positives"],
                                       "delta": r(v["delta"], 4)}
                                   for k, v in horizon["stability"]["by_origin"].items()})
    print("stability note:", horizon["stability"].get("note", "")[:160])
    tracks = [(k, v) for k, v in horizon["stability"]["by_track"].items() if v["delta"] is not None]
    print(f"tracks with data: {len(tracks)}")
    for k, v in sorted(tracks, key=lambda kv: -kv[1]["delta"])[:4]:
        print(f"  best  {k:22s} n={v['n']:4d} pos={v['positives']:3d} dAP={r(v['delta'],4)}")
    for k, v in sorted(tracks, key=lambda kv: kv[1]["delta"])[:4]:
        print(f"  worst {k:22s} n={v['n']:4d} pos={v['positives']:3d} dAP={r(v['delta'],4)}")
    companies = [(k, v) for k, v in horizon["stability"]["by_company"].items() if v["delta"] is not None]
    print(f"companies with data: {len(companies)}")
    for k, v in sorted(companies, key=lambda kv: -kv[1]["delta"])[:3]:
        print(f"  best  {k:26s} n={v['n']:4d} pos={v['positives']:3d} dAP={r(v['delta'],4)}")
    for k, v in sorted(companies, key=lambda kv: kv[1]["delta"])[:3]:
        print(f"  worst {k:26s} n={v['n']:4d} pos={v['positives']:3d} dAP={r(v['delta'],4)}")

print("\n" + "=" * 74)
print("multiplicity:", json.dumps(data.get("multiplicity"), ensure_ascii=False, indent=1))
