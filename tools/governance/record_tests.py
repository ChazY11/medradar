#!/usr/bin/env python3
"""Run the offline pytest suite and write the measurement artifact.

``PROJECT_STATE.yaml`` claims a test count. A claim needs an artifact, so this
tool runs the suite once, records the exact counts, the command, the tested
commit and (importantly) whether ``tests/`` differs from that commit, and
writes the JSON file that ``check_state.py`` verifies.

The artifact is only truthful while ``tests/`` is unchanged from the recorded
head; if it has changed, this tool refuses to write (exit 2) so the state file
cannot silently claim a stale count.

Usage:
    python tools/governance/record_tests.py
    python tools/governance/record_tests.py --base-ref origin/main --out -
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:  # ``python tools/governance/record_tests.py``
    from . import common
except ImportError:  # ``python -m tools.governance.record_tests``
    import common  # type: ignore

TOOL = "record_tests"
DEFAULT_COMMAND = ["-m", "pytest", "-q", "-o", "addopts="]
COUNT_RE = {
    "passed": re.compile(r"(\d+) passed\b"),
    "skipped": re.compile(r"(\d+) skipped\b"),
    "failed": re.compile(r"(\d+) failed\b"),
    "errors": re.compile(r"(\d+) errors?\b"),
}


def _parse_counts(output: str) -> dict:
    counts = {"passed": 0, "skipped": 0, "failed": 0, "errors": 0}
    summary_lines = [
        line
        for line in output.splitlines()
        if re.search(r"\b(?:passed|failed|error|skipped)\b", line)
        and "====" in line
    ]
    if not summary_lines:
        summary_lines = output.splitlines()[-3:]
    tail = " ".join(summary_lines)
    for name, pattern in COUNT_RE.items():
        match = pattern.search(tail)
        if match:
            counts[name] = int(match.group(1))
    counts["collected"] = (
        counts["passed"] + counts["skipped"] + counts["failed"] + counts["errors"]
    )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Run the offline pytest suite and write the test-count artifact "
            "verified by check_state.py."
        ),
        epilog=(
            "Exit codes: 0 artifact written, 1 pytest failed, "
            "2 refused to write / usage error."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Commit whose tree the measurement describes (default: origin/main).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Artifact path (default: %s; '-' prints to stdout)."
        % common.DEFAULT_TEST_ARTIFACT,
    )
    parser.add_argument(
        "--command",
        default=" ".join(DEFAULT_COMMAND),
        help="Diagnostic command string recorded in the artifact.",
    )
    args = parser.parse_args(argv)

    try:
        root = common.repo_root(args.root)
    except common.ConfigError as exc:
        return common.config_error(TOOL, str(exc))

    base_head = common.git_rev_parse(root, args.base_ref)
    if base_head is None:
        return common.config_error(
            TOOL, "cannot resolve base ref %r (fetch it first)" % args.base_ref
        )
    head = common.git_rev_parse(root, "HEAD")
    if head is None:
        return common.config_error(TOOL, "cannot resolve HEAD")
    # The count must describe a commit: refuse if tests/ has uncommitted edits,
    # because then no commit's tests match the measured tree.
    dirty_tests = common.git_diff_names(root, "HEAD", "tests/")
    if dirty_tests:
        print(
            "%s: refusing to record a test count: tests/ has uncommitted changes "
            "relative to HEAD." % TOOL,
            file=sys.stderr,
        )
        for name in dirty_tests:
            print("  changed: %s" % name, file=sys.stderr)
        return common.EXIT_CONFIG

    tests_changed_vs_base = common.git_diff_names(root, base_head, "tests/")
    if tests_changed_vs_base:
        print(
            "%s: tests/ differs from %s; recording a count for the current HEAD "
            "and flagging that in the artifact." % (TOOL, args.base_ref),
            file=sys.stderr,
        )

    print(
        "%s: running python %s" % (TOOL, " ".join(DEFAULT_COMMAND)),
        file=sys.stderr,
    )
    proc = subprocess.run(
        [sys.executable, *DEFAULT_COMMAND],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    combined = proc.stdout + "\n" + proc.stderr
    counts = _parse_counts(combined)
    if proc.returncode not in (0, 1) or counts["collected"] == 0:
        print(
            "%s: could not parse a pytest summary; first lines of output:" % TOOL,
            file=sys.stderr,
        )
        print("\n".join(combined.splitlines()[:20]), file=sys.stderr)
        return common.EXIT_CONFIG
    if proc.returncode != 0:
        print(
            "%s: pytest failed (exit %d); fix the suite before recording a count"
            % (TOOL, proc.returncode),
            file=sys.stderr,
        )
        print("\n".join(combined.splitlines()[-5:]), file=sys.stderr)
        return common.EXIT_FAIL

    artifact = {
        "schema": common.SCHEMA_TEST_ARTIFACT,
        "collected": counts["collected"],
        "passed": counts["passed"],
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "errors": counts["errors"],
        "command": args.command,
        "tested_head": head,
        "tested_ref": "HEAD",
        "base_ref": args.base_ref,
        "base_head": base_head,
        "tests_unchanged_from_head": True,
        "tests_changed_vs_base": bool(tests_changed_vs_base),
        "note": (
            "Generated by tools/governance/record_tests.py: the offline suite was "
            "run on a working tree whose tests/ was identical to tested_head. "
            "tests_changed_vs_base only records whether the branch differs from "
            "the base ref. Do not hand-edit."
        ),
    }
    payload = json.dumps(artifact, indent=2, sort_keys=False) + "\n"

    if args.out == "-":
        print(payload, end="")
        return common.EXIT_PASS

    output = Path(args.out) if args.out else root / common.DEFAULT_TEST_ARTIFACT
    if not output.is_absolute():
        output = (root / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8", newline="\n")
    print(
        "%s: wrote %s (%d collected, %d passed, %d skipped, %d failed)"
        % (
            TOOL,
            output.relative_to(root).as_posix(),
            counts["collected"],
            counts["passed"],
            counts["skipped"],
            counts["failed"],
        )
    )
    return common.EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
