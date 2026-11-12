#!/usr/bin/env python
"""For each branch-only family, list the top-level and second-level directories it adds vs main."""
import subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def git(*a):
    return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stdout


def added(ref):
    out = []
    for ln in git('diff', '--name-status', 'origin/main...' + ref).splitlines():
        p = ln.split('\t')
        if p and p[0] == 'A' and len(p) > 1:
            out.append(p[-1])
    return out


BRANCHES = [
    'research/s028-temporal-graph-early-signal',
    'research/s029-evidence-based-relations',
    'research/s031-hiring-capability-study',
    'research/innovation-signals-observatory',
    'research/horizon-001',
    'foundation/atlas-001',
    'integration/convergence-001',
    'research/data-expansion-001',
    'research/local-llm-foundation',
    'research/overnight-qlora-s030',
    'research/phoenix-001-external-methods',
    'research/phoenix-001-round2',
    'research/phoenix-002-h8-validation',
    'research/phoenix-003-early-evidence',
    'research/early-signal-ai-review',
    'research/full-history-v1',
    'feat/medradar-2.0-mvp',
    'feat/live-observatory-v1',
    'feat/observatory-reliability-v1',
    'maintenance/repository-consolidation',
    'research/ai-evidence-review',
]

for b in BRANCHES:
    a = added('origin/' + b)
    dirs = {}
    for p in a:
        segs = p.split('/')
        key = '/'.join(segs[:2]) if len(segs) > 2 else p
        dirs[key] = dirs.get(key, 0) + 1
    print(f"\n=== {b}  (+{len(a)} files) ===")
    for k, v in sorted(dirs.items(), key=lambda kv: -kv[1])[:18]:
        print(f"   {k:60s} {v:5d}")
