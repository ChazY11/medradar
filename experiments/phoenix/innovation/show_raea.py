import json
from pathlib import Path

P = Path(__file__).resolve().parent / "results" / "raea_results.json"
d = json.loads(P.read_text(encoding="utf-8"))
print("=== coverage change (share of all events in that kind) ===")
print(f"{'kind':16s} {'events':>8s} {'before':>8s} {'after':>8s} {'before%':>8s} {'after%':>7s} {'gain_pp':>8s}")
for k, v in d["coverage_change"].items():
    print(f"{k:16s} {v['events']:8d} {v['mapped_before']:8d} {v['mapped_after']:8d} "
          f"{v['share_before']*100:7.2f}% {v['share_after']*100:6.2f}% {v['absolute_gain_pp']:+8.2f}")
print()
print("total gained:", d["application_to_unmapped"]["total_gained"])
print()
print("=== gained by rule x kind ===")
for r in d["application_to_unmapped"]["gained_by_rule_and_kind"]:
    print(f"  {r['rule']:12s} {r['kind']:16s} {r['n']:6d}")
print()
print("=== sample attributions (for manual precision review) ===")
for rule, ex in d["application_to_unmapped"]["examples"].items():
    print(f"-- {rule}")
    for e in ex[:10]:
        print(f"   {e['kind']:15s} {str(e['applicant_raw'])[:52]:54s} -> {e['company_key']}")
