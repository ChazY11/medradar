#!/usr/bin/env python3
"""Audit expected frozen assets without creating, modifying or replacing them."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).with_name("asset_audit.json")
EXPECTED = ("data/medradar.sqlite", "data/research.sqlite")


def command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=15, check=False)
        return result.stdout.strip() or result.stderr.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_sqlite(path: Path) -> dict:
    display_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    row: dict[str, object] = {"path": display_path.as_posix(), "exists": path.is_file(), "sha256": None}
    if not path.is_file():
        row.update({"size_bytes": None, "read_only_test": False, "integrity_check": "not_run_missing"})
        return row
    row["size_bytes"] = path.stat().st_size
    row["sha256"] = sha256(path)
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            row["integrity_check"] = result[0] if result else "no_result"
            row["read_only_test"] = True
    except sqlite3.Error as exc:
        row["integrity_check"] = f"failed: {exc}"
        row["read_only_test"] = False
    return row


def main() -> int:
    candidates = list(EXPECTED)
    external = os.environ.get("MEDRADAR_DATA_DIR")
    if external:
        candidates.extend(str(Path(external) / Path(p).name) for p in EXPECTED)
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": command_version(["git", "rev-parse", "HEAD"]),
        "git_branch": command_version(["git", "branch", "--show-current"]),
        "os": platform.platform(), "python": sys.version,
        "node": command_version(["node", "--version"]),
        "npm": command_version(["npm", "--version"]),
        "assets": [audit_sqlite(ROOT / p) for p in dict.fromkeys(candidates)],
        "policy": "Missing frozen stores are not regenerated or replaced. Existing stores are opened with SQLite mode=ro only.",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
