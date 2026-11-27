"""One line per nightly step, so a stalled lane is visible without reading the journal.

Why this exists
---------------
The nightly job runs seven steps and swallows every failure with `|| true`, which is right: a blocked
source is a normal night, not an outage. But it means the only evidence that a step did nothing was a
journal line nobody reads. Measured: the patent lane had been returning 503 for a week and the failure
first surfaced through a health check, not through the pipeline that was failing.

This records what each step did, in a file the web process can read:

    {"run": "2026-11-28T04:20:00Z", "step": "papers:europepmc", "ok": true,
     "started": "...", "ended": "...", "note": "candidates 120, stored 66"}

Append-only, bounded, never fatal: a step that cannot be recorded must not fail the step.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Run as a script from the release directory, so the package is not on the path yet.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_PATH = Path("/srv/medradar/data/radar/nightly.jsonl")
KEEP_LINES = 400


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    # Bound the file: the last few runs are all anyone reads, and an unbounded log on a small server is
    # its own kind of defect.
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > KEEP_LINES:
            path.write_text("\n".join(lines[-KEEP_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def start(path: Path | None = None, *, run: str | None = None) -> str:
    run_id = run or _now()
    _append(path or DEFAULT_PATH, {"run": run_id, "step": "_start", "ok": True, "at": _now()})
    return run_id


def mark(step: str, ok: bool, note: str = "", *, run: str, path: Path | None = None) -> None:
    _append(path or DEFAULT_PATH, {"run": run, "step": step, "ok": bool(ok), "at": _now(),
                                   "note": str(note)[:300]})


def read(path: Path | None = None, *, limit_steps: int = 20) -> dict[str, Any]:
    """Read through the package module, so the script and the page share one parser."""
    from medradar.radar.nightly import read as read_ledger

    target = path or DEFAULT_PATH
    return read_ledger(target.parent, limit_steps=limit_steps)


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:])
    path = Path(args[0]) if args and args[0].endswith(".jsonl") else DEFAULT_PATH
    if path != DEFAULT_PATH:
        args = args[1:]
    if not args:
        print(json.dumps(read(path), ensure_ascii=False, indent=2))
        return 0
    command = args[0]
    if command == "start":
        print(start(path))
        return 0
    if command == "mark" and len(args) >= 3:
        run = args[3] if len(args) > 3 else start(path)
        mark(args[1], args[2] in ("ok", "true", "1"), args[4] if len(args) > 4 else "", run=run, path=path)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
