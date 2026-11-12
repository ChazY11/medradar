import json

f = json.load(open('docs/refoundation/_evidence/repo_facts.json', encoding='utf-8'))
prs = f['pull_requests']
print('| PR | State | Draft | Base | Head | Merged | Files | +/- | Title |')
print('|---|---|---|---|---|---|---|---|---|')
for p in prs:
    m = (p['mergedAt'] or '')[:10] or '-'
    title = p['title'].replace('|', '\\|')[:72]
    print(f"| #{p['number']} | {p['state']} | {'yes' if p['isDraft'] else 'no'} | "
          f"{p['baseRefName']} | {p['headRefName']} | {m} | {p['changedFiles']} | "
          f"+{p['additions']}/-{p['deletions']} | {title} |")
print()
print('OPEN total additions:', sum(p['additions'] for p in prs if p['state'] == 'OPEN'))
print('MERGED total additions:', sum(p['additions'] for p in prs if p['state'] == 'MERGED'))
