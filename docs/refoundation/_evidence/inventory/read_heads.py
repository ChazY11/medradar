#!/usr/bin/env python
"""Extract module docstrings / headers from origin/main blobs for inventory purposes."""
import subprocess, sys

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def show(ref, path, n=6):
    p = subprocess.run(['git', '-C', ROOT, 'show', f'{ref}:{path}'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode != 0:
        print(f'--- {path}: MISSING on {ref}')
        return
    body = p.stdout.splitlines()
    print(f'\n--- {path} ({len(body)} lines)')
    # print shebang/blank-skipped head
    shown = 0
    for ln in body:
        print('   ' + ln[:150])
        shown += 1
        if shown >= n:
            break


targets = sys.argv[1:]
for t in targets:
    show('origin/main', t, 5)
