"""Pin the committed data artifacts by SHA-256 (Phase 4 deliverable integrity).

A research report that cites counts must also pin the exact bytes those counts were
computed from, or a later reader cannot tell whether the numbers describe the file in
the repository. This writes `ARTIFACT_MANIFEST.json` listing every data artifact in a
results directory with its size and SHA-256, plus the rule used.

Note on line endings: the repository's `.gitattributes` marks `*.jsonl` as `-text`, so
the committed bytes are the working-tree bytes and these hashes stay valid after a
checkout. Without that, git's `* text=auto eol=lf` would rewrite CRLF files on checkout
and every recorded hash would silently stop matching.

Usage:
    python experiments/innovation_signals_observatory/sources/make_artifact_manifest.py \
        --results experiments/innovation_signals_observatory/results/2026-11-04
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIR_PARTS = ("_httpcache", "__pycache__", "stability_store")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    root = Path(args.results)
    out = Path(args.out) if args.out else root / "ARTIFACT_MANIFEST.json"
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(SKIP_DIR_PARTS) for part in path.parts):
            continue
        if path.name in ("ARTIFACT_MANIFEST.json",):
            continue
        files.append({
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": root.name,
        "n_files": len(files),
        "total_bytes": sum(f["bytes"] for f in files),
        "rule": ("SHA-256 over the file's bytes as stored in git; *.jsonl is committed with "
                 "-text so checkout does not rewrite line endings and these hashes stay valid"),
        "files": files,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} ({payload['n_files']} files, {payload['total_bytes'] / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
