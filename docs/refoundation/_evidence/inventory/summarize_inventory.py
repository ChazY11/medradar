#!/usr/bin/env python
"""Render human-readable summaries of inventory_facts.json for the auditor."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, 'inventory_facts.json')
d = json.load(open(P, encoding='utf-8'))
modes = sys.argv[1:] or ['all']


def hdr(t):
    print('\n' + '=' * 10 + ' ' + t + ' ' + '=' * 10)


def want(m):
    return 'all' in modes or m in modes


if want('top'):
    hdr('TOP LEVEL')
    tot_f = tot_b = 0
    for k, v in sorted(d['top_level'].items(), key=lambda kv: -kv[1]['bytes']):
        print(f"{k:24s} {v['files']:6d} {v['bytes']:10d} {v['bytes']/1048576:8.2f} MiB")
        tot_f += v['files']; tot_b += v['bytes']
    print(f"{'TOTAL':24s} {tot_f:6d} {tot_b:10d} {tot_b/1048576:8.2f} MiB")

if want('med'):
    hdr('MEDRADAR FILES')
    for x in d['medradar_files']:
        print(f"{x['path']:56s} {x['bytes']:7d} {str(x['lines']):>6s}")

if want('cli'):
    hdr('CLI')
    print('__main__.py bytes', d['cli']['__main___bytes'])
    print('subcommands:', d['cli']['add_parser_subcommands'])

if want('prs'):
    hdr('PRS')
    for p in d['prs']:
        ba = p.get('base_ahead_behind_main')
        print(f"#{p['number']:>2} {p['state']:6s} draft={str(p['isDraft']):5s} "
              f"base={p['baseRefName']:38s} head={p['headRefName']:44s} "
              f"base_ab={ba} files={p['changedFiles']} +{p['additions']}/-{p['deletions']}")

if want('branches'):
    hdr('BRANCHES')
    for k, v in sorted(d['branches'].items()):
        ds = v['diffstat_vs_main']
        print(f"{k:48s} ah={v['ahead']:3d} bh={v['behind']:3d} "
              f"treefiles={ds['files']:4d} +{ds['additions']}/-{ds['deletions']} "
              f"| {v['tip_subject'][:60]}")

if want('tests'):
    hdr('TESTS')
    for t in d['tests']:
        print(f"{t['path']:56s} bytes={t['bytes']:6d} tests={t['test_count']:4d}")

if want('config'):
    hdr('CONFIG')
    for x in d['config']:
        print(f"{x['path']:56s} {x['bytes']:9d}")
    hdr('WORKFLOWS')
    for x in d['workflows']:
        print(f"{x['path']:56s} {x['bytes']:7d}")

if want('local'):
    hdr('LOCAL BRANCHES')
    for b in d['local_branches']:
        print(f"{b['name']:46s} ahead={b.get('ahead','?'):>4} behind={b.get('behind','?'):>4} "
              f"on_no_remote={b['commits_on_no_remote']:3d} upstream={b['upstream']}")

if want('bt'):
    hdr('BRANCH TREES (open PR heads)')
    for branch, t in d['branch_trees'].items():
        print(f"\n--- {branch} (PR #{t['pr']}) files={t['files']} bytes={t['bytes']}")
        print('  root_new:', ', '.join(t['root_new']))
        top = sorted(t['top_level'].items(), key=lambda kv: -kv[1]['bytes'])[:10]
        print('  top:', '; '.join(f"{k}:{v['files']}f/{v['bytes']}b" for k, v in top))
