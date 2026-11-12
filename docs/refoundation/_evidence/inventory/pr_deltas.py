#!/usr/bin/env python
"""Per-PR true delta vs declared base + hidden-stack import estimate."""
import json, subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
FACTS = 'docs/refoundation/_evidence/repo_facts.json'
facts = json.load(open(FACTS, encoding='utf-8'))


def git(*a):
    return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stdout


def numstat(a, b):
    files = adds = dels = 0
    for ln in git('diff', '--numstat', f'{a}...{b}').splitlines():
        p = ln.split('\t')
        if len(p) < 3:
            continue
        files += 1
        if p[0].isdigit():
            adds += int(p[0])
        if p[1].isdigit():
            dels += int(p[1])
    return files, adds, dels


def count(a, b):
    left, right = git('rev-list', '--left-right', '--count', f'{a}...{b}').strip().split('\t')
    return int(right), int(left)   # ahead, behind


# ancestry edges we rely on for merge order
EDGES = [
    ('origin/research/phoenix-001-external-methods', 'origin/research/phoenix-001-round2'),
    ('origin/feat/live-observatory-v1', 'origin/research/s028-temporal-graph-early-signal'),
    ('origin/feat/live-observatory-v1', 'origin/research/s029-evidence-based-relations'),
    ('origin/maintenance/repository-consolidation', 'origin/main'),
]
print('=== ANCESTRY EDGES ===')
for a, b in EDGES:
    rc = subprocess.run(['git', '-C', ROOT, 'merge-base', '--is-ancestor', a, b]).returncode
    print(f'  {a:56s} ancestor of {b:50s}: {"YES" if rc == 0 else "no"}')

print('\n=== PER-PR DELTA vs DECLARED BASE vs DELTA vs MAIN ===')
print(f"{'PR':>4} {'head':44s} {'base':34s} {'vs_base_f/+/-':>22s} {'vs_main_f/+/-':>22s}")
rows = []
for p in facts['pull_requests']:
    if p['state'] != 'OPEN':
        continue
    h = 'origin/' + p['headRefName']
    b = 'origin/' + p['baseRefName']
    fb = numstat(b, h)
    fm = numstat('origin/main', h)
    rows.append({'pr': p['number'], 'head': p['headRefName'], 'base': p['baseRefName'],
                 'vs_base': fb, 'vs_main': fm, 'draft': p['isDraft']})
    print(f"{p['number']:>4} {p['headRefName']:44s} {p['baseRefName']:34s} "
          f"{fb[0]:6d}/{fb[1]:7d}/{fb[2]:6d}   {fm[0]:6d}/{fm[1]:7d}/{fm[2]:6d}")

json.dump(rows, open('docs/refoundation/_evidence/inventory/pr_deltas.json', 'w', encoding='utf-8'),
          indent=1, ensure_ascii=False)
print('\nwrote pr_deltas.json')
