#!/usr/bin/env python
"""True delta of the two deceptive PRs: #22 vs #21, #30 vs #29 (and #30 vs atlas)."""
import subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


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


PAIRS = [
    ('#22 true delta vs #21', 'origin/research/innovation-signals-observatory',
     'origin/research/s031-hiring-capability-study'),
    ('#21 true delta vs phase4-base', 'origin/integration/phase4-base',
     'origin/research/innovation-signals-observatory'),
    ('#30 true delta vs #29', 'origin/research/horizon-001', 'origin/integration/convergence-001'),
    ('#30 true delta vs #28', 'origin/foundation/atlas-001', 'origin/integration/convergence-001'),
    ('#15 delta vs #14', 'origin/feat/observatory-reliability-v1',
     'origin/research/s028-temporal-graph-early-signal'),
    ('#16 delta vs #14', 'origin/feat/observatory-reliability-v1',
     'origin/research/s029-evidence-based-relations'),
    ('#25 delta vs #24', 'origin/research/phoenix-001-round2',
     'origin/research/phoenix-002-h8-validation'),
]
for label, a, b in PAIRS:
    f, ad, de = numstat(a, b)
    print(f'{label:34s} files={f:4d} +{ad:7d}/-{de:5d}')

# commit counts vs declared base
COMMITS = [
    ('#13', 'origin/feat/medradar-2.0-mvp', 'origin/feat/live-observatory-v1'),
    ('#14', 'origin/feat/live-observatory-v1', 'origin/feat/observatory-reliability-v1'),
    ('#15', 'origin/feat/observatory-reliability-v1', 'origin/research/s028-temporal-graph-early-signal'),
    ('#16', 'origin/feat/observatory-reliability-v1', 'origin/research/s029-evidence-based-relations'),
    ('#20', 'origin/research/local-llm-foundation', 'origin/research/overnight-qlora-s030'),
    ('#21', 'origin/integration/phase4-base', 'origin/research/innovation-signals-observatory'),
    ('#25', 'origin/research/phoenix-001-round2', 'origin/research/phoenix-002-h8-validation'),
]
print('\ncommits vs declared base:')
for label, a, b in COMMITS:
    n = git('rev-list', '--count', f'{a}..{b}').strip()
    print(f'  {label} {n} commits')
