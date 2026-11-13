#!/usr/bin/env python
"""Render ancestry_verify.json."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, 'ancestry_verify.json'), encoding='utf-8'))

print('=== ANCESTRY: head contains base? ===')
cols = list(next(iter(d['contains_ancestor'].values())).keys())
short = {c: c.split('/')[-1][:14] for c in cols}
print(f"{'head':44s} " + ' '.join(f"{short[c]:>14s}" for c in cols))
for br, row in d['contains_ancestor'].items():
    print(f"{br:44s} " + ' '.join(f"{('YES' if row[c] else '.'):>14s}" for c in cols))

print('\n=== COPY IDENTITY (>=10 identical added files) ===')
for rec in d['copy_identity']:
    if not rec['identical_to']:
        continue
    print(f"\nPR #{rec['pr']} {rec['branch']} added_vs_main={rec['added_vs_main']}")
    for o, v in sorted(rec['identical_to'].items(), key=lambda kv: -kv[1]['count']):
        print(f"   identical to {o:46s} {v['count']:4d} files = {v['pct']:5.1f}%  e.g. {v['examples'][:2]}")

print('\n=== BLOB VARIANTS ===')
for f, v in d['blob_variants'].items():
    print(f"\n{f}: {len(v)} distinct blobs")
    for sha, brs in v.items():
        print(f"   {sha[:12]}  {len(brs):2d} refs: {', '.join(brs[:12])}{' ...' if len(brs) > 12 else ''}")
