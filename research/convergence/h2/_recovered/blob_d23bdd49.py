import json
d=json.load(open("experiments/regulatory/EXP_H2_SUMMARY.json",encoding="utf-8"))
print("per_signal:", json.dumps(d["per_signal_sufficiency"], indent=2))
print("signal table:", json.dumps(d["signal_sufficiency_table"], indent=2))
print("verdicts:", d["verdicts"], "| HN:", d["primary"]["hard_negative_rules_attempted"])
print("finding.confirmed:", d["finding"]["confirmed_pairs"], "rejected:", d["finding"]["rejected_pairs"])
print("S4 fired:", d["finding"]["S4_official_identifier_fired"], "S1:", d["finding"]["s1_exact_name_fired"], "S2:", d["finding"]["s2_model_in_both_fired"])
