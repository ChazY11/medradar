#!/usr/bin/env python
"""Probe JSON/YAML state files and short docs on origin/main."""
import json, subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def cat(path):
    p = subprocess.run(['git', '-C', ROOT, 'show', f'origin/main:{path}'], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    return p.stdout if p.returncode == 0 else None


for path in ['research/STATE.json', 'research/AUDIT.json', 'research/FINAL_AUDIT.json',
             'papers/CLAIMS.json']:
    body = cat(path)
    print(f'\n=== {path} ===')
    if body is None:
        print('  MISSING'); continue
    try:
        d = json.loads(body)
        if isinstance(d, dict):
            print('  top keys:', list(d.keys())[:30])
            for k in list(d.keys())[:6]:
                v = d[k]
                print(f'   {k}: {json.dumps(v, ensure_ascii=False)[:220]}')
        else:
            print('  list len', len(d), json.dumps(d[0], ensure_ascii=False)[:300])
    except Exception as e:
        print('  parse fail', e, body[:300])

for path in ['research/BACKLOG.yaml', 'research/MISSION.md', 'research/ROADMAP.md',
             'config/sources.json', 'papers/README.md', 'verifier/README.md',
             'verifier/v1/criteria.md', 'ROADMAP.md', 'CONTRIBUTING.md', 'CHANGELOG.md',
             'research/DECISIONS.md', 'research/PREDICTION_PROTOCOL.md']:
    body = cat(path)
    print(f'\n=== {path} ({len(body.splitlines()) if body else 0} lines) ===')
    if body:
        print('\n'.join('  ' + x[:160] for x in body.splitlines()[:14]))
