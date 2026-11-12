#!/usr/bin/env python3
"""Bump PROJECT_STATE.yaml's `main` block to a git ref, then regenerate views.

Why this exists
---------------
`check_state.py` requires the state's `main.head` to equal `origin/main`. When
`main` advances, every open PR must carry a one-line state update; this tool
performs that update mechanically and deterministically:

* `main.head`, `main.short`, `main.committed_at`, `main.commit_subject`;
* `main.version` (read from the ref's `pyproject.toml`, not the worktree);
* `main.tracked_files` and `main.workflows` (from the ref's tree);
* the top-level `generated_at` timestamp (set to the ref's commit time, so the
  result is reproducible from the ref — no wall clock).

Everything else in PROJECT_STATE.yaml is preserved byte-for-byte, including the
hand-written comments, because the tool replaces only the `main:` block and the
`generated_at:` value. Run `gen_views.py` afterwards (or use `--with-views`) to
refresh the generated README/CHANGELOG/RESEARCH_INDEX.

This is the pre-merge half of the safe automation: it runs in the PR, on the
contributor's machine or in CI, and never writes to `main` itself. A
post-merge bot commit cannot maintain strict `main.head == HEAD` equality,
because the commit that updates the file changes the head it would have to
record (see docs/refoundation/phase1/GOVERNANCE_ACTIVATION_REVIEW.md).

Usage:
    python tools/governance/bump_state.py                       # origin/main
    python tools/governance/bump_state.py --ref origin/main --dry-run
    python tools/governance/bump_state.py --with-views
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:  # ``python tools/governance/bump_state.py``
    from . import common, yamlmini
except ImportError:  # ``python -m tools.governance.bump_state``
    import common  # type: ignore
    import yamlmini  # type: ignore

TOOL = "bump_state"
TOP_LEVEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")
MAIN_BLOCK_RE = re.compile(r"^main:\s*$")
GENERATED_AT_RE = re.compile(r'^generated_at:\s*".*"\s*$')


class BumpError(RuntimeError):
    pass


def _git_show_file(root: Path, ref: str, path: str) -> str:
    code, out, err = common.run_git(root, "show", "%s:%s" % (ref, path))
    if code != 0:
        raise BumpError("cannot read %s at %s: %s" % (path, ref, err.strip()))
    return out


def _yaml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return '"%s"' % escaped


def _ref_facts(root: Path, ref: str) -> dict:
    code, out, err = common.run_git(root, "rev-parse", "--verify", ref + "^{commit}")
    if code != 0:
        raise BumpError("cannot resolve %r: %s" % (ref, err.strip()))
    head = out.strip()
    code, out, err = common.run_git(root, "show", "-s", "--format=%cI%x00%s", head)
    if code != 0:
        raise BumpError("git show failed: %s" % err.strip())
    committed_at, _, subject = out.partition("\x00")
    code, out, err = common.run_git(root, "ls-tree", "-r", "--name-only", head)
    if code != 0:
        raise BumpError("git ls-tree failed: %s" % err.strip())
    tracked = [line for line in out.splitlines() if line]
    workflows = sorted(
        Path(path).stem
        for path in tracked
        if path.startswith(".github/workflows/") and path.endswith(".yml")
    )
    version_text = _git_show_file(root, head, "pyproject.toml")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', version_text)
    if match is None:
        raise BumpError("no project version in pyproject.toml at %s" % head)
    return {
        "ref": ref,
        "head": head,
        "short": head[:7],
        "committed_at": committed_at.strip(),
        "commit_subject": subject.strip(),
        "version": match.group(1),
        "tracked_files": len(tracked),
        "workflows": workflows,
    }


def _main_block(facts: dict) -> str:
    lines = [
        "main:",
        "  ref: %s" % facts["ref"],
        "  head: %s" % facts["head"],
        "  short: %s" % facts["short"],
        "  committed_at: %s" % _yaml_string(facts["committed_at"]),
        "  commit_subject: %s" % _yaml_string(facts["commit_subject"]),
        "  version: %s" % _yaml_string(facts["version"]),
        "  version_source: pyproject.toml",
        "  tracked_files: %d" % facts["tracked_files"],
    ]
    if facts["workflows"]:
        lines.append("  workflows:")
        lines.extend("    - %s" % name for name in facts["workflows"])
    else:
        lines.append("  workflows: []")
    return "\n".join(lines) + "\n"


def _main_block_span(lines: list[str]) -> tuple[int, int]:
    start = None
    for index, line in enumerate(lines):
        if MAIN_BLOCK_RE.match(line):
            start = index
            break
    if start is None:
        raise BumpError("no top-level 'main:' block found in PROJECT_STATE.yaml")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if TOP_LEVEL_RE.match(lines[index]):
            end = index
            break
    return start, end


def _replace_main_block(text: str, block: str) -> str:
    lines = text.split("\n")
    start, end = _main_block_span(lines)
    return "\n".join(lines[:start]) + "\n" + block + "\n".join(lines[end:])


def _existing_main_block(text: str) -> str:
    lines = text.split("\n")
    start, end = _main_block_span(lines)
    return "\n".join(lines[start:end]).rstrip("\n")


def _replace_generated_at(text: str, timestamp: str) -> str:
    lines = text.split("\n")
    replaced = False
    for index, line in enumerate(lines):
        if GENERATED_AT_RE.match(line):
            lines[index] = 'generated_at: "%s"' % timestamp
            replaced = True
            break
    if not replaced:
        raise BumpError("no top-level generated_at value found in PROJECT_STATE.yaml")
    return "\n".join(lines)


def propose(root: Path, state_path: Path, ref: str) -> tuple[str, str, dict]:
    original = state_path.read_text(encoding="utf-8")
    facts = _ref_facts(root, ref)
    new_block = _main_block(facts)
    if _existing_main_block(original) == new_block.rstrip("\n"):
        return original, original, facts
    updated = _replace_main_block(original, new_block)
    updated = _replace_generated_at(updated, facts["committed_at"])
    # Sanity: the result must parse and describe the ref exactly.
    parsed = yamlmini.loads(updated, path=str(state_path))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("main"), dict):
        raise BumpError("bump produced an unparseable state file")
    main = parsed["main"]
    for key in (
        "ref",
        "head",
        "short",
        "committed_at",
        "commit_subject",
        "version",
        "tracked_files",
    ):
        if main.get(key) != facts[key]:
            raise BumpError(
                "bump mismatch for main.%s: wrote %r, parsed %r"
                % (key, facts[key], main.get(key))
            )
    if main.get("workflows") != facts["workflows"]:
        raise BumpError("bump mismatch for main.workflows")
    return original, updated, facts


def _run_views(root: Path) -> int:
    try:  # script invocation
        import gen_views  # type: ignore
    except ImportError:  # module invocation
        from . import gen_views  # type: ignore

    return gen_views.main(["--root", str(root)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Update PROJECT_STATE.yaml's main block (head, date, subject, "
            "version, tracked-file and workflow counts) to a git ref, then "
            "regenerate the derived views. Deterministic: no wall clock."
        ),
        epilog=(
            "Exit codes: 0 state is up to date or was written, 1 error, "
            "2 configuration error. Use this BEFORE pushing/merging a PR so "
            "check_state.py passes against the PR's base main."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--ref",
        default="origin/main",
        help="Git ref that PROJECT_STATE.yaml should describe (default: origin/main).",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="State file (default: PROJECT_STATE.yaml).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the unified diff instead of writing the file.",
    )
    parser.add_argument(
        "--with-views",
        action="store_true",
        help="Regenerate README/CHANGELOG/RESEARCH_INDEX after writing the state.",
    )
    args = parser.parse_args(argv)

    try:
        root = common.repo_root(args.root)
        state_path = Path(args.state) if args.state else root / common.DEFAULT_STATE
        if not state_path.is_absolute():
            state_path = (root / state_path).resolve()
        original, updated, facts = propose(root, state_path, args.ref)
    except (common.ConfigError, BumpError) as exc:
        return common.config_error(TOOL, str(exc))

    changed = updated != original
    if args.dry_run:
        import difflib

        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=str(state_path.relative_to(root)),
            tofile=str(state_path.relative_to(root)),
            n=3,
        )
        print("".join(diff), end="")
        if args.json:
            print(
                json.dumps(
                    {
                        "tool": TOOL,
                        "dry_run": True,
                        "changed": changed,
                        "ref": facts["ref"],
                        "head": facts["head"],
                    },
                    indent=2,
                )
            )
        return common.EXIT_PASS

    if changed:
        state_path.write_text(updated, encoding="utf-8", newline="\n")
    if args.json:
        print(
            json.dumps(
                {
                    "tool": TOOL,
                    "changed": changed,
                    "ref": facts["ref"],
                    "head": facts["head"],
                    "committed_at": facts["committed_at"],
                    "version": facts["version"],
                    "tracked_files": facts["tracked_files"],
                    "workflows": facts["workflows"],
                },
                indent=2,
            )
        )
    else:
        print(
            "%s %s: %s -> %s (%d tracked files, workflows: %s)%s"
            % (
                "UPDATED" if changed else "UP TO DATE",
                state_path.relative_to(root).as_posix(),
                "state",
                facts["ref"] + " @ " + facts["short"],
                facts["tracked_files"],
                ", ".join(facts["workflows"]),
                "; rerun gen_views.py" if changed else "",
            )
        )
    if args.with_views and changed:
        return _run_views(root)
    return common.EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
