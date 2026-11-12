#!/usr/bin/env python3
"""REFOUNDATION-001 ground-truth collector (read-only).

Produces repo_facts.json from live GitHub + local git. No writes to git state.
Run from anywhere:  python docs/refoundation/_evidence/collect_facts.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "repo_facts.json"


def run(args: list[str], **kw) -> str:
    p = subprocess.run(args, cwd=str(REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", **kw)
    if p.returncode != 0:
        raise RuntimeError(f"{args} failed: {p.stderr[:400]}")
    return p.stdout


def gh_json(args: list[str]):
    return json.loads(run(["gh"] + args))


def main() -> int:
    facts: dict = {"collected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    facts["repo"] = gh_json([
        "repo", "view", "ChazY11/medradar", "--json",
        "name,defaultBranchRef,isPrivate,diskUsage,stargazerCount,forkCount,"
        "hasIssuesEnabled,hasDiscussionsEnabled,hasWikiEnabled,licenseInfo,"
        "primaryLanguage,languages,createdAt,pushedAt,homepageUrl,description",
    ])

    facts["main_head"] = run(["git", "rev-parse", "origin/main"]).strip()
    facts["main_head_subject"] = run(["git", "log", "-1", "--format=%s", "origin/main"]).strip()
    facts["main_head_date"] = run(["git", "log", "-1", "--format=%cI", "origin/main"]).strip()

    prs = gh_json([
        "pr", "list", "--state", "all", "--limit", "200", "--json",
        "number,title,state,isDraft,headRefName,baseRefName,createdAt,updatedAt,"
        "mergedAt,closedAt,additions,deletions,changedFiles,author,url,body",
    ])
    for pr in prs:
        if isinstance(pr.get("author"), dict):
            pr["author"] = pr["author"].get("login")
    facts["pull_requests"] = sorted(prs, key=lambda p: p["number"])
    facts["pull_request_summary"] = {
        "total": len(prs),
        "merged": sum(1 for p in prs if p["state"] == "MERGED"),
        "open": sum(1 for p in prs if p["state"] == "OPEN"),
        "open_drafts": sum(1 for p in prs if p["state"] == "OPEN" and p["isDraft"]),
        "closed_unmerged": sum(1 for p in prs if p["state"] == "CLOSED"),
    }

    facts["issues"] = gh_json(["issue", "list", "--state", "all", "--limit", "200",
                               "--json", "number,title,state,createdAt,closedAt,labels"])
    try:
        facts["pages"] = gh_json(["api", "repos/ChazY11/medradar/pages"])
    except Exception as exc:  # noqa: BLE001
        facts["pages"] = {"error": str(exc)}

    refs = {}
    raw = run(["git", "for-each-ref", "refs/remotes/origin",
               "--format=%(refname:short)|%(objectname)|%(committerdate:iso-strict)"])
    for line in raw.splitlines():
        name, sha, date = line.split("|", 2)
        if name.endswith("/HEAD"):
            continue
        short = name.removeprefix("origin/")
        ahead = int(run(["git", "rev-list", "--count", f"origin/main..{name}"]).strip())
        behind = int(run(["git", "rev-list", "--count", f"{name}..origin/main"]).strip())
        refs[short] = {"sha": sha, "committed": date, "ahead_of_main": ahead,
                       "behind_main": behind}
    facts["remote_branches"] = refs

    local = {}
    raw = run(["git", "for-each-ref", "refs/heads", "--format=%(refname:short)|%(objectname)"])
    for line in raw.splitlines():
        name, sha = line.split("|", 1)
        upstream = ""
        try:
            upstream = run(["git", "rev-parse", "--abbrev-ref",
                            f"{name}@{{upstream}}"]).strip()
        except RuntimeError:
            upstream = ""
        # commits on this local branch not reachable from ANY remote ref
        unpushed = run(["git", "rev-list", "--count", name, "--not", "--remotes"]).strip()
        local[name] = {"sha": sha, "upstream": upstream,
                       "commits_not_on_any_remote": int(unpushed)}
    facts["local_branches"] = local

    tree = run(["git", "ls-tree", "-r", "--name-only", "origin/main"]).splitlines()
    facts["main_file_count"] = len(tree)

    sizes = run(["git", "ls-tree", "-r", "--format=%(objectsize) %(path)", "origin/main"])
    agg: dict[str, dict] = {}
    for line in sizes.splitlines():
        size_s, path = line.split(" ", 1)
        top = path.split("/", 1)[0]
        slot = agg.setdefault(top, {"files": 0, "bytes": 0})
        slot["files"] += 1
        slot["bytes"] += int(size_s)
    for slot in agg.values():
        slot["mb"] = round(slot["bytes"] / 1048576, 2)
    facts["main_tree_by_top_level"] = dict(
        sorted(agg.items(), key=lambda kv: kv[1]["bytes"], reverse=True))

    facts["worktrees"] = [
        dict(zip(("path", "head", "branch"), line.split("\t") if "\t" in line
                 else [line, "", ""]))
        for line in run(["git", "worktree", "list"]).splitlines()
    ]

    OUT.write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(json.dumps(facts["pull_request_summary"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
