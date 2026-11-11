"""Freeze a snapshot of the integration staging database into verifier scope.

Uses the SQLite backup API over a read-only source connection so a concurrent
writer cannot produce a torn copy. Records the snapshot digest so every V7
verdict is bound to immutable bytes.

    python tools/convergence/verify/_snapshot_staging.py            # current state
    python tools/convergence/verify/_snapshot_staging.py --label rejected
"""
import argparse
import hashlib
import json
import os
import sqlite3

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SRC = os.path.join(ROOT, "research", "convergence", "staging", "convergence.sqlite")
OUT_DIR = os.path.join(ROOT, "research", "convergence", "verification", "snapshots")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    parser.add_argument("--source", default=SRC)
    args = parser.parse_args(argv)
    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = ("_" + args.label) if args.label else ""
    dest = os.path.join(OUT_DIR, "convergence_staging_snapshot%s.sqlite" % suffix)
    info_path = os.path.join(OUT_DIR, "convergence_staging_snapshot%s.json" % suffix)
    if os.path.exists(dest):
        os.remove(dest)
    src = sqlite3.connect("file:" + args.source.replace("\\", "/") + "?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    info = {"source_path": os.path.relpath(args.source, ROOT).replace("\\", "/"),
            "snapshot_path": os.path.relpath(dest, ROOT).replace("\\", "/"),
            "snapshot_bytes": os.path.getsize(dest),
            "snapshot_sha256": digest(dest)}
    with open(info_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(info, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
