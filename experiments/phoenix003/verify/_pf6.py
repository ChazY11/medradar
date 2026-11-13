p='verify_final.py'; s=open(p,encoding='utf-8').read()
old='''    print("all checks pass:", all(checks.values()))'''
new='''    print("all checks pass:", all(checks.values()))
    top_leads = sorted(strict_rows, key=lambda r: -r["lead_days"])
    seen_anchor = set()
    print("top strict cases (independent, distinct anchors):")
    for r in top_leads:
        if r["anchor_id"] in seen_anchor:
            continue
        seen_anchor.add(r["anchor_id"])
        print(f"   lead={r['lead_days']:5d} {r['firm']:22s} {r['milestone_key']:10s} "
              f"{r['matched_token']:16s} {r['evidence_source']}:{r['evidence_id']} {r['evidence_date']}"
              f" | {short(r['evidence_title'], 70)}")
        if len(seen_anchor) >= 8:
            break
    # SYMPLICITY anchor status in the strict set
    sym_anchor_rows = [r for r in strict_rows if r["firm"] == "medtronic" and r["milestone_key"] == "PP220026"]
    print(f"SYMPLICITY anchor rows in strict set: {len(sym_anchor_rows)}; max lead="
          f"{max((r['lead_days'] for r in sym_anchor_rows), default=None)}")'''
assert old in s; s=s.replace(old,new,1)
open(p,'w',encoding='utf-8').write(s); print('ok')
