"""Index every experiment artifact with its SHA-256 and provenance.

Why an index rather than a directory listing
--------------------------------------------
A report is only checkable if a reader can take one file, hash it, and see that it
is the file the numbers came from.  This script walks the run roots, writes one
row per file (path, bytes, sha256, mtime) and fails if a file it must see is
missing.  Large artifacts (model adapters, corpora) are indexed too: their hashes
are what make "do not commit weights" auditable -- the index proves the weight
files exist locally and were not silently swapped.

Exit codes: 0 wrote the index, 2 a required root is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

#: Roots that must exist for the index to mean anything.
REQUIRED_SUFFIXES = ("training/ovn-qlora/training_run.json",)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_index(roots: Sequence[Path], *, exclude_suffixes: Sequence[str] = ()) -> dict[str, object]:
    files: list[dict[str, object]] = []
    total_bytes = 0
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if any(path.name.endswith(suffix) for suffix in exclude_suffixes):
                continue
            size = path.stat().st_size
            total_bytes += size
            files.append(
                {
                    "path": str(path),
                    "relative": str(path.relative_to(root.parent)),
                    "root": str(root),
                    "bytes": size,
                    "sha256": _sha256(path),
                    "mtime": path.stat().st_mtime,
                }
            )
    return {
        "file_count": len(files),
        "total_bytes": total_bytes,
        "total_mib": round(total_bytes / (1024 * 1024), 2),
        "roots": [str(root) for root in roots],
        "files": files,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--require", action="append", default=None)
    args = parser.parse_args(argv)
    roots = [Path(item) for item in args.root]
    for suffix in (args.require or REQUIRED_SUFFIXES):
        if not any((root / suffix).is_file() for root in roots):
            print(f"REFUSED: required artifact missing: */{suffix}", file=sys.stderr)
            return 2
    index = build_index(roots)
    Path(args.out).write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"indexed {index['file_count']} files ({index['total_mib']} MiB) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
