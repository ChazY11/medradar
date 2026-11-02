"""Verify every number quoted in experiments/hist_v1/REPORT.md against results.json / audits / timeline."""
import json
from pathlib import Path

ROOT = Path('.')
r = json.loads((ROOT / 'experiments/hist_v1/results.json').read_text(encoding='utf-8'))
tl = json.loads((ROOT / 'experiments/hist_v1/five_firm_timeline.json').read_text(encoding='utf-8'))
aud = json.loads((ROOT / 'experiments/hist_v1/audits.json').read_text(encoding='utf-8'))
checks = []


def chk(name, actual, expected, tol=5e-4):
    checks.append((actual is not None and abs(actual - expected) <= tol, name, actual, expected))


def exact(name, actual, expected):
    checks.append((actual == expected, name, actual, expected))


p = r['primary']
m = p['mean_per_origin_ap']
for model, want in (('B0', 0.0229), ('B1', 0.0553), ('B2', 0.0468), ('B3', 0.0699),
                    ('M1A', 0.0489), ('M1B', 0.0905), ('M1C', 0.1137)):
    chk('primary mean AP ' + model, m[model]['mean'], want)
exact('primary origins with AP', m['M1C']['n'], 30)
chk('B1 ci low', p['bootstrap']['mean_ap']['B1']['ci_low'], 0.0361)
chk('B1 ci high', p['bootstrap']['mean_ap']['B1']['ci_high'], 0.0922)
chk('B3 ci low', p['bootstrap']['mean_ap']['B3']['ci_low'], 0.0518)
chk('B3 ci high', p['bootstrap']['mean_ap']['B3']['ci_high'], 0.1201)
chk('M1C ci low', p['bootstrap']['mean_ap']['M1C']['ci_low'], 0.0753)
chk('M1C ci high', p['bootstrap']['mean_ap']['M1C']['ci_high'], 0.1837)
exact('bootstrap status', p['bootstrap']['status'], 'OK')
chk('degenerate share', p['bootstrap']['share_resamples_below_min_contributing_origins'], 0.001)
chk('contributing median', p['bootstrap']['contributing_origins_median'], 29.0)
d1 = p['deltas_vs_baselines']['M1C-B1']
chk('delta M1C-B1 point', d1['point_delta'], 0.0584)
chk('delta M1C-B1 mean', d1['bootstrap']['mean'], 0.068)
chk('delta M1C-B1 ci low', d1['bootstrap']['ci_low'], 0.0020)
chk('delta M1C-B1 ci high', d1['bootstrap']['ci_high'], 0.1213)
chk('delta M1C-B1 p', d1['bootstrap']['p_two_sided'], 0.045)
chk('delta M1C-B1 mde', d1['bootstrap']['mde_80pct_power_alpha_0.05'], 0.0896)
d2 = p['deltas_vs_baselines']['M1C-B2']
chk('delta M1C-B2 point', d2['point_delta'], 0.0669)
chk('delta M1C-B2 ci low', d2['bootstrap']['ci_low'], 0.0147)
chk('delta M1C-B2 ci high', d2['bootstrap']['ci_high'], 0.1198)
chk('delta M1C-B2 p', d2['bootstrap']['p_two_sided'], 0.004)
chk('delta M1C-B2 mde', d2['bootstrap']['mde_80pct_power_alpha_0.05'], 0.0813)
d3 = p['deltas_vs_baselines']['M1C-B3']
chk('delta M1C-B3 point', d3['point_delta'], 0.0438)
chk('delta M1C-B3 ci low', d3['bootstrap']['ci_low'], -0.0184)
chk('delta M1C-B3 ci high', d3['bootstrap']['ci_high'], 0.0957)
chk('delta M1C-B3 p', d3['bootstrap']['p_two_sided'], 0.198)
chk('delta M1C-B3 mde', d3['bootstrap']['mde_80pct_power_alpha_0.05'], 0.0875)

dec = r['decision']['H1']
exact('H1 h8 supported', dec['h8_primary']['supported'], True)
exact('H1 h8 status', dec['h8_primary']['status'], 'SUPPORTED')
chk('H1 h8 delta', dec['h8_primary']['delta_ap'], 0.0584)
chk('H1 h8 ci low', dec['h8_primary']['ci_low'], 0.0020)
chk('H1 h8 ci high', dec['h8_primary']['ci_high'], 0.1213)
chk('H1 h8 mde', dec['h8_primary']['mde_80pct_power_alpha_0.05'], 0.0896)
exact('H1 h4 status', dec['h4_secondary']['status'], 'UNRELIABLE (no pre-registered CI quotable)')
chk('H1 h4 delta', dec['h4_secondary']['delta_ap'], 0.0565)
chk('H1 h4 descriptive low', dec['h4_secondary']['descriptive_interval_not_a_ci'][0], -0.0020)
chk('H1 h4 descriptive high', dec['h4_secondary']['descriptive_interval_not_a_ci'][1], 0.1143)
exact('H2 status', r['decision']['H2']['status'], 'EVALUATED_BUT_WORSE_AND_BOOTSTRAP_UNRELIABLE')
chk('H2 delta', r['decision']['H2']['delta_ap_D_minus_C'], -0.0053)

perm = r['robustness']['permutation_null']
chk('perm observed', perm['observed_delta_ap'], 0.0584)
chk('perm null mean', perm['null_distribution']['mean'], 0.0239)
chk('perm null sd', perm['null_distribution']['sd'], 0.0129)
chk('perm null max', perm['null_distribution']['max'], 0.0667)
chk('perm p', perm['empirical_p_value_one_sided'], 0.0299)
exact('perm achieved', perm['n_permutations_achieved'], 200)

fg = r['robustness']['feature_groups']
chk('ablation A', fg['A']['mean_per_origin_ap']['mean'], 0.0489)
chk('ablation A delta', fg['A']['delta_ap_vs_B1'], -0.0064)
chk('ablation B', fg['B']['mean_per_origin_ap']['mean'], 0.0905)
chk('ablation B delta', fg['B']['delta_ap_vs_B1'], 0.0352)
chk('ablation C', fg['C']['mean_per_origin_ap']['mean'], 0.1137)
chk('ablation C delta', fg['C']['delta_ap_vs_B1'], 0.0584)

eras = r['robustness']['eras']
chk('era 1995-2004 B1', eras['1995-2004']['models']['B1']['mean'], 0.0670)
chk('era 1995-2004 B3', eras['1995-2004']['models']['B3']['mean'], 0.0925)
chk('era 1995-2004 M1C', eras['1995-2004']['models']['M1C']['mean'], 0.1550)
chk('era 1995-2004 delta', eras['1995-2004']['delta_ap_M1C_minus_B1'], 0.0879)
chk('era 2005-2014 delta', eras['2005-2014']['delta_ap_M1C_minus_B1'], 0.0634)
chk('era 2015-2024 delta', eras['2015-2024']['delta_ap_M1C_minus_B1'], 0.0239)

full = r['secondary']['R_full|h8']
chk('R_full B1', full['mean_per_origin_ap']['B1']['mean'], 0.0307)
chk('R_full B3', full['mean_per_origin_ap']['B3']['mean'], 0.0397)
chk('R_full M1C', full['mean_per_origin_ap']['M1C']['mean'], 0.0607)
cmp8 = full['bootstrap']['comparisons']['M1C-B1']
chk('R_full delta bootstrap mean', cmp8['mean'], 0.0371)
chk('R_full point delta', full['mean_per_origin_ap']['M1C']['mean'] - full['mean_per_origin_ap']['B1']['mean'], 0.0300)
chk('R_full ci low', cmp8['ci_low'], 0.0128)
chk('R_full ci high', cmp8['ci_high'], 0.0699)
cmp3 = full['bootstrap']['comparisons']['M1C-B3']
chk('R_full B3 bootstrap mean', cmp3['mean'], 0.0225)
chk('R_full B3 point delta', full['mean_per_origin_ap']['M1C']['mean'] - full['mean_per_origin_ap']['B3']['mean'], 0.0210)
chk('R_full B3 ci low', cmp3['ci_low'], -0.0087)
chk('R_full B3 ci high', cmp3['ci_high'], 0.0565)
h4 = r['secondary']['R_full|h4']['bootstrap']['comparisons']['M1C-B1']
chk('R_full h4 bootstrap mean', h4['mean'], 0.0281)
chk('R_full h4 point delta',
    r['secondary']['R_full|h4']['mean_per_origin_ap']['M1C']['mean']
    - r['secondary']['R_full|h4']['mean_per_origin_ap']['B1']['mean'], 0.0204)
chk('R_full h4 ci low', h4['ci_low'], 0.0099)
chk('R_full h4 ci high', h4['ci_high'], 0.0516)

fus = r['fusion_h2']
chk('fusion C', fus['mean_per_origin_ap_C']['mean'], 0.0401)
chk('fusion D', fus['mean_per_origin_ap_D']['mean'], 0.0348)
chk('fusion delta', fus['delta_ap_D_minus_C'], -0.0053)
exact('fusion cells', fus['coverage']['cells'], 2902)
chk('fusion pub join', fus['coverage']['publication_join_rate'], 0.786)
chk('fusion trial present', fus['coverage']['trial_track_present_rate'], 0.910)
exact('fusion trial events', fus['coverage']['trial_events'], 2663)
exact('fusion trial unmapped', fus['coverage']['trial_events_unmapped_to_panel_tracks'], 1364)

lt = r['lead_time']
exact('lead entries in risk set', lt['entries']['n_entries'], 94)
exact('lead entries excluded', lt['entries']['excluded_never_in_risk_set'], 161)
exact('lead entries in window', lt['entries']['n_entries'] + lt['entries']['excluded_never_in_risk_set'], 255)
frontier = {round(x['budget'], 2): x for x in lt['h5_frontier']}
for budget, (precision, recall, alerted, missed, median_lead, fa) in {
        0.01: (0.206, 0.072, 9, 85, 5, 5.9),
        0.05: (0.137, 0.177, 19, 75, 6, 24.0),
        0.10: (0.094, 0.243, 24, 70, 6, 50.6),
        0.20: (0.073, 0.359, 38, 56, 6, 98.3)}.items():
    row = frontier[budget]
    chk(f'lead {budget} precision', row['precision'], precision)
    chk(f'lead {budget} recall', row['recall'], recall)
    exact(f'lead {budget} alerted', row['entries_alerted'], alerted)
    exact(f'lead {budget} missed', row['entries_missed'], missed)
    chk(f'lead {budget} median', row['lead_quarters']['median'], float(median_lead))
    chk(f'lead {budget} fa', row['false_alarms_per_1000_candidate_quarters'], fa, 0.06)

h = r['heterogeneity']
pp = h['h3_companies']['per_company']
elig = [v for v in pp.values() if v.get('eligible')]
exact('eligible companies', len(elig), 3)
chk('abbott delta', pp['abbott']['delta_ap'], 0.192)
chk('bbraun delta', pp['bbraun']['delta_ap'], 0.397)
chk('medtronic delta', pp['medtronic']['delta_ap'], 0.286)
dv = h['deep_vs_auxiliary']
chk('deep vs aux difference', dv['difference'], -0.038)
chk('deep vs aux ci low', dv['ci_low'], -0.168)
chk('deep vs aux ci high', dv['ci_high'], 0.093)
cats = {k: v for k, v in h['h4_categories']['per_category'].items() if v['n_positives']}
for name, want in (('orthopedics', 0.342), ('diabetes', 0.308), ('neuroscience', 0.144), ('surgery', 0.095),
                   ('specialty', 0.044), ('cardiovascular', 0.033), ('imaging', 0.024),
                   ('monitoring', -0.077), ('ivd', -0.099)):
    chk('category delta ' + name, cats[name]['delta_ap'], want)

ds = r['dataset']['panel']
exact('panel pairs', ds['n_pairs_recorded'], 528)
exact('panel events', ds['total_material_events'], 14704)
exact('panel quarters', ds['n_quarters'], 202)
exact('panel companies', ds['n_companies'], 53)
exact('panel tracks', ds['n_tracks'], 38)
exact('audit events', aud['panel_summary']['n_material_events'], 14704)
cfgs = r['dataset']['configs']['R_adj|h8']
exact('R_adj origins', len(cfgs), 30)
exact('R_adj candidates total', sum(c['n_candidates'] for c in cfgs), 8415)
exact('R_adj positives total', sum(c['n_positives'] for c in cfgs), 181)
exact('R_adj first positives', cfgs[0]['n_positives'], 12)
exact('R_adj last positives', cfgs[-1]['n_positives'], 4)
cfgs_full = r['dataset']['configs']['R_full|h8']
exact('R_full candidates total', sum(c['n_candidates'] for c in cfgs_full), 41892)
exact('R_full positives total', sum(c['n_positives'] for c in cfgs_full), 459)

leak = r['leakage_controls']
exact('leak purge violations', leak['label_purge']['violations'], 0)
exact('replay mismatches', leak['independent_replay']['mismatches'], 0)
exact('replay cells', leak['independent_replay']['cells_sampled'], 300)

for firm, tracks, last in (('medtronic', 32, '2012-Q4'), ('ge_healthcare', 11, '2000-Q4'),
                           ('philips', 15, '2025-Q2'), ('draeger', 4, '2014-Q4'), ('mindray', 3, '2011-Q1')):
    f = tl['deep_cases'][firm]
    exact('timeline tracks ' + firm, f['tracks_entered'], tracks)
    exact('timeline last entry ' + firm, f['last_entry'], last)

failed = [c for c in checks if not c[0]]
print(f'checks: {len(checks)}; failed: {len(failed)}')
for ok, name, actual, expected in failed:
    print('FAIL', name, 'actual=', actual, 'expected=', expected)
raise SystemExit(0 if not failed else 1)
