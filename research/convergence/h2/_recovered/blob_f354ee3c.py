import re
p = "experiments/regulatory/exp_h2_identity.py"
s = open(p, encoding="utf-8").read()
s = s.replace("    hard = add_hard_negatives(pairs, fda, md)",
              "    hard, hn_rules = add_hard_negatives(pairs, fda, md)")
s = s.replace('"by_construction_rule": dict(by_rule),',
              '"by_construction_rule": dict(by_rule),\n        "hard_negative_rules_attempted": hn_rules,')
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched")
