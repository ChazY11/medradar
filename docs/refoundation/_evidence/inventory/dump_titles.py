#!/usr/bin/env python
"""Dump full PR titles/dates, branch tip dates, and worktree list for the audit doc."""
import json

FACTS = 'docs/refoundation/_evidence/repo_facts.json'
d = json.load(open(FACTS, encoding='utf-8'))

print('=== OPEN PR TITLES ===')
for p in d['pull_requests']:
    if p['state'] == 'OPEN':
        print(f"#{p['number']:>2} | {p['createdAt']} | {p['updatedAt']} | {p['headRefName']}")
        print(f"     {p['title']}")

print('\n=== BRANCH TIPS ===')
for b, v in d['remote_branches'].items():
    print(f"  {b:48s} {v['committed']}  {v['sha'][:10]}")

print('\n=== WORKTREES ===')
for w in d['worktrees']:
    print('  ', w['path'])
