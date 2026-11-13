import json,hashlib,os
m=json.load(open('results/manifest.json'))
print('generated_at',m['generated_at']); print('stages',m['stages']); print('total_s',m.get('total_seconds'))
bad=[]
for f in m['files']:
    p=f['path']
    if not os.path.exists(p): bad.append((p,'MISSING')); continue
    h=hashlib.sha256(open(p,'rb').read()).hexdigest()
    if h!=f['sha256'] or os.path.getsize(p)!=f['bytes']: bad.append((p,'MISMATCH',h,f['sha256']))
print('manifest files',len(m['files']),'mismatches',len(bad))
for b in bad[:10]: print(' ',b)
v=json.load(open('results/verdict.json')); d=json.load(open('results/d_leadtime.json')); b=json.load(open('results/b_links.json')); b2=json.load(open('results/b2_novelty.json')); c=json.load(open('results/c_controls.json'))
print('verdict',v['verdict'],'k',v['gates']['k_verified_links'],'share90',v['gates']['share_ge_90_days'],'spec',v['gates']['specificity'],'p',v['gates']['p_placebo_median_lead'],'coverage',v['gates']['coverage_rate'])
print('b_links', {k:b[k] for k in ('anchors','anchors_with_verified_link','tier_counts','link_rows')})
print('ladder', {k:{'anchors':d['validity_ladder'][k]['anchors'],'median':d['validity_ladder'][k]['median'],'share90':d['validity_ladder'][k]['share_ge_90_days']} for k in d['validity_ladder']})
print('overall', {k:d['overall_publication_clock'][k] for k in ('anchors_with_verified_link','share_ge_90_days','median','max','min')})
print('b2', {k:b2[k] for k in b2 if isinstance(b2[k],(int,float,str))})
print('c3', {k:c['c3_decoy'].get(k) for k in ('specificity','specificity_matched_denominator','decoy_link_rate','real_link_rate','real_link_rate_matched','decoy_linked','anchors_with_decoy','specificity_note')})
print('c4b', {k:c['c4b_date_permutation'].get(k) for k in ('draws','p_median_lead','p_link_rate')})
print('c4a', {k:c['c4a_time_shift'].get(k) for k in ('draws','p_median_lead')})
A=[json.loads(l) for l in open('REGULATORY_ANCHORS.jsonl',encoding='utf-8')]
print('anchor rows',len(A),'sha',hashlib.sha256(open('REGULATORY_ANCHORS.jsonl','rb').read()).hexdigest()[:16])
print('per firm',{})
import collections
print(dict(collections.Counter(a['firm'] for a in A)))
L=[json.loads(l) for l in open('EVIDENCE_LINKS.jsonl',encoding='utf-8')]
print('link rows',len(L),'tiers',dict(collections.Counter(r['tier'] for r in L)),'sha',hashlib.sha256(open('EVIDENCE_LINKS.jsonl','rb').read()).hexdigest()[:16])
print('link row keys',list(L[0].keys()))
