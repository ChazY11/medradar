#!/usr/bin/env python
"""Final precision checks: exact conflict set for PR #1; phoenix commit containment."""
import subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def git(*a):
    return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


p = git('merge-tree', '--write-tree', 'origin/main', 'origin/feat/frontier-device-radar')
paths = set()
for ln in p.stdout.splitlines():
    if ln.startswith('CONFLICT'):
        # "CONFLICT (content): Merge conflict in <path>" or "...(modify/delete): <path> deleted in ..."
        if 'Merge conflict in ' in ln:
            paths.add(ln.split('Merge conflict in ', 1)[1])
        elif '): ' in ln:
            rest = ln.split('): ', 1)[1]
            paths.add(rest.split(' ')[0])
print('PR#1 conflicted paths:', len(paths))
for x in sorted(paths):
    print('  ', x)

print('\nphoenix local commits:')
total = int(git('rev-list', '--count', 'research/phoenix-001-external-methods').stdout.strip())
not_round2 = int(git('rev-list', '--count', 'research/phoenix-001-external-methods',
                     '^origin/research/phoenix-001-round2').stdout.strip())
not_any_remote = len([l for l in git('log', '--oneline', 'research/phoenix-001-external-methods',
                                     '--not', '--remotes').stdout.splitlines() if l.strip()])
print('  total commits on local branch:', total)
print('  not in origin/research/phoenix-001-round2:', not_round2)
print('  not in any remote:', not_any_remote)

print('\nremote twin containment:')
for ref in ['origin/research/phoenix-001-round2', 'origin/research/phoenix-001-external-methods']:
    n = int(git('rev-list', '--count', 'research/phoenix-001-external-methods', '^' + ref).stdout.strip())
    print(f'  local commits not in {ref}:', n)
