"""Run the round-end verification routine in one command.

The programme's rule is that a round is not finished until its artifacts verify. This script runs every
verifier the repository has, in order, and writes a single machine-readable summary plus a readable log, so
each round ends with evidence rather than an assertion.

Steps:
  1. test suite            python -m medradar selftest
  2. paper claim map       papers/verify_claims.py
  3. paper figures         papers/verify_figures.py
  4. profile self-check    experiments/b027/selfcheck.py
  5. snapshot chain        experiments/b027/snapshot_diff.py
  6. objective audit       tools/audit_objectives.py
  7. repository state      git status / remote comparison

Usage:
    python tools/round_end.py [--skip-selftest]
Exit code 0 only when every step passes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "tools" / "round_end.json"
OUT_LOG = ROOT / "tools" / "round_end.log"

STEPS = (
    ("test suite", [sys.executable, "-m", "medradar", "selftest"], ("Ran ", "OK (")),
    ("paper claim map", [sys.executable, "papers/verify_claims.py"], ("claims checked",)),
    ("methods claim map", [sys.executable, "papers/verify_claims.py", "--paper",
                           "papers/PAPER_METHODS_v1.md", "--claims",
                           "papers/CLAIMS_METHODS.json"], ("claims checked",)),
    ("paper figures", [sys.executable, "papers/verify_figures.py"], ("figures checked",)),
    ("methods figures", [sys.executable, "papers/verify_figures.py", "--paper",
                         "papers/PAPER_METHODS_v1.md"], ("figures checked",)),
    ("profile self-check", [sys.executable, "experiments/b027/selfcheck.py"], ("checked ", "snapshots")),
    ("snapshot chain", [sys.executable, "experiments/b027/snapshot_diff.py"], ("leakage problems",)),
    ("objective audit", [sys.executable, "tools/audit_objectives.py"], ("audit:",)),
)


def tail_line(text: str, prefer: tuple[str, ...] = ()) -> str:
    """Pick the informative line: the last one matching a step-specific marker, else the last line."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if prefer and any(marker in line for marker in prefer):
            return line
    return lines[-1] if lines else "no output"


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT)
    return (result.stdout or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-selftest", action="store_true",
                        help="skip the 20-second test suite (for quick checks)")
    args = parser.parse_args(argv)

    results = []
    log_lines = [f"round-end verification {datetime.now(timezone.utc).isoformat(timespec='seconds')}", ""]
    for name, command, prefer in STEPS:
        if args.skip_selftest and name == "test suite":
            results.append({"step": name, "status": "SKIPPED", "detail": "--skip-selftest"})
            log_lines.append(f"SKIPPED {name}")
            continue
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
        # unittest reports "Ran N tests" on stderr, so the detail line must read both streams
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        detail = tail_line(combined, prefer)
        results.append({"step": name, "status": "PASS" if result.returncode == 0 else "FAIL",
                        "detail": detail, "exit": result.returncode})
        log_lines.append(f"{results[-1]['status']:7s} {name}: {detail}")

    dirty = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    head = git("rev-parse", "HEAD")
    remote_line = git("ls-remote", "--heads", "origin", branch)
    remote = remote_line.split()[0] if remote_line else ""
    synced = bool(head and remote and head == remote)
    state_status = "PASS" if synced else ("N/A" if not remote else "FAIL")
    results.append({"step": "repository state", "status": state_status,
                    "detail": f"HEAD {head[:12]}, remote {'synced' if synced else remote[:12] or 'unknown'}, "
                              f"{len(dirty)} uncommitted path(s)"})
    log_lines.append(f"{state_status:7s} repository state: {results[-1]['detail']}")

    failed = [row for row in results if row["status"] == "FAIL"]
    payload = {"schema": "round_end_v1", "checked_at_utc": datetime.now(timezone.utc).isoformat(
        timespec="seconds"), "branch": branch, "head": head, "remote_synced": synced,
        "uncommitted_paths": dirty, "results": results,
        "summary": {"passed": sum(1 for row in results if row["status"] == "PASS"),
                    "failed": len(failed),
                    "skipped": sum(1 for row in results if row["status"] == "SKIPPED"),
                    "not_applicable": sum(1 for row in results if row["status"] == "N/A")}}
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")
    OUT_LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8", newline="\n")

    for row in results:
        print(f"{row['status']:7s} {row['step']}: {row['detail']}")
    print(f"\n{payload['summary']}")
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_LOG.relative_to(ROOT)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
