import json
d=json.load(open("experiments/regulatory/EXP_H2_SUMMARY.json",encoding="utf-8"))
print("\nfinding keys:", list(d["finding"]))
print("verdicts:", d["verdicts"])
print("primary verdicts:", d["primary"]["verdicts"])
print("HN rules:", d["primary"]["hard_negative_rules_attempted"])
rows=[json.loads(l) for l in open("experiments/regulatory/EXP_H2_PAIRS.jsonl",encoding="utf-8")]
print("pairs in file:", len(rows))
print("sample pair:", json.dumps(rows[0], ensure_ascii=False)[:500])
print("sample HN:", json.dumps([r for r in rows if r["construction_rule"]][0], ensure_ascii=False)[:600])
