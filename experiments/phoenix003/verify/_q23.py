import json
new=json.load(open('FROZEN_RULES.json'))
print('name_vocab keys:',list(new['name_vocab'].keys()))
print('name_vocab non-stoplist:',{k:v for k,v in new['name_vocab'].items() if k!='stoplist_part_a'})
print('verdict:',json.dumps(new['verdict'],indent=1))
print('anchor:',json.dumps(new['anchor'],indent=1))
print('evidence window:',new['evidence']['window_years_before_anchor'],new['evidence']['window_start_global'])
print('stats:',new['stats'])
