#!/usr/bin/env python
"""Precise blob-variant check for version-bearing files across main + all open-PR heads."""
import subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
heads = ['feat/frontier-device-radar', 'feat/medradar-2.0-mvp', 'feat/live-observatory-v1',
         'feat/observatory-reliability-v1', 'research/s028-temporal-graph-early-signal',
         'research/s029-evidence-based-relations', 'maintenance/repository-consolidation',
         'research/ai-evidence-review', 'research/local-llm-foundation',
         'research/overnight-qlora-s030', 'research/innovation-signals-observatory',
         'research/s031-hiring-capability-study', 'research/phoenix-001-external-methods',
         'research/phoenix-001-round2', 'research/phoenix-002-h8-validation',
         'research/phoenix-003-early-evidence', 'research/data-expansion-001',
         'foundation/atlas-001', 'research/horizon-001', 'integration/convergence-001']


def blob(ref, path):
    p = subprocess.run(['git', '-C', ROOT, 'rev-parse', f'{ref}:{path}'],
                       capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


for path in ['README.md', 'pyproject.toml', 'CHANGELOG.md']:
    print(f'\n=== {path} ===')
    seen = {}
    for b in ['main'] + heads:
        ref = 'origin/main' if b == 'main' else 'origin/' + b
        sha = blob(ref, path)
        print(f"  {b:44s} {(sha or 'MISSING')[:12]}")
        if sha:
            seen.setdefault(sha, []).append(b)
    print(f'  DISTINCT: {len(seen)}')
    for sha, brs in seen.items():
        print(f'    {sha[:12]} x{len(brs)}')
