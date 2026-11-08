p='verify_final.py'; s=open(p,encoding='utf-8').read()
s=s.replace('("anchor_id", "firm", "milestone_key", "product_code",\n                                              "tier", "source", "evidence_id", "evidence_date",','("anchor_id", "firm", "milestone_key", "product_code",\n                                              "tier", "evidence_source", "evidence_id", "evidence_date",')
open(p,'w',encoding='utf-8').write(s); print('ok')
