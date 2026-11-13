#!/usr/bin/env python
"""Independent verification of ancestry and copy-paste claims for BRANCH_PR_AUDIT.

Read-only. Writes ancestry_verify.json into this evidence directory.
Verifies (does not trust) the peer-supplied _evidence/ancestry.json / copy_volume.json.
"""
import json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
OUT = os.path.join(HERE, 'ancestry_verify.json')


def git(*a):
    return subprocess.run(['git', '-C', ROOT] + list(a), capture_output=True, text=True,
                          encoding='utf-8', errors='replace').stdout


def is_anc(anc, desc):
    return subprocess.run(['git', '-C', ROOT, 'merge-base', '--is-ancestor', anc, desc],
                          capture_output=True).returncode == 0


def head(branch):
    return 'origin/' + branch


PRODUCT = ['feat/medradar-2.0-mvp', 'feat/live-observatory-v1', 'feat/observatory-reliability-v1']
HEADS = {
    'feat/frontier-device-radar': 1, 'feat/medradar-2.0-mvp': 12, 'feat/live-observatory-v1': 13,
    'feat/observatory-reliability-v1': 14, 'research/s028-temporal-graph-early-signal': 15,
    'research/s029-evidence-based-relations': 16, 'maintenance/repository-consolidation': 17,
    'research/ai-evidence-review': 18, 'research/local-llm-foundation': 19,
    'research/overnight-qlora-s030': 20, 'research/innovation-signals-observatory': 21,
    'research/s031-hiring-capability-study': 22, 'research/phoenix-001-external-methods': 23,
    'research/phoenix-001-round2': 24, 'research/phoenix-002-h8-validation': 25,
    'research/phoenix-003-early-evidence': 26, 'research/data-expansion-001': 27,
    'foundation/atlas-001': 28, 'research/horizon-001': 29, 'integration/convergence-001': 30,
}
STACK = PRODUCT + ['integration/phase4-base']

data = {'generated_by': 'docs/refoundation/_evidence/inventory/verify_ancestry.py'}

# ---- 1. which open-PR heads contain which base branch (ancestry, not diff) ----
mat = {}
for br in HEADS:
    row = {}
    for b in STACK + ['foundation/atlas-001', 'research/horizon-001']:
        try:
            row[b] = is_anc(head(b), head(br))
        except Exception:
            row[b] = None
    mat[br] = row
data['contains_ancestor'] = mat

# ---- 2. blob identity: added-vs-main files that already exist byte-identically elsewhere ----
def tree_blobs(ref):
    out = {}
    for ln in git('ls-tree', '-r', ref).splitlines():
        if not ln.strip():
            continue
        meta, path = ln.split('\t', 1)
        out[path] = meta.split()[2]
    return out


def added(ref):
    out = []
    for ln in git('diff', '--name-status', 'origin/main...' + ref).splitlines():
        p = ln.split('\t')
        if p and p[0] == 'A' and len(p) > 1:
            out.append(p[-1])
    return out


main_blobs = tree_blobs('origin/main')
copy = []
for br, pr in HEADS.items():
    added_paths = added(head(br))
    if not added_paths:
        continue
    mine = tree_blobs(head(br))
    rec = {'pr': pr, 'branch': br, 'added_vs_main': len(added_paths), 'identical_to': {}}
    for other in HEADS:
        if other == br:
            continue
        ob = tree_blobs(head(other))
        same = [p for p in added_paths if p in mine and p in ob and mine[p] == ob[p]]
        if len(same) >= 10:
            rec['identical_to'][other] = {'count': len(same),
                                          'pct': round(100.0 * len(same) / len(added_paths), 1),
                                          'examples': same[:5]}
    copy.append(rec)
data['copy_identity'] = copy

# ---- 3. blob variants for version-bearing files across all branches ----
variants = {}
for f in ['README.md', 'pyproject.toml', 'CHANGELOG.md', 'README.zh-CN.md']:
    seen = {}
    refs = ['origin/main'] + [head(b) for b in HEADS]
    for r in refs:
        sha = git('rev-parse', f'{r}:{f}').strip()
        if sha:
            seen.setdefault(sha, []).append(r.replace('origin/', ''))
    variants[f] = {sha: v for sha, v in seen.items()}
data['blob_variants'] = variants

# ---- 4. PR #1 ancestry / divergence detail ----
data['pr1'] = {
    'behind_main': git('rev-list', '--count', 'origin/feat/frontier-device-radar..origin/main').strip(),
    'ahead_main': git('rev-list', '--count', 'origin/main..origin/feat/frontier-device-radar').strip(),
    'merge_base': git('merge-base', 'origin/main', 'origin/feat/frontier-device-radar').strip(),
    'touches_frontier_on_main': 'medradar/frontier.py' in main_blobs,
}

# ---- 5. no-PR branches: are they ancestors of main? ----
nopr = {}
for b in ['integration/phase4-base', 'research/cycle2-coverage-power',
          'research/early-signal-ai-review', 'research/full-history-v1']:
    nopr[b] = {'ancestor_of_main': is_anc(head(b), 'origin/main'),
               'ahead': int(git('rev-list', '--count', 'origin/main..' + head(b)).strip())}
data['branches_without_pr'] = nopr

json.dump(data, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('wrote', OUT, os.path.getsize(OUT), 'bytes')
for p in ['pr1', 'branches_without_pr']:
    print(p, json.dumps(data[p], ensure_ascii=False))
