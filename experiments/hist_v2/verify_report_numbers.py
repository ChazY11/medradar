"""Verify every number quoted in experiments/hist_v2/REPORT.md against results.json / the panel manifest."""
import json
from pathlib import Path

ROOT = Path('.')
r = json.loads((ROOT / 'experiments/hist_v2/results.json').read_text(encoding='utf-8'))
checks = []


def chk(name, actual, expected, tol=5e-4):
    checks.append((actual is not None and abs(actual - expected) <= tol, name, actual, expected))


def exact(name, actual, expected):
    checks.append((actual == expected, name, actual, expected))


p = r['primary']
m = p['mean_per_origin_ap']
for model, want in (('B0', 0.0170), ('B1', 0.0435), ('B2', 0.0277), ('B3', 0.0619),
                    ('M1A', 0.0515), ('M1B', 0.0812), ('M1C', 0.0775)):
    chk('mean AP ' + model, m[model]['mean'], want)
exact('origins with AP', m['M1C']['n'], 21)
exact('bootstrap status', p['bootstrap']['status'], 'OK')
chk('degenerate share', p['bootstrap']['share_resamples_below_min_contributing_origins'], 0.0)
for model, want in (('B1', 0.0489), ('B3', 0.0739), ('M1C', 0.0909)):
    chk(f'bootstrap mean {model}', p['bootstrap']['mean_ap'][model]['bootstrap_mean'], want)
chk('B1 ci low', p['bootstrap']['mean_ap']['B1']['ci_low'], 0.0345)
chk('B1 ci high', p['bootstrap']['mean_ap']['B1']['ci_high'], 0.0663)
chk('B3 ci low', p['bootstrap']['mean_ap']['B3']['ci_low'], 0.0499)
chk('B3 ci high', p['bootstrap']['mean_ap']['B3']['ci_high'], 0.1042)
chk('M1C ci low', p['bootstrap']['mean_ap']['M1C']['ci_low'], 0.0613)
chk('M1C ci high', p['bootstrap']['mean_ap']['M1C']['ci_high'], 0.1238)
d1 = p['deltas_vs_baselines']['M1C-B1']
chk('delta M1C-B1 point', d1['point_delta'], 0.0340)
chk('delta M1C-B1 ci low', d1['bootstrap']['ci_low'], 0.0215)
chk('delta M1C-B1 ci high', d1['bootstrap']['ci_high'], 0.0661)
chk('delta M1C-B1 mde', d1['bootstrap']['mde_80pct_power_alpha_0.05'], 0.0316)
d2 = p['deltas_vs_baselines']['M1C-B2']
chk('delta M1C-B2 point', d2['point_delta'], 0.0498)
chk('delta M1C-B2 ci low', d2['bootstrap']['ci_low'], 0.0284)
chk('delta M1C-B2 ci high', d2['bootstrap']['ci_high'], 0.0899)
d3 = p['deltas_vs_baselines']['M1C-B3']
chk('delta M1C-B3 point', d3['point_delta'], 0.0156)
chk('delta M1C-B3 ci low', d3['bootstrap']['ci_low'], -0.0107)
chk('delta M1C-B3 ci high', d3['bootstrap']['ci_high'], 0.0445)
chk('delta M1C-B3 p', d3['bootstrap']['p_two_sided'], 0.212)
chk('delta M1C-B3 mde', d3['bootstrap']['mde_80pct_power_alpha_0.05'], 0.0389)

dec = r['decision']['H1']
exact('H1 supported', dec['supported'], True)
exact('H1 criterion met', dec['criterion_met'], True)
exact('H1 powered', dec['powered'], True)
chk('H1 share origins positive', dec['criterion_components']['share_origins_positive'], 0.8571)
exact('H1 origins with defined delta', dec['criterion_components']['n_origins_with_defined_delta'], 21)

perm = (r.get('robustness') or {}).get('permutation_null') or {}
exact('perm achieved', perm.get('n_permutations_achieved'), 200)
chk('perm observed', perm.get('observed_delta_ap'), 0.0340)
chk('perm p', perm.get('empirical_p_value_one_sided'), 0.004975)

fg = (r.get('robustness') or {}).get('feature_groups') or {}
for group, want in (('A', 0.0515), ('B', 0.0812), ('C', 0.0775)):
    chk('ablation ' + group, fg[group]['mean_per_origin_ap']['mean'], want)

eras = (r.get('robustness') or {}).get('eras') or {}
chk('era 1995-2004 delta', eras['1995-2004']['delta_ap_M1C_minus_B1'], 0.0464)
chk('era 1995-2004 M1C', eras['1995-2004']['models']['M1C']['mean'], 0.1082)
chk('era 2005-2015 delta', eras['2005-2015']['delta_ap_M1C_minus_B1'], 0.0227)
chk('era 2005-2015 M1B', eras['2005-2015']['models']['M1B']['mean'], 0.0574)
chk('era 2005-2015 M1C', eras['2005-2015']['models']['M1C']['mean'], 0.0496)

sec = r['secondary']
h4 = sec['R_dom|h4']['bootstrap']['comparisons']['M1C-B1']
chk('h4 delta', h4['mean'], 0.0432)
chk('h4 ci low', h4['ci_low'], 0.0214)
chk('h4 ci high', h4['ci_high'], 0.0692)
h4b3 = sec['R_dom|h4']['bootstrap']['comparisons']['M1C-B3']
chk('h4 B3 delta', h4b3['mean'], 0.0211)
chk('h4 B3 ci low', h4b3['ci_low'], -0.0019)
chk('h4 B3 ci high', h4b3['ci_high'], 0.0448)
adj = r['decision']['secondary_risk_set']
chk('R_dom_adj delta', adj['delta_ap_M1C_minus_B1'], 0.0554)
exact('R_dom_adj status', adj['status'], 'DESCRIPTIVE')
hold = r['decision']['holdout']
chk('holdout delta', hold['delta_ap_M1C_minus_B1'], 0.0095)
exact('holdout status', hold['status'], 'DESCRIPTIVE_NO_INFERENCE')

lt = r['lead_time']
exact('lead entries', lt['entries']['n_entries'], 133)
exact('lead excluded', lt['entries']['excluded_never_in_risk_set'], 15)
exact('lead cells', lt['entries']['evaluation_window'][1] is not None and lt['primary_budget']['n_candidate_cells'], 15233)
exact('lead positives', lt['primary_budget']['n_positive_cells'], 252)
frontier = {round(x['budget'], 2): x for x in lt['h5_frontier']}
for budget, (precision, recall, alerted, missed, median, fa) in {
        0.01: (0.106, 0.083, 14, 119, 5, 11.7),
        0.05: (0.079, 0.294, 41, 92, 7, 56.8),
        0.10: (0.058, 0.397, 58, 75, 6, 106.1)}.items():
    row = frontier[budget]
    chk(f'lead {budget} precision', row['precision'], precision)
    chk(f'lead {budget} recall', row['recall'], recall)
    exact(f'lead {budget} alerted', row['entries_alerted'], alerted)
    exact(f'lead {budget} missed', row['entries_missed'], missed)
    chk(f'lead {budget} median', row['lead_quarters']['median'], float(median))
    chk(f'lead {budget} fa', row['false_alarms_per_1000_candidate_quarters'], fa, 0.06)

panel = r['dataset']['panel']
exact('panel pairs', panel['n_pairs_recorded'], 377)
exact('panel events', panel['total_material_events'], 14704)
exact('panel domains', panel['n_domains'], 22)
exact('panel companies', panel['n_companies'], 53)
configs = r['dataset']['configs']['R_dom|h8']
exact('origins', len(configs), 21)
exact('candidate cells', sum(c['n_candidates'] for c in configs), 15233)
exact('positive cells', sum(c['n_positives'] for c in configs), 252)
leak = r['leakage_controls']
exact('purge violations', leak['label_purge']['violations'], 0)
exact('replay mismatches', leak['independent_replay']['mismatches'], 0)
exact('replay cells', leak['independent_replay']['cells_sampled'], 300)
attr = (r.get('robustness') or {}).get('attribution_sensitivity_no_acquired') or {}
exact('sensitivity status', attr.get('status'), 'DESCRIPTIVE_SENSITIVITY')
exact('sensitivity events retained', attr.get('n_events_retained'), 14487)
exact('sensitivity events primary', attr.get('n_events_primary'), 14704)
exact('sensitivity pairs', attr.get('n_pairs_retained'), 377)
chk('sensitivity M1C', attr['mean_per_origin_ap']['M1C']['mean'], 0.0791)
chk('sensitivity B1', attr['mean_per_origin_ap']['B1']['mean'], 0.0429)
chk('sensitivity B3', attr['mean_per_origin_ap']['B3']['mean'], 0.0656)
chk('sensitivity delta', attr.get('delta_ap_M1C_minus_B1'), 0.0361)
exact('sensitivity bootstrap ok', attr['bootstrap'].get('status'), 'OK')

power = r['power']
exact('power status', power['status'], 'POWERED')
chk('power mde', power['primary_M1C_minus_B1']['mde_80pct_power_alpha_0.05'], 0.0316)

failed = [c for c in checks if not c[0]]
print(f'checks: {len(checks)}; failed: {len(failed)}')
for ok, name, actual, expected in failed:
    print('FAIL', name, 'actual=', actual, 'expected=', expected)
raise SystemExit(0 if not failed else 1)
