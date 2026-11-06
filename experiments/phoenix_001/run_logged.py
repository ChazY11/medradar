#!/usr/bin/env python3
"""Execute a reviewed local command and preserve its real outcome and resource use."""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    log_dir = Path(__file__).with_name("logs")
    log_dir.mkdir(exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in args.name)
    stdout_path = log_dir / f"{safe_name}.stdout.txt"
    started_at = datetime.now(timezone.utc)
    start = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=args.timeout, check=False)
        exit_code, stdout, stderr, failure = result.returncode, result.stdout, result.stderr, None
    except subprocess.TimeoutExpired as exc:
        exit_code, stdout, stderr, failure = 124, exc.stdout or "", exc.stderr or "", "timeout"
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
    finished_at = datetime.now(timezone.utc)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    stdout_path.write_text(stdout + (("\n[stderr]\n" + stderr) if stderr else ""), encoding="utf-8")
    payload = {
        "command": command, "exit_code": exit_code, "failure": failure,
        "started_at": started_at.isoformat(), "finished_at": finished_at.isoformat(),
        "wall_seconds": time.monotonic() - start,
        "cpu_user_seconds": after.ru_utime - before.ru_utime,
        "cpu_system_seconds": after.ru_stime - before.ru_stime,
        "max_rss_kib": after.ru_maxrss,
        "stdout_log": stdout_path.name,
    }
    (log_dir / f"{safe_name}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(stdout, end="")
    if stderr:
        print(stderr, end="", file=__import__("sys").stderr)
    print(json.dumps(payload, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
