#!/usr/bin/env python
"""Which horizon-001 added files are NOT identical in convergence-001 (the sanitised copy)?"""
import subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def git(*a):
    return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stdout


def blobs(ref):
    d = {}
    for ln in git('ls-tree', '-r', ref).splitlines():
        if ln.strip():
            meta, p = ln.split('\t', 1)
            d[p] = meta.split()[2]
    return d


def added(ref):
    return [ln.split('\t')[-1] for ln in git('diff', '--name-status', 'origin/main...' + ref).splitlines()
            if ln.startswith('A\t')]


hor = blobs('origin/research/horizon-001')
conv = blobs('origin/integration/convergence-001')
a = added('origin/research/horizon-001')
diff = [p for p in a if conv.get(p) != hor[p]]
print('horizon added:', len(a), '| not identical in convergence:', len(diff))
for p in sorted(diff):
    state = 'ABSENT' if p not in conv else 'DIFFERS'
    print(f'  {state:7s} {p}')
