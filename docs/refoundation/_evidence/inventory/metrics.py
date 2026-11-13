#!/usr/bin/env python
"""Compute citable summary metrics for ORIGIN/MAIN for the inventory doc."""
import subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def git(*a):
    return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stdout


tree = []
for ln in git('ls-tree', '-r', '-l', 'origin/main').splitlines():
    if not ln.strip():
        continue
    meta, path = ln.split('\t', 1)
    p = meta.split()
    tree.append({'path': path, 'size': int(p[3]) if p[3].isdigit() else 0})

print('files', len(tree), 'bytes', sum(t['size'] for t in tree))

for root in ['medradar', 'tests', 'scripts', 'tools', 'verifier', 'papers', 'research',
             'config', 'docs', 'experiments', '.github']:
    sel = [t for t in tree if t['path'].startswith(root + '/')]
    py = [t for t in sel if t['path'].endswith('.py')]
    md = [t for t in sel if t['path'].endswith('.md')]
    print(f'{root:12s} files={len(sel):5d} py={len(py):4d} md={len(md):4d} bytes={sum(t["size"] for t in sel):10d}')

# LOC for code roots (skip experiments which are mostly data)
loc = {}
for root in ['medradar', 'tests', 'scripts', 'tools', 'verifier', 'papers', 'research']:
    n = 0
    for t in [x for x in tree if x['path'].startswith(root + '/') and x['path'].endswith('.py')]:
        body = git('show', 'origin/main:' + t['path'])
        n += body.count('\n')
    loc[root] = n
print('LOC(.py, newline count):', loc, 'sum', sum(loc.values()))

# experiment families
exp_dirs = sorted({t['path'].split('/')[1] for t in tree
                   if t['path'].startswith('experiments/') and t['path'].count('/') >= 2})
b0 = [d for d in exp_dirs if d.startswith('b0') and d[1:].isdigit()]
other = [d for d in exp_dirs if d not in b0]
print('experiments dirs:', len(exp_dirs), '| b0xx:', len(b0), b0, '| others:', other)

# test modules
tm = [t['path'] for t in tree if t['path'].startswith('tests/test_') and t['path'].endswith('.py')]
print('test modules:', len(tm))
fixtures = [t for t in tree if t['path'].startswith('tests/fixtures/')]
print('fixture files:', len(fixtures))

# docs breakdown
docs = [t for t in tree if t['path'].startswith('docs/')]
print('docs root md:', len([t for t in docs if t['path'].count('/') == 1 and t['path'].endswith('.md')]))
print('docs root html:', [t['path'] for t in docs if t['path'].endswith('.html')])
print('docs research:', len([t for t in docs if t['path'].startswith('docs/research/')]))
print('docs calibration:', len([t for t in docs if t['path'].startswith('docs/calibration/')]))

# research studies
rs = [t for t in tree if t['path'].startswith('research/studies/')]
print('research/studies files:', len(rs))
rr = [t for t in tree if t['path'].startswith('research/RESULTS/')]
print('research/RESULTS files:', len(rr))
