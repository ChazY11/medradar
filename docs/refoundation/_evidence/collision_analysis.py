"""Cross-branch change-surface collision analysis (read-only).

For a set of branches, compute which paths each one adds/modifies relative to
origin/main, then report (a) per-branch top-level footprint, (b) pairwise
overlap of touched paths, (c) paths touched by 3+ branches.

This measures *fragmentation*, not semantic duplication: a shared path means
two branches are editing the same file, which is where merge conflict and
doc drift originate.
"""
from __future__ import annotations

import json
import subprocess
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "collisions.json"

BRANCHES = [
    "feat/medradar-2.0-mvp",
    "feat/live-observatory-v1",
    "feat/observatory-reliability-v1",
    "research/s028-temporal-graph-early-signal",
    "research/s029-evidence-based-relations",
    "maintenance/repository-consolidation",
    "research/ai-evidence-review",
    "research/local-llm-foundation",
    "research/overnight-qlora-s030",
    "research/innovation-signals-observatory",
    "research/s031-hiring-capability-study",
    "research/phoenix-001-external-methods",
    "research/phoenix-001-round2",
    "research/phoenix-002-h8-validation",
    "research/phoenix-003-early-evidence",
    "research/data-expansion-001",
    "foundation/atlas-001",
    "research/horizon-001",
    "integration/convergence-001",
]


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:300])
    return p.stdout


def main() -> int:
    touched: dict[str, set[str]] = {}
    for b in BRANCHES:
        raw = git("diff", "--name-only", f"origin/main...origin/{b}")
        touched[b] = {line for line in raw.splitlines() if line.strip()}

    result: dict = {"branches": BRANCHES, "per_branch": {}, "pairwise": [],
                    "multi_branch_paths": []}

    for b, paths in touched.items():
        tops: dict[str, int] = {}
        for p in paths:
            top = p.split("/", 1)[0]
            tops[top] = tops.get(top, 0) + 1
        result["per_branch"][b] = {
            "touched_paths": len(paths),
            "top_level": dict(sorted(tops.items(), key=lambda kv: -kv[1])[:12]),
        }

    for a, b in combinations(BRANCHES, 2):
        inter = touched[a] & touched[b]
        # ignore trivially shared generated dirs for the headline number
        substantive = {p for p in inter
                       if not p.startswith(("experiments/", "docs/", "research/RESULTS/"))}
        if substantive:
            result["pairwise"].append({
                "a": a, "b": b, "shared_paths": len(inter),
                "shared_substantive": len(substantive),
                "examples": sorted(substantive)[:8],
            })

    owners: dict[str, list[str]] = {}
    for b, paths in touched.items():
        for p in paths:
            owners.setdefault(p, []).append(b)
    multi = {p: bs for p, bs in owners.items() if len(bs) >= 3}
    result["multi_branch_paths"] = [
        {"path": p, "branches": sorted(bs)} for p, bs in
        sorted(multi.items(), key=lambda kv: -len(kv[1]))
    ]

    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")

    print("\n== touched paths per branch ==")
    for b in BRANCHES:
        n = result["per_branch"][b]["touched_paths"]
        print(f"{n:6d}  {b}")

    print("\n== highest-overlap pairs (substantive) ==")
    for row in sorted(result["pairwise"], key=lambda r: -r["shared_substantive"])[:15]:
        print(f"{row['shared_substantive']:5d}  {row['a']}  <->  {row['b']}")

    print("\n== paths touched by 3+ branches ==")
    for row in result["multi_branch_paths"][:30]:
        print(f"{len(row['branches']):3d}  {row['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
