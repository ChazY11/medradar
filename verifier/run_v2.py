#!/usr/bin/env python3
"""Run v2 and append an immutable timestamped record under verifier/runs/."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "verifier" / "runs"
RUNS.mkdir(parents=True, exist_ok=True)
started = datetime.now(timezone.utc)
command = [sys.executable, "verifier/v2/verify.py"]
result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=600, check=False)
finished = datetime.now(timezone.utc)
existing = list(RUNS.glob("*-v2-*.json"))
number = max([int(p.name.split("-", 1)[0]) for p in existing if p.name.split("-", 1)[0].isdigit()] + [0]) + 1
stem = f"{number:03d}-v2-{started.strftime('%Y%m%dT%H%M%SZ')}"
(RUNS / f"{stem}.txt").write_text(result.stdout, encoding="utf-8")
meta = {
    "command": " ".join(command), "exit_code": result.returncode,
    "started_at": started.isoformat(), "finished_at": finished.isoformat(),
    "stdout_file": f"{stem}.txt",
}
try:
    parsed = json.loads(result.stdout)
    meta["ok"] = parsed.get("ok")
    meta["values"] = parsed.get("checks")
except json.JSONDecodeError:
    meta["ok"] = False
    meta["values"] = {"parse_error": "verifier output was not JSON"}
(RUNS / f"{stem}.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(result.stdout, end="")
print(f"verifier record: verifier/runs/{stem}.json")
raise SystemExit(result.returncode)
