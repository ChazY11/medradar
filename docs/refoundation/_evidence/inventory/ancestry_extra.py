#!/usr/bin/env python
"""Targeted ancestry + PR#1 net-new verification."""
import subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def run(*a):
    return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def anc(a, b):
    return run('merge-base', '--is-ancestor', a, b).returncode == 0


PAIRS = [
    ('origin/feat/medradar-2.0-mvp', 'origin/integration/phase4-base'),
    ('origin/feat/observatory-reliability-v1', 'origin/integration/phase4-base'),
    ('origin/research/s028-temporal-graph-early-signal', 'origin/research/s029-evidence-based-relations'),
    ('origin/research/innovation-signals-observatory', 'origin/research/s031-hiring-capability-study'),
    ('origin/research/horizon-001', 'origin/integration/convergence-001'),
    ('origin/foundation/atlas-001', 'origin/integration/convergence-001'),
    ('origin/main', 'origin/feat/frontier-device-radar'),
    ('origin/research/phoenix-001-round2', 'origin/research/phoenix-002-h8-validation'),
    ('origin/research/local-llm-foundation', 'origin/research/overnight-qlora-s030'),
    ('origin/integration/phase4-base', 'origin/research/innovation-signals-observatory'),
]
print('=== ANCESTRY ===')
for a, b in PAIRS:
    print(f'  {a:52s} ancestor of {b:52s} : {"YES" if anc(a, b) else "no"}')

print('\n=== PR #1 added paths: on main already? ===')
out = run('diff', '--name-status', 'origin/main...origin/feat/frontier-device-radar').stdout
net_new = []
for ln in out.splitlines():
    p = ln.split('\t')
    if p[0] == 'A':
        exists = run('cat-file', '-e', 'origin/main:' + p[-1]).returncode == 0
        print(f"  {'ON-MAIN' if exists else 'NET-NEW'}  {p[-1]}")
        if not exists:
            net_new.append(p[-1])
print('  net-new count:', len(net_new))

print('\n=== PR #1 modifications: which files differ ===')
for ln in out.splitlines():
    p = ln.split('\t')
    if p[0] != 'A':
        print('  ', ln)
