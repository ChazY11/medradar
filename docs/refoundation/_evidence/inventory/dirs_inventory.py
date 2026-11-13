#!/usr/bin/env python
"""Directory-level listing for origin/main tree roots (dirs aggregated recursively)."""
import subprocess, sys

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
out = subprocess.run(['git', '-C', ROOT, 'ls-tree', '-r', '-l', 'origin/main'],
                     capture_output=True, text=True, encoding='utf-8').stdout
tree = []
for ln in out.splitlines():
    if not ln.strip():
        continue
    meta, path = ln.split('\t', 1)
    p = meta.split()
    tree.append({'path': path, 'size': int(p[3]) if p[3].isdigit() else 0})

roots = sys.argv[1:] or ['experiments', 'research', 'papers', 'docs', 'config', 'verifier',
                         'tools', 'scripts', '.github', 'tests']
for r in roots:
    print(f"\n===== {r} =====")
    items = [e for e in tree if e['path'].startswith(r + '/')]
    direct = sorted([e for e in items if e['path'].count('/') == 1], key=lambda e: -e['size'])
    dirs = {}
    for e in items:
        segs = e['path'].split('/')
        if len(segs) < 3:
            continue
        k = segs[1]
        dirs.setdefault(k, {'files': 0, 'bytes': 0})
        dirs[k]['files'] += 1
        dirs[k]['bytes'] += e['size']
    for k, v in sorted(dirs.items(), key=lambda kv: -kv[1]['bytes']):
        print(f"  DIR  {k:44s} {v['files']:5d}f {v['bytes']:9d}b")
    for e in direct:
        print(f"  FILE {e['path'][len(r) + 1:]:52s} {e['size']:9d}")
