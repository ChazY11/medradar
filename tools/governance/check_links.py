#!/usr/bin/env python3
"""Validate repository-relative Markdown links under ``docs/``.

What this gate blocks
---------------------
* a relative Markdown link or image in ``docs/**/*.md`` that points at a path
  which does not exist (a moved page, a renamed file, a typo);
* a link that escapes the repository root;
* a link that is ambiguous because it has no path (pure fragment) — those are
  skipped by design, and external URLs (any scheme) are skipped as well.

Fenced code blocks, inline HTML comments and external URLs are not checked.
Absolute filesystem links are rejected: published documentation must use
repository-relative paths.

Exit codes: 0 pass, 1 check failed, 2 configuration/usage error.

Usage:
    python tools/governance/check_links.py [--json]
    python tools/governance/check_links.py --docs docs
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

try:  # ``python tools/governance/check_links.py``
    from . import common
except ImportError:  # ``python -m tools.governance.check_links``
    import common  # type: ignore

TOOL = "check_links"
LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+[^)]*)?\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SCHEME_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9+.-]*:")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
ABSOLUTE_RE = re.compile(r"\A(?:/|[A-Za-z]:[\\/])")


def _strip_code_and_comments(text: str) -> list[tuple[int, str]]:
    """Return (line_number, line) with fenced blocks and HTML comments removed."""
    lines: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        lines.append((number, line))
    return lines


def _target(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    return value


def check_markdown(root: Path, path: Path) -> tuple[list[dict], int]:
    """Return (broken_links, checked_count) for one Markdown file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = HTML_COMMENT_RE.sub("", text)
    broken: list[dict] = []
    checked = 0
    for line_number, line in _strip_code_and_comments(text):
        for match in LINK_RE.finditer(line):
            raw = _target(match.group(1))
            if not raw:
                continue
            if raw.startswith("#"):
                continue  # pure fragment: anchor validation is out of scope
            if SCHEME_RE.match(raw) or raw.startswith("//"):
                continue  # external URL or protocol-relative link
            if ABSOLUTE_RE.match(raw):
                broken.append(
                    {
                        "file": common.rel_posix(path, root),
                        "line": line_number,
                        "target": raw,
                        "reason": "absolute filesystem path in documentation",
                    }
                )
                continue
            target_path = urllib.parse.unquote(raw.split("#", 1)[0].split("?", 1)[0])
            if target_path == "":
                continue
            checked += 1
            resolved = (path.parent / target_path).resolve()
            if not common.is_within(root, resolved):
                broken.append(
                    {
                        "file": common.rel_posix(path, root),
                        "line": line_number,
                        "target": raw,
                        "reason": "link escapes the repository root",
                    }
                )
                continue
            if not resolved.exists():
                broken.append(
                    {
                        "file": common.rel_posix(path, root),
                        "line": line_number,
                        "target": raw,
                        "reason": "target does not exist",
                    }
                )
    return broken, checked


def build_report(root: Path, docs_dir: Path) -> common.Report:
    report = common.Report(TOOL)
    if not docs_dir.is_dir():
        report.fail("docs.exists", "docs directory not found: %s" % docs_dir)
        return report
    markdown_files = sorted(docs_dir.rglob("*.md"))
    report.check(
        "docs.markdown_files",
        len(markdown_files) > 0,
        "%d Markdown files under %s"
        % (len(markdown_files), common.rel_posix(docs_dir, root)),
    )
    all_broken: list[dict] = []
    total_links = 0
    for path in markdown_files:
        broken, checked = check_markdown(root, path)
        all_broken.extend(broken)
        total_links += checked
    report.check(
        "links.checked", True, "%d relative link(s) resolved against the filesystem" % total_links
    )
    if all_broken:
        for item in all_broken:
            report.fail(
                "links.%s:%d" % (item["file"], item["line"]),
                "%r — %s" % (item["target"], item["reason"]),
            )
    else:
        report.check("links.resolve", True, "every relative link resolves")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Validate relative Markdown links under docs/ (external URLs, "
            "fragments and fenced code blocks are skipped)."
        ),
        epilog=(
            "Exit codes: 0 pass, 1 broken link, 2 configuration error. "
            "Generated pages (docs/RESEARCH_INDEX.md) are checked too, so a "
            "generator that emits a stale path fails here."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--docs",
        default="docs",
        help="Directory containing Markdown (default: docs).",
    )
    args = parser.parse_args(argv)

    try:
        root = common.repo_root(args.root)
    except common.ConfigError as exc:
        return common.config_error(TOOL, str(exc))
    docs_dir = Path(args.docs)
    if not docs_dir.is_absolute():
        docs_dir = (root / docs_dir).resolve()
    report = build_report(root, docs_dir)
    return common.emit(report, args.json)


if __name__ == "__main__":
    sys.exit(main())
