"""S-028 audit shared helpers.

Read-only access to the three data stores; every number in the report is produced
by the audit_*.py scripts and dumped here as machine-readable JSON.

Partial sections are written to a scratch dir OUTSIDE the study folder so that the
study folder ends up containing exactly the two deliverable files plus audit_*.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

RESEARCH = r"D:\DEPPSKK\worktrees\integration-v2\data\research.sqlite"
PRODUCT = r"D:\DEPPSKK\medradar\data\medradar.sqlite"
OBS = r"D:\DEPPSKK\medradar\data\observatory\observatory.sqlite"
CFG = r"D:\DEPPSKK\medradar\config"

STUDY = r"D:\DEPPSKK\medradar\research\studies\graph_early_signal_s028"
SCRATCH = os.path.join(tempfile.gettempdir(), "s028_audit")


def ro(path: str) -> sqlite3.Connection:
    """Open a database strictly read-only (mode=ro URI)."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def sha256_of(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def dump(section: str, payload: dict) -> str:
    """Persist one audit section to the scratch dir; the assembler merges them."""
    os.makedirs(SCRATCH, exist_ok=True)
    p = os.path.join(SCRATCH, f"{section}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, default=str)
    print(f"\n[written] {p}")
    return p


def pct(num, den) -> float | None:
    if not den:
        return None
    return round(100.0 * num / den, 4)
