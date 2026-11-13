#!/usr/bin/env python3
"""Refresh PROJECT_STATE.yaml's five state concepts from a git ref.

Design (see docs/refoundation/phase3/STATE_LIFECYCLE.md)
--------------------------------------------------------
The state distinguishes five concepts instead of pretending one commit is all of
them:

* ``git.head`` — the main commit last **observed** (may legitimately lag main);
* ``verified.commit`` — the last commit whose full suite + all gates passed;
* ``release.version`` / ``release.commit`` — what is actually released (or null);
* ``data_snapshot`` — local data build (hand-maintained, untouched here);
* ``tests.tested_head`` — the commit the measured suite describes (untouched).

This tool refreshes exactly the blocks it can derive mechanically — ``git``,
``verified`` and the ``release.version`` — from ``--ref`` (default
``origin/main``), sets ``generated_at`` to the ref's commit time (deterministic:
no wall clock), and regenerates the derived views in the same command. It never
invents a release commit: an existing non-null ``release.commit`` is preserved.

After a merge, the state may be stale-but-an-ancestor of main; that is a WARNING
in ``check_state.py``, not a failure. Running this one command refreshes the
observed head and the verified baseline when convenient.

Usage:
    python tools/governance/bump_state.py                 # refresh + views
    python tools/governance/bump_state.py --dry-run       # show the diff only
    python tools/governance/bump_state.py --no-views      # state only
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
TOP_LEVEL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$")
GENERATED_AT_RE = re.compile(r'^generated_at:\s*".*"\s*$')
BLOCK_KEYS = ("git", "verified", "release")
VIEW_FILES = ("README.md", "CHANGELOG.md", "docs/RESEARCH_INDEX.md")


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


def _git_block(facts: dict) -> str:
    lines = [
        "git:",
        "  ref: %s" % facts["ref"],
        "  head: %s" % _yaml_string(facts["head"]),
        "  short: %s" % _yaml_string(facts["short"]),
        "  committed_at: %s" % _yaml_string(facts["committed_at"]),
        "  commit_subject: %s" % _yaml_string(facts["commit_subject"]),
        "  observed_at: %s" % _yaml_string(facts["committed_at"]),
        "  tracked_files: %d" % facts["tracked_files"],
    ]
    if facts["workflows"]:
        lines.append("  workflows:")
        lines.extend("    - %s" % name for name in facts["workflows"])
    else:
        lines.append("  workflows: []")
    return "\n".join(lines) + "\n"


def _verified_block(facts: dict) -> str:
    return "\n".join(
        [
            "verified:",
            "  commit: %s" % _yaml_string(facts["head"]),
            "  verified_at: %s" % _yaml_string(facts["committed_at"]),
            '  note: "Refreshed by bump_state.py from %s; the full offline suite '
            'and the governance gates are expected to pass at this commit."'
            % facts["ref"],
        ]
    ) + "\n"


def _release_block(facts: dict, existing_commit: str | None) -> str:
    commit = _yaml_string(existing_commit) if existing_commit else "null"
    return "\n".join(
        [
            "release:",
            "  version: %s" % _yaml_string(facts["version"]),
            "  commit: %s" % commit,
        ]
    ) + "\n"


def _block_span(lines: list[str], key: str) -> tuple[int, int]:
    pattern = re.compile("^" + re.escape(key) + r":\s*$")
    start = None
    for index, line in enumerate(lines):
        if pattern.match(line):
            start = index
            break
    if start is None:
        raise BumpError(
            "no top-level '%s:' block found in PROJECT_STATE.yaml; run the "
            "schema migration (see docs/refoundation/phase3/STATE_LIFECYCLE.md)" % key
        )
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if TOP_LEVEL_RE.match(lines[index]):
            end = index
            break
    return start, end


def _existing_block(text: str, key: str) -> str:
    lines = text.split("\n")
    start, end = _block_span(lines, key)
    return "\n".join(lines[start:end]).rstrip("\n")


def _replace_block(text: str, key: str, block: str) -> str:
    lines = text.split("\n")
    start, end = _block_span(lines, key)
    return "\n".join(lines[:start]) + "\n" + block + "\n".join(lines[end:])


def _replace_generated_at(text: str, timestamp: str) -> str:
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if GENERATED_AT_RE.match(line):
            lines[index] = 'generated_at: "%s"' % timestamp
            return "\n".join(lines)
    raise BumpError("no top-level generated_at value found in PROJECT_STATE.yaml")


def propose(root: Path, state_path: Path, ref: str) -> tuple[str, str, dict]:
    original = state_path.read_text(encoding="utf-8")
    facts = _ref_facts(root, ref)
    try:
        parsed_old = yamlmini.loads(original, path=str(state_path))
    except yamlmini.YamlSubsetError as exc:
        raise BumpError("cannot parse PROJECT_STATE.yaml: %s" % exc)
    if not isinstance(parsed_old, dict):
        raise BumpError("PROJECT_STATE.yaml must be a mapping")
    release_old = parsed_old.get("release") or {}
    existing_commit = release_old.get("commit") if isinstance(release_old, dict) else None
    if existing_commit is not None and not isinstance(existing_commit, str):
        raise BumpError("release.commit must be null or a commit sha")

    blocks = {
        "git": _git_block(facts),
        "verified": _verified_block(facts),
        "release": _release_block(facts, existing_commit),
    }
    if all(
        _existing_block(original, key) == blocks[key].rstrip("\n")
        for key in BLOCK_KEYS
    ):
        return original, original, facts
    updated = original
    for key in BLOCK_KEYS:
        updated = _replace_block(updated, key, blocks[key])
    updated = _replace_generated_at(updated, facts["committed_at"])

    parsed = yamlmini.loads(updated, path=str(state_path))
    if not isinstance(parsed, dict):
        raise BumpError("bump produced an unparseable state file")
    git_block = parsed.get("git")
    if not isinstance(git_block, dict):
        raise BumpError("bump produced no git block")
    for key in (
        "ref",
        "head",
        "short",
        "committed_at",
        "commit_subject",
        "tracked_files",
    ):
        if git_block.get(key) != facts[key]:
            raise BumpError(
                "bump mismatch for git.%s: wrote %r, parsed %r"
                % (key, facts[key], git_block.get(key))
            )
    if git_block.get("workflows") != facts["workflows"]:
        raise BumpError("bump mismatch for git.workflows")
    verified = parsed.get("verified")
    if not isinstance(verified, dict) or verified.get("commit") != facts["head"]:
        raise BumpError("bump mismatch for verified.commit")
    release = parsed.get("release")
    if not isinstance(release, dict) or release.get("version") != facts["version"]:
        raise BumpError("bump mismatch for release.version")
    if release.get("commit") != existing_commit:
        raise BumpError("bump changed release.commit")
    return original, updated, facts


def _views_available(root: Path) -> bool:
    return all((root / path).is_file() for path in VIEW_FILES)


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
            "Refresh the observed-main, verified and release-version state from a "
            "git ref, then regenerate the derived views. Deterministic: the state "
            "timestamp is the ref's commit time, not a wall clock."
        ),
        epilog=(
            "Exit codes: 0 state is up to date or was written, 1 error, "
            "2 configuration error. One command after a merge: "
            "`python tools/governance/bump_state.py`."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--ref",
        default="origin/main",
        help="Git ref whose tree/commit the state should observe (default: origin/main).",
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
        "--no-views",
        action="store_true",
        help="Do not regenerate README/CHANGELOG/RESEARCH_INDEX after writing.",
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
            "%s %s: observed %s @ %s (%d tracked files, workflows: %s)"
            % (
                "UPDATED" if changed else "UP TO DATE",
                state_path.relative_to(root).as_posix(),
                facts["ref"],
                facts["short"],
                facts["tracked_files"],
                ", ".join(facts["workflows"]),
            )
        )
    if changed and not args.no_views:
        if _views_available(root):
            code = _run_views(root)
            if code != common.EXIT_PASS:
                return code
        else:
            print(
                "%s: derived views not present here; skipped view regeneration"
                % TOOL
            )
    return common.EXIT_PASS


if __name__ == "__main__":
    sys.exit(main())
