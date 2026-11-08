import json
L=json.load(open('dataset/firm_lineage.json'))
print('lineage top keys',list(L.keys()))
for f,spec in L['brand_tokens'].items():
    extras={k:v for k,v in spec.items() if k not in ('any_token','qualifier_tokens','segment_notes')}
    if extras: print(f,extras)
R=json.load(open('FROZEN_RULES.json'))
print('rules top keys',list(R.keys()))
print('novelty section:',json.dumps(R.get('novelty'),indent=1))
print('name_vocab extra:',{k:v for k,v in R['name_vocab'].items() if 'literature' in k or 'rare' in k})
