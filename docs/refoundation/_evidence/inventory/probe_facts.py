#!/usr/bin/env python
"""Probe repo_facts.json structure for the inventory audit. Read-only."""
import json, sys

P = 'docs/refoundation/_evidence/repo_facts.json'
d = json.load(open(P, encoding='utf-8'))

def show(label, obj, n=3000):
    print(f"\n=== {label} ===")
    print(json.dumps(obj, indent=1, ensure_ascii=False)[:n])

show('summary', d['pull_request_summary'])
print("\n=== PR keys ==="); print(list(d['pull_requests'][0].keys()))
show('PR[0]', d['pull_requests'][0], 2500)

rb = d['remote_branches']; k = list(rb.keys())[0]
show(f'remote branch sample {k}', rb[k], 1200)
lb = d['local_branches']; k2 = list(lb.keys())[0]
show(f'local branch sample {k2}', lb[k2], 1200)
show('main_tree_by_top_level', d['main_tree_by_top_level'], 4000)
show('pages', d['pages'], 1500)
print("\nworktrees:", len(d['worktrees']))
show('worktrees[0:3]', d['worktrees'][:3], 1500)
print("\nremote branch names:")
for k, v in rb.items():
    print(' ', k, '|', v if not isinstance(v, dict) else json.dumps(v, ensure_ascii=False)[:150])
print("\nlocal branch names:", len(lb))
for k, v in lb.items():
    print(' ', k, '|', json.dumps(v, ensure_ascii=False)[:170] if isinstance(v, dict) else v)
