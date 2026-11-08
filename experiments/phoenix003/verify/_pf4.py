p='verify_final.py'; s=open(p,encoding='utf-8').read()
s=s.replace("token={top['matched_token']} {top['source']}:{top['evidence_id']}", "token={top['matched_token']} {top['evidence_source']}:{top['evidence_id']}")
old='''    out["novelty"] = {"reclassified": dict(reclassified), "status_mismatches": status_mismatch,'''
new='''    # over-breadth: rows reclassified by a marker whose token had NO earlier regulatory record
    # (i.e. the old rule would have called them PRE_REGULATORY). For "continued access" this is
    # the dangerous case: FDA continued-access programmes can run BEFORE approval.
    breadth = collections.Counter()
    breadth_ex = collections.defaultdict(list)
    for r in com_v:
        rec = rec_by.get((r["evidence_source"], r["evidence_id"]))
        text = ((rec.get("text") if rec else "") or "").lower()
        marker = next((m for m in markers if m in text), None)
        if not marker:
            continue
        d = vc.parse_date(r["evidence_date"])
        fg = first_global.get(r["matched_token"])
        if fg is None or (d is not None and fg > d):
            breadth[marker] += 1
            if len(breadth_ex[marker]) < 6:
                breadth_ex[marker].append((r["firm"], r["milestone_key"], r["matched_token"],
                                           r["evidence_date"], short(r.get("evidence_title"), 80)))
    print("over-breadth: reclassified rows with NO earlier token record (would have been PRE_REG):")
    for m, c in sorted(breadth.items()):
        print(f"  [{m}] {c} rows")
        for x in breadth_ex[m]:
            print("      ", x)
    out["over_breadth"] = {"counts": dict(breadth), "examples": {m: list(v) for m, v in breadth_ex.items()}}
    out["novelty"] = {"reclassified": dict(reclassified), "status_mismatches": status_mismatch,
                      "over_breadth": {"counts": dict(breadth)},
                      "over_breadth_examples": {m: list(v) for m, v in breadth_ex.items()},'''
assert old in s
s=s.replace(old,new,1)
open(p,'w',encoding='utf-8').write(s); print('ok')
