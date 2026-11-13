import json
d=json.load(open('verify/run2_snapshot/d_leadtime.json'))
print('run2 ladder levels:',list(d['validity_ladder'].keys()))
m=json.load(open('verify/run2_snapshot/manifest.json'))
print('run2 stages:',list(m['stages'].keys()))
print('run2 files include epmc_df_meta/rare_tokens:',[f['path'] for f in m['files'] if 'epmc_df' in f['path'] or 'rare' in f['path']])
