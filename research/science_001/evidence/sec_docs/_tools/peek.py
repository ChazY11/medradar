
import json
base = r"D:\DEPPSKK\worktrees\science-001\research\science_001\evidence\sec_docs"
f = open(base + r"\raw\fts-api.json", encoding="utf-8").read()
print("fts len:", len(f), "has file_date lit:", '"file_date":"2024-11-01"' in f, "| with space:", '"file_date": "2024-11-01"' in f)
i = f.find('"file_date"')
print("fts excerpt:", f[i-80:i+120])
s = open(base + r"\raw\submissions-json-CIK0000064670.json", encoding="utf-8").read()
print()
print("subs len:", len(s), 'has 2015-02-17T12:18:53.000Z:', '"2015-02-17T12:18:53.000Z"' in s)
i = s.find("2015-02-17T12:18:53.000Z")
print("subs excerpt:", s[i-200:i+60])
