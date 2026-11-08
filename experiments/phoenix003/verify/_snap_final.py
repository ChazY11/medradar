import hashlib,glob,os,json
rows=[]
paths=sorted(glob.glob('verify/final_snapshot/*'))+sorted(glob.glob('dataset/*_compact.jsonl.gz'))+['FROZEN_RULES.json','REGULATORY_ANCHORS.jsonl','EVIDENCE_LINKS.jsonl','dataset/firm_lineage.json','dataset/frozen_vocab.json']
for p in paths:
    if os.path.isfile(p):
        rows.append({'path':p.replace('\\','/'),'bytes':os.path.getsize(p),'sha256':hashlib.sha256(open(p,'rb').read()).hexdigest(),'mtime':os.path.getmtime(p)})
json.dump(rows,open('verify/final_snapshot/SNAPSHOT_FILES.json','w'),indent=1)
for r in rows: print(r['sha256'][:16],r['path'])
