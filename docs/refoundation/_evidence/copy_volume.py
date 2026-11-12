"""Quantify copy-paste contamination between branches (read-only).

For each (source, target) pair, count files that target introduces relative to
main and that already exist byte-identically in source. High counts mean the
target branch is carrying another branch's unmerged code as a copy, which is
the mechanism behind the repo's fragmentation.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "copy_volume.json"

PAIRS = [
    # target branch, comparison branch(es) it may have copied from
    ("research/s031-hiring-capability-study", ["feat/observatory-reliability-v1"]),
    ("research/innovation-signals-observatory", ["feat/observatory-reliability-v1"]),
    ("research/s029-evidence-based-relations", ["medradar-2.0"]),  # placeholder, handled below
    ("integration/convergence-001", ["foundation/atlas-001", "research/horizon-001"]),
    ("research/s028-temporal-graph-early-signal", ["feat/observatory-reliability-v1"]),
]
PAIRS[2] = ("research/s029-evidence-based-relations", ["feat/observatory-reliability-v1"])


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.stdout if p.returncode == 0 else ""


def blob(ref: str, path: str) -> str | None:
    p = subprocess.run(["git", "rev-parse", f"{ref}:{path}"], cwd=str(REPO),
                       capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def added_paths(branch: str) -> list[str]:
    raw = git("diff", "--name-only", "--diff-filter=A",
              f"origin/main...origin/{branch}")
    return [x for x in raw.splitlines() if x.strip()]


def main() -> int:
    results = []
    for target, sources in PAIRS:
        paths = added_paths(target)
        copied: dict[str, list[str]] = {s: [] for s in sources}
        for path in paths:
            th = blob(f"origin/{target}", path)
            if not th:
                continue
            for s in sources:
                if blob(f"origin/{s}", path) == th:
                    copied[s].append(path)
        total = len(paths)
        row = {
            "target": target,
            "added_vs_main": total,
            "copied": {s: {"count": len(v), "pct": round(100 * len(v) / total, 1) if total else 0,
                           "examples": v[:6]} for s, v in copied.items()},
        }
        results.append(row)

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    for row in results:
        print(f"\n== {row['target']}  (adds {row['added_vs_main']} files vs main)")
        for s, info in row["copied"].items():
            print(f"   identical to {s}: {info['count']} files ({info['pct']}%)")
            for ex in info["examples"][:4]:
                print(f"      e.g. {ex}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
