"""The nightly run's own account of what it did, step by step.

Every step of `deploy/preprint_nightly.sh` swallows its failure with `|| true`, which is correct: a
blocked source is a normal night, not an outage. The cost is that a step doing nothing left no trace -
measured in November, the patent lane returned 503 every night for a week and the first thing to notice
was a health check, not the pipeline that was failing.

Each step now appends one JSON line here, and `/sources` prints the latest run. Reading is bounded and
tolerant: a torn line is skipped, an absent file is a stated gap, and nothing here can fail a page.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_DIR = "/srv/medradar/data/radar"
KEEP_LINES = 400


def ledger_path(directory: str | os.PathLike[str] | None = None) -> Path:
    base = Path(directory or os.environ.get("MEDRADAR_RADAR_DIR") or DEFAULT_DIR)
    return base / "nightly.jsonl"


def read(directory: str | os.PathLike[str] | None = None, *, limit_steps: int = 20) -> dict[str, Any]:
    """The most recent run and its steps. `available: False` means nothing has run yet."""
    path = ledger_path(directory)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"available": False, "run": None, "steps": [], "failed": []}
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue          # a half-written line from a killed night is not a reason to 500
    if not rows:
        return {"available": False, "run": None, "steps": [], "failed": []}
    run_id = rows[-1].get("run")
    for row in reversed(rows):
        if row.get("step") == "_start":
            run_id = row.get("run")
            break
    steps = [row for row in rows if row.get("run") == run_id and row.get("step") != "_start"]
    return {
        "available": True,
        "run": run_id,
        "steps": steps[-limit_steps:],
        "failed": [row.get("step") for row in steps if not row.get("ok")],
    }


def summary_for_page(directory: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """What /sources prints: the run, its steps, and how many of them reported a failure."""
    data = read(directory)
    if not data.get("available"):
        return {"available": False, "note": "还没有记录过夜间任务"}
    steps = data.get("steps") or []
    return {
        "available": True,
        "run": str(data.get("run") or "")[:19].replace("T", " "),
        "steps": [{"step": row.get("step"), "ok": bool(row.get("ok")),
                   "at": str(row.get("at") or "")[:19].replace("T", " "),
                   "note": row.get("note") or ""} for row in steps],
        "failed": data.get("failed") or [],
        "count": len(steps),
    }


__all__ = ["DEFAULT_DIR", "KEEP_LINES", "ledger_path", "read", "summary_for_page"]
