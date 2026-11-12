#!/usr/bin/env python
"""Exact duplicate accounting for #30 against the union of #29 and #28."""
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


conv = blobs('origin/integration/convergence-001')
hor = blobs('origin/research/horizon-001')
atl = blobs('origin/foundation/atlas-001')
a = added('origin/integration/convergence-001')

dup_h = [p for p in a if p in hor and conv.get(p) == hor[p]]
dup_a = [p for p in a if p in atl and conv.get(p) == atl[p]]
dup_union = sorted(set(dup_h) | set(dup_a))
unique = [p for p in a if p not in set(dup_union)]
print('PR #30 added vs main      :', len(a))
print('  identical to horizon-001:', len(dup_h))
print('  identical to atlas-001  :', len(dup_a))
print('  identical to union      :', len(dup_union))
print('  not identical to either :', len(unique))
print('  unique examples:', unique[:15])
