"""Blob-identity matrix: are the parallel infrastructure packages literal copies?

A git blob is content-addressed, so two branches showing the same blob id for
the same path means byte-identical files. That is proof of copy-paste
duplication rather than convergent design.

Read-only.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "blob_identity.json"

BRANCHES = [
    "feat/medradar-2.0-mvp",
    "feat/live-observatory-v1",
    "feat/observatory-reliability-v1",
    "research/s028-temporal-graph-early-signal",
    "research/s029-evidence-based-relations",
    "research/s031-hiring-capability-study",
    "research/innovation-signals-observatory",
    "foundation/atlas-001",
    "research/horizon-001",
    "integration/convergence-001",
]

# candidate duplicate-infrastructure files
CANDIDATES = [
    "medradar/product/store.py",
    "medradar/product/catalog.py",
    "medradar/product/analyst.py",
    "medradar/atlas/store.py",
    "medradar/atlas/evidence/schema.py",
    "medradar/atlas/identity/resolver.py",
    "medradar/atlas/db/migrations.py",
    "medradar/atlas/graph/build.py",
    "medradar/atlas/quality/checks.py",
    "medradar/observatory/ledger.py",
    "medradar/tkg/store.py",
    "medradar/forecast_registry.py",
    "web/CONTRACT.md",
    "web/js/util.js",
    "pyproject.toml",
    "README.md",
]


def blob(ref: str, path: str) -> str | None:
    p = subprocess.run(["git", "rev-parse", f"{ref}:{path}"], cwd=str(REPO),
                       capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def main() -> int:
    matrix: dict[str, dict[str, str | None]] = {}
    for path in CANDIDATES:
        row = {b: blob(f"origin/{b}", path) for b in BRANCHES}
        matrix[path] = row

    out: dict = {"branches": BRANCHES, "matrix": matrix, "identity_groups": []}
    for path, row in matrix.items():
        groups: dict[str, list[str]] = {}
        for b, h in row.items():
            if h:
                groups.setdefault(h, []).append(b)
        for h, bs in groups.items():
            if len(bs) >= 2:
                out["identity_groups"].append({
                    "path": path, "blob": h, "branches": sorted(bs),
                    "count": len(bs),
                })

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}\n")
    print("path | copy groups (blob -> #branches)")
    for path in CANDIDATES:
        groups = [g for g in out["identity_groups"] if g["path"] == path]
        present = sum(1 for v in matrix[path].values() if v)
        if not present:
            continue
        desc = ", ".join(f"{g['blob'][:8]}x{g['count']}" for g in groups) or "all distinct"
        print(f"{path:48s} present={present:2d}  {desc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
