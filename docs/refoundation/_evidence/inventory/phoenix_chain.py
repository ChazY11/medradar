#!/usr/bin/env python
"""Resolve the local phoenix fork point and the S-028 ancestry question."""
import subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def git(*a):
    p = subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return p.returncode, p.stdout


def anc(a, b):
    return git('merge-base', '--is-ancestor', a, b)[0] == 0


S028 = 'origin/research/s028-temporal-graph-early-signal'
print('s028 tip is ancestor of:')
for ref in ['origin/integration/phase4-base', 'origin/research/innovation-signals-observatory',
            'origin/research/s031-hiring-capability-study', 'origin/integration/convergence-001',
            'research/phoenix-001-external-methods']:
    print(f'  {ref:52s} : {"YES" if anc(S028, ref) else "no"}')

rc, mb = git('merge-base', 'research/phoenix-001-external-methods', 'origin/integration/phase4-base')
mb = mb.strip()
print('\nmerge-base(local phoenix, phase4-base) =', mb[:12])
print('  subject:', git('log', '-1', '--format=%s', mb)[1].strip())
print('  is that s028 tip?', mb == git('rev-parse', S028)[1].strip())
print('  local phoenix contains s028 tip:', anc(S028, 'research/phoenix-001-external-methods'))

print('\nlocal phoenix unique commits (not in any remote):')
print(git('log', '--format=%h %s', 'research/phoenix-001-external-methods', '--not', '--remotes')[1])
print('local phoenix 26 shared commits (not on main, not unique):')
print(git('log', '--format=%h %s', 'research/phoenix-001-external-methods', '^origin/main',
          '^research/phoenix-001-external-methods~0', '--not', '--remotes')[1][:0] or '(see counts below)')
print('commit count vs main:', git('rev-list', '--count', 'origin/main..research/phoenix-001-external-methods')[1].strip())
