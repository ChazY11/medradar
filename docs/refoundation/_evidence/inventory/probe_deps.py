#!/usr/bin/env python
"""Small targeted checks: package metadata, clinical.py, env-var dependencies."""
import re, subprocess

ROOT = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()


def show(path, n=12):
    p = subprocess.run(['git', '-C', ROOT, 'show', f'origin/main:{path}'], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    print(f'\n--- {path}')
    print('\n'.join('   ' + x[:150] for x in p.stdout.splitlines()[:n]))
    return p.stdout


show('medradar/__init__.py', 21)
show('medradar/clinical.py', 8)
show('medradar/__main__.py', 12)

for path in ['medradar/llm.py', 'medradar/http.py', 'medradar/config.py', 'medradar/prices.py',
             'medradar/db.py']:
    body = show(path, 0)
    envs = sorted(set(re.findall(r'(?:environ\.get|environ\[|getenv)\(\s*[\'"]([A-Z0-9_]+)[\'"]', body)))
    urls = sorted(set(re.findall(r'https?://[A-Za-z0-9./_-]+', body)))
    print('   ENV:', envs, '| URLs:', urls[:6])
