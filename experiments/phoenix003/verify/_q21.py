import json,hashlib
m=json.load(open('results/manifest.json')); v=json.load(open('results/verdict.json')); d=json.load(open('results/d_leadtime.json')); b=json.load(open('results/b_links.json')); b2=json.load(open('results/b2_novelty.json'))
print('manifest generated_at',m['generated_at'],'stages',list(m['stages'].keys()))
print('verdict',v['verdict'],'k',v['gates']['k_verified_links'],'spec',v['gates']['specificity'],'p',v['gates']['p_placebo_median_lead'])
print('b_links k',b['anchors_with_verified_link'],'tiers',b['tier_counts'])
print('b2',{k:b2[k] for k in ('link_status_counts','anchors_with_regulatory_link' if 'anchors_with_regulatory_link' in b2 else 'anchors_with_pre_regulatory_link','anchors_with_product_specific_pre_regulatory_link')})
print('ladder',{k:{kk:v['anchors'] for kk in ('anchors',) for v in [d['validity_ladder'][k]]} for k in d['validity_ladder']})
for p in ('REGULATORY_ANCHORS.jsonl','EVIDENCE_LINKS.jsonl'):
    print(p,hashlib.sha256(open(p,'rb').read()).hexdigest())
