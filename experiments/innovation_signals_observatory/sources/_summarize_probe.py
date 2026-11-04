import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding='utf-8'))
for k, v in d['companies'].items():
    print('=' * 78)
    print(k, v['company_name'], 'ATS:', v['ats_hypotheses'])
    for c in v['candidates']:
        print('   ', c['status'], c['url'][:78], '->', (c.get('final_url') or '')[:88],
              '|', c['content_type'], '| ats:', c['ats_hits'], '| jsonld:', c.get('jsonld_scripts'),
              '| err:', c['error'], '| ms:', c['elapsed_ms'])
    for h, r in v['robots'].items():
        print('    robots', h, r['status'], r['error'])
        for path, vd in r['verdicts'].items():
            print('       ', path, '->', vd['verdict'], vd['rule'], 'certain' if vd.get('certain') else '')
