import hashlib,glob,os,json,collections
rows=[]
for p in sorted(glob.glob('verify/run3_final_snapshot/*')+glob.glob('dataset/*_compact.jsonl.gz')+['FROZEN_RULES.json','REGULATORY_ANCHORS.jsonl','EVIDENCE_LINKS.jsonl','dataset/frozen_vocab.json']):
    rows.append({'path':p.replace('\\','/'),'bytes':os.path.getsize(p),'sha256':hashlib.sha256(open(p,'rb').read()).hexdigest()})
json.dump(rows,open('verify/run3_final_snapshot/SNAPSHOT_FILES.json','w'),indent=1)
for r in rows: print(r['sha256'][:16],r['path'])
L=[json.loads(l) for l in open('EVIDENCE_LINKS.jsonl',encoding='utf-8')]
print('rows',len(L),'tiers',dict(collections.Counter(r['tier'] for r in L)))
print('keys of first row:',list(L[0].keys()))
