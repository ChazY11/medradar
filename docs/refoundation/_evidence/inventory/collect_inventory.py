#!/usr/bin/env python
"""REFOUNDATION-001 inventory evidence collector (read-only git inspection).

Writes docs/refoundation/_evidence/inventory/inventory_facts.json with:
  main_tree        : every blob on origin/main with size
  top_level        : per-top-level file/size aggregation
  sub_trees        : per-directory aggregation for selected roots
  branches         : divergence + diffstat for every remote branch
  prs              : PR ledger from repo_facts.json + computed head/base checks
  local_branches   : divergence + commits on no remote
  branch_trees     : top-level + notable new paths for each open-PR head
  medradar_files   : path/bytes/lines for medradar/**
  cli              : subcommands parsed from medradar/__main__.py
  tests            : test module list
  config           : config inventory
  workflows        : .github/workflows inventory
"""
import json, os, subprocess, sys, re

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..'))
# script lives at docs/refoundation/_evidence/inventory/ ; repo root is 4 levels up from it
OUT = os.path.join(ROOT, 'docs', 'refoundation', '_evidence', 'inventory', 'inventory_facts.json')
FACTS = os.path.join(ROOT, 'docs', 'refoundation', '_evidence', 'repo_facts.json')


def git(*args, check=True):
    p = subprocess.run(['git', '-C', ROOT] + list(args), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if check and p.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} failed: {p.stderr}')
    return p.stdout


def lines(s):
    return [x for x in s.splitlines() if x.strip()]


def tree_of(ref):
    """Return list of dicts: mode,type,sha,size,path from git ls-tree -r -l."""
    out = []
    for ln in lines(git('ls-tree', '-r', '-l', ref)):
        meta, path = ln.split('\t', 1)
        parts = meta.split()
        mode, typ, sha, size = parts[0], parts[1], parts[2], parts[3]
        out.append({'mode': mode, 'type': typ, 'sha': sha,
                    'size': int(size) if size.isdigit() else 0, 'path': path})
    return out


def agg(tree, depth):
    a = {}
    for e in tree:
        segs = e['path'].split('/')
        key = '/'.join(segs[:depth]) if len(segs) > depth else segs[0]
        d = a.setdefault(key, {'files': 0, 'bytes': 0})
        d['files'] += 1
        d['bytes'] += e['size']
    return dict(sorted(a.items(), key=lambda kv: -kv[1]['bytes']))


def diffstat(a, b):
    out = git('diff', '--numstat', f'{a}...{b}')
    files = adds = dels = 0
    for ln in lines(out):
        p = ln.split('\t')
        if len(p) < 3:
            continue
        files += 1
        if p[0].isdigit():
            adds += int(p[0])
        if p[1].isdigit():
            dels += int(p[1])
    return {'files': files, 'additions': adds, 'deletions': dels}


def ahead_behind(branch, base='origin/main'):
    """ahead = commits only on `branch`; behind = commits only on base.

    git rev-list --left-right --count A...B prints "<left-only>\\t<right-only>",
    so left-only (base-only) is *behind* and right-only (branch-only) is *ahead*.
    """
    left, right = lines(git('rev-list', '--left-right', '--count', f'{base}...{branch}'))[0].split('\t')
    return {'ahead': int(right), 'behind': int(left)}


def merge_check(base, head):
    """Read-only 3-way merge probe. Returns whether they merge cleanly + conflicted paths."""
    p = subprocess.run(['git', '-C', ROOT, 'merge-tree', '--write-tree', base, head],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if p.returncode == 0:
        return {'clean': True, 'conflicts': []}
    conflicts = [ln.split('\t')[-1] for ln in lines(p.stdout) if ln.startswith('CONFLICT')]
    return {'clean': False, 'exit': p.returncode, 'conflicts': conflicts[:40],
            'stderr_tail': '\n'.join(p.stderr.splitlines()[-5:])}


def name_status(a, b):
    out = git('diff', '--name-status', f'{a}...{b}')
    res = []
    for ln in lines(out):
        p = ln.split('\t')
        res.append({'status': p[0], 'path': p[-1]})
    return res


def main():
    facts = json.load(open(FACTS, encoding='utf-8'))
    data = {'generated_by': 'docs/refoundation/_evidence/inventory/collect_inventory.py'}

    # ---- A. main tree ----
    tree = tree_of('origin/main')
    data['main_file_count'] = len(tree)
    data['main_total_bytes'] = sum(e['size'] for e in tree)
    data['top_level'] = agg(tree, 1)
    roots = ['medradar', 'experiments', 'research', 'tests', 'docs', 'config',
             'papers', 'verifier', 'tools', 'scripts', '.github']
    data['sub_trees'] = {r: agg([e for e in tree if e['path'].startswith(r + '/')], len(r.split('/')) + 2)
                         for r in roots}

    # medradar file detail with line counts
    med = []
    for e in tree:
        if not e['path'].startswith('medradar/'):
            continue
        if e['path'].endswith('.py'):
            body = git('show', f'origin/main:{e["path"]}')
            nlines = body.count('\n') + (0 if body.endswith('\n') else 1)
        else:
            nlines = None
        med.append({'path': e['path'], 'bytes': e['size'], 'lines': nlines})
    data['medradar_files'] = med

    # ---- B. branches ----
    rb = list(facts['remote_branches'].keys())
    branches = {}
    for b in rb:
        ref = f'origin/{b}' if b != 'origin' else 'origin/main'
        subj = lines(git('log', '-1', '--format=%s', ref))
        branches[b] = {
            'sha': git('rev-parse', ref).strip(),
            'tip_subject': subj[0] if subj else '',
            'tip_date': git('log', '-1', '--format=%cI', ref).strip(),
            **ahead_behind(ref),
            'diffstat_vs_main': diffstat('origin/main', ref),
        }
    data['branches'] = branches
    data['branch_counts'] = {
        'remote_branch_refs': len([b for b in rb if b not in ('origin', 'main')]),
        'pr_heads': len({p['headRefName'] for p in facts['pull_requests']}),
        'remote_branches_without_pr': sorted(
            set(b for b in rb if b not in ('origin', 'main'))
            - {p['headRefName'] for p in facts['pull_requests']}),
        'pr_heads_without_remote_branch': sorted(
            {p['headRefName'] for p in facts['pull_requests']} - set(rb)),
    }

    # ---- C. PRs ----
    prs = []
    for p in facts['pull_requests']:
        head = 'origin/' + p['headRefName']
        base = 'origin/' + p['baseRefName']
        rec = {k: p[k] for k in ('number', 'state', 'isDraft', 'baseRefName', 'headRefName',
                                 'title', 'additions', 'deletions', 'changedFiles',
                                 'createdAt', 'mergedAt', 'url')}
        rec['head_sha'] = git('rev-parse', head).strip() if subprocess.run(
            ['git', '-C', ROOT, 'rev-parse', '--verify', '--quiet', head]).returncode == 0 else None
        rec['base_sha'] = git('rev-parse', base).strip() if subprocess.run(
            ['git', '-C', ROOT, 'rev-parse', '--verify', '--quiet', base]).returncode == 0 else None
        rec['base_is_main'] = p['baseRefName'] == 'main'
        try:
            rec['base_ahead_behind_main'] = ahead_behind(base)
        except Exception:
            rec['base_ahead_behind_main'] = None
        try:
            rec['merged_into_main'] = subprocess.run(
                ['git', '-C', ROOT, 'merge-base', '--is-ancestor', head, 'origin/main']).returncode == 0
        except Exception:
            rec['merged_into_main'] = None
        if p['state'] == 'OPEN':
            rec['merge_probe_main'] = merge_check('origin/main', head)
            rec['merge_probe_declared_base'] = merge_check(base, head)
        prs.append(rec)
    data['prs'] = prs

    # ---- D. local branches ----
    locals_ = []
    for ln in lines(git('for-each-ref', '--format=%(refname:short)', 'refs/heads')):
        try:
            ab = ahead_behind(ln)
        except Exception:
            ab = None
        notremote = lines(git('log', '--format=%H', ln, '--not', '--remotes'))
        locals_.append({'name': ln, 'sha': git('rev-parse', ln).strip(),
                        'upstream': git('rev-parse', '--abbrev-ref', f'{ln}@{{u}}', check=False).strip(),
                        **({'ahead': ab['ahead'], 'behind': ab['behind']} if ab else {}),
                        'commits_on_no_remote': len(notremote)})
    data['local_branches'] = locals_

    # ---- E. branch-top-level trees for open PR heads ----
    bt = {}
    for p in facts['pull_requests']:
        if p['state'] != 'OPEN':
            continue
        head = 'origin/' + p['headRefName']
        try:
            t = tree_of(head)
        except Exception:
            continue
        ns = name_status('origin/main', head)
        added = [x for x in ns if x['status'] == 'A']
        bt[p['headRefName']] = {
            'pr': p['number'],
            'files': len(t),
            'bytes': sum(e['size'] for e in t),
            'top_level': agg(t, 1),
            'added_top_dirs': agg([e for e in t if e['path'] in {x['path'] for x in added}], 2),
            'root_new': sorted({x['path'].split('/')[0] for x in added}),
            'notable_added': sorted([x['path'] for x in added if x['path'].count('/') <= 2])[:120],
        }
    data['branch_trees'] = bt

    # ---- F. CLI subcommands ----
    mainpy = git('show', 'origin/main:medradar/__main__.py')
    subs = re.findall(r"add_parser\(\s*[\"']([a-z0-9_-]+)[\"']", mainpy)
    if not subs:
        subs = re.findall(r"subparsers\.add_parser\(\s*[\"']([^\"']+)", mainpy)
    data['cli'] = {'__main___bytes': len(mainpy.encode()),
                   'add_parser_subcommands': sorted(set(subs)),
                   'pyproject': git('show', 'origin/main:pyproject.toml')}

    # ---- G. tests ----
    tests = []
    for e in tree:
        if e['path'].startswith('tests/') and e['path'].endswith('.py'):
            body = git('show', f'origin/main:{e["path"]}')
            testdefs = re.findall(r'^\s*def (test_\w+)', body, re.M)
            tests.append({'path': e['path'], 'bytes': e['size'], 'test_count': len(testdefs)})
    data['tests'] = tests

    # ---- H. config / workflows ----
    data['config'] = [{'path': e['path'], 'bytes': e['size']} for e in tree if e['path'].startswith('config/')]
    data['workflows'] = [{'path': e['path'], 'bytes': e['size']} for e in tree
                         if e['path'].startswith('.github/')]

    json.dump(data, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('wrote', OUT, os.path.getsize(OUT), 'bytes')


if __name__ == '__main__':
    main()
