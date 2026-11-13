#!/usr/bin/env python
"""Extended summaries: merge probes, branch counts, branch trees."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, 'inventory_facts.json'), encoding='utf-8'))
modes = sys.argv[1:] or ['merge']


def hdr(t):
    print('\n' + '=' * 10 + ' ' + t + ' ' + '=' * 10)


def want(m):
    return 'all' in modes or m in modes


if want('merge'):
    hdr('MERGE PROBES (open PRs)')
    for p in d['prs']:
        if p['state'] != 'OPEN':
            continue
        mm = p.get('merge_probe_main') or {}
        mb = p.get('merge_probe_declared_base') or {}
        print(f"#{p['number']:>2} {p['headRefName']:44s} base={p['baseRefName']:34s} "
              f"into_main={'CLEAN' if mm.get('clean') else 'CONFLICT'} "
              f"({len(mm.get('conflicts', []))} paths) "
              f"into_declared_base={'CLEAN' if mb.get('clean') else 'CONFLICT'}")
        if not mm.get('clean'):
            print('     main conflicts:', ', '.join(mm.get('conflicts', [])[:8]))

if want('counts'):
    hdr('BRANCH COUNTS')
    print(json.dumps(d['branch_counts'], indent=1))

if want('bt'):
    hdr('BRANCH TREES (open PR heads)')
    for branch, t in d['branch_trees'].items():
        print(f"\n--- {branch} (PR #{t['pr']}) files={t['files']} bytes={t['bytes']}")
        print('  new top-level entries:', ', '.join(t['root_new']))
        top = sorted(t['top_level'].items(), key=lambda kv: -kv[1]['bytes'])[:8]
        print('  top:', '; '.join(f"{k}:{v['files']}f" for k, v in top))
        print('  notable added (<=2 levels):', ', '.join(t['notable_added'][:40]))

if want('merged'):
    hdr('MERGED / STALE BRANCH CHECK')
    for p in d['prs']:
        if p['state'] == 'MERGED':
            print(f"#{p['number']:>2} {p['headRefName']:44s} head_in_main={p.get('merged_into_main')}")
