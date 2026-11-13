p='verify_final.py'; s=open(p,encoding='utf-8').read()
s=s.replace('r["source"]','r["evidence_source"]').replace('top["source"]','top["evidence_source"]')
open(p,'w',encoding='utf-8').write(s); print('ok')
