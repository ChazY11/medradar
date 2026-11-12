"""Ancestry matrix: which unmerged stack does each branch actually contain?

The PR `base` metadata says one thing; git ancestry says another. This script
reports, for each remote branch, whether selected stack bases are ancestors.
Used to distinguish legitimate stack inheritance from true copy-paste.

Read-only.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "ancestry.json"

BASES = [
    "feat/medradar-2.0-mvp",
    "feat/live-observatory-v1",
    "feat/observatory-reliability-v1",
    "foundation/atlas-001",
    "research/horizon-001",
    "integration/phase4-base",
]


def is_ancestor(a: str, b: str) -> bool:
    p = subprocess.run(["git", "merge-base", "--is-ancestor", a, b],
                       cwd=str(REPO), capture_output=True)
    return p.returncode == 0


def main() -> int:
    raw = subprocess.run(["git", "for-each-ref", "refs/remotes/origin",
                          "--format=%(refname:short)"], cwd=str(REPO),
                         capture_output=True, text=True).stdout
    branches = sorted(x.removeprefix("origin/") for x in raw.splitlines()
                      if x.strip() and not x.endswith("/HEAD") and x != "origin")
    matrix = {}
    for b in branches:
        matrix[b] = {base: is_ancestor(f"origin/{base}", f"origin/{b}")
                     for base in BASES}
    OUT.write_text(json.dumps({"bases": BASES, "matrix": matrix}, indent=2),
                   encoding="utf-8")

    print(f"{'branch':54s} " + " ".join(f"{i}" for i in range(len(BASES))))
    for i, b in enumerate(BASES):
        print(f"  {i} = {b}")
    print()
    for b in branches:
        cells = " ".join("Y" if matrix[b][base] else "." for base in BASES)
        if any(matrix[b].values()) or b == "main":
            print(f"{b:54s} {cells}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
