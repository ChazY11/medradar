#!/usr/bin/env python3
"""Verify that frozen research artifacts have not changed or been added to.

What this gate blocks
---------------------
* a file listed in ``docs/governance/FROZEN.yaml`` whose SHA-256 changed
  (editing a frozen protocol, report or forecast set in place);
* a file that disappeared from a frozen study directory;
* a new file appearing under a frozen study directory (an unreviewed artifact
  entering a study that is already on the record).

Changing a frozen artifact is allowed only through a dedicated commit that
updates ``FROZEN.yaml`` with a reason; this gate makes that commit explicit
instead of silent. ``--manifest`` prints the current directory manifests for
that review — it never writes to the repository.

Exit codes: 0 pass, 1 check failed, 2 configuration/usage error.

Usage:
    python tools/governance/check_frozen.py [--json]
    python tools/governance/check_frozen.py --manifest
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:  # ``python tools/governance/check_frozen.py``
    from . import common, yamlmini
except ImportError:  # ``python -m tools.governance.check_frozen``
    import common  # type: ignore
    import yamlmini  # type: ignore

TOOL = "check_frozen"
FREEZE_ID_RE = re.compile(r"\AFZ-[0-9]{3}\Z")


def _relative(root: Path, raw: str, where: str, report: common.Report) -> Path | None:
    if raw.startswith("/") or re.match(r"\A[A-Za-z]:[\\/]", raw):
        report.fail("%s.path" % where, "absolute path is not allowed: %r" % raw)
        return None
    if ".." in Path(raw).parts:
        report.fail("%s.path" % where, "path must stay inside the repository: %r" % raw)
        return None
    return root / raw


def _walk_files(directory: Path) -> list[str]:
    """Sorted repository-relative POSIX paths of every file under *directory*."""
    return sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    )


def _check_file(
    report: common.Report, root: Path, entry: dict, where: str
) -> tuple[str, int] | None:
    path = _relative(root, entry.get("path", ""), where, report)
    sha = entry.get("sha256")
    if path is None:
        return None
    if not isinstance(sha, str) or not re.match(r"\A[0-9a-f]{64}\Z", sha):
        report.fail("%s.sha256" % where, "expected 64 lowercase hex characters, found %r" % (sha,))
        return None
    if not path.is_file():
        report.fail("%s.exists" % where, "frozen file is missing: %s" % entry["path"])
        return None
    actual = common.sha256_file(path)
    report.check(
        "%s.sha256" % where,
        actual == sha,
        "%s expected %s... got %s..."
        % (entry["path"], sha[:16], actual[:16]),
    )
    return entry["path"], 1


def _check_directory(
    report: common.Report, root: Path, entry: dict, where: str
) -> tuple[str, int] | None:
    path = _relative(root, entry.get("path", ""), where, report)
    if path is None:
        return None
    manifest = entry.get("file_manifest")
    if entry.get("no_new_files") is not True:
        report.fail(
            "%s.no_new_files" % where,
            "a frozen directory entry must declare no_new_files: true",
        )
        return None
    if not isinstance(manifest, list) or not all(
        isinstance(item, str) for item in manifest
    ):
        report.fail("%s.file_manifest" % where, "expected a list of relative paths")
        return None
    if not path.is_dir():
        report.fail(
            "%s.exists" % where, "frozen directory is missing: %s" % entry["path"]
        )
        return None
    actual = _walk_files(path)
    declared = sorted(manifest)
    added = [item for item in actual if item not in set(declared)]
    removed = [item for item in declared if item not in set(actual)]
    report.check(
        "%s.no_new_files" % where,
        not added,
        "new file(s) under %s: %s" % (entry["path"], added) if added else "no new files",
    )
    report.check(
        "%s.no_removed_files" % where,
        not removed,
        "missing file(s) under %s: %s"
        % (entry["path"], removed)
        if removed
        else "no removed files",
    )
    if len(declared) != len(set(declared)):
        report.fail("%s.file_manifest.duplicates" % where, "manifest has duplicate paths")
    return entry["path"], len(actual)


def _print_manifest(root: Path, document: dict) -> int:
    """Print the current directory manifests as YAML for a reviewed re-baseline."""
    entries = document.get("entries") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        print("check_frozen: no directory entries to print", file=sys.stderr)
        return common.EXIT_CONFIG
    output: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") != "directory":
            continue
        path = root / str(entry.get("path", ""))
        output.append(
            {
                "freeze_id": entry.get("freeze_id", "?"),
                "path": entry.get("path", "?"),
                "file_manifest": _walk_files(path) if path.is_dir() else [],
            }
        )
    print(yamlmini.dumps({"directories": output}), end="")
    return common.EXIT_PASS


def build_report(root: Path, frozen_path: Path) -> common.Report:
    report = common.Report(TOOL)
    if not frozen_path.is_file():
        report.fail("frozen.exists", "freeze spec not found: %s" % frozen_path)
        return report
    try:
        document = common.read_yaml(frozen_path)
    except common.ConfigError as exc:
        report.fail("frozen.parse", str(exc))
        return report
    if not isinstance(document, dict):
        report.fail("frozen.parse", "FROZEN.yaml must be a mapping")
        return report
    report.check(
        "frozen.schema",
        document.get("schema") == common.SCHEMA_FROZEN,
        "expected %s, found %r"
        % (common.SCHEMA_FROZEN, document.get("schema")),
    )
    report.check(
        "frozen.frozen_at",
        isinstance(document.get("frozen_at"), str) and document.get("frozen_at"),
        str(document.get("frozen_at", "")),
    )
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        report.fail("frozen.entries", "expected a non-empty 'entries' list")
        return report
    report.check("frozen.entries.nonempty", True, "%d entries" % len(entries))
    seen_ids: dict[str, int] = {}
    seen_paths: dict[str, str] = {}
    frozen_paths: list[tuple[str, int]] = []
    for index, entry in enumerate(entries):
        where = "frozen.entries[%d]" % index
        if not isinstance(entry, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        freeze_id = entry.get("freeze_id")
        if not isinstance(freeze_id, str) or not FREEZE_ID_RE.match(freeze_id):
            report.fail(
                "%s.freeze_id" % where,
                "expected an id like FZ-001, found %r" % (freeze_id,),
            )
        elif freeze_id in seen_ids:
            report.fail(
                "%s.freeze_id.unique" % where,
                "duplicate freeze_id %r (also at entry %d)"
                % (freeze_id, seen_ids[freeze_id]),
            )
        else:
            seen_ids[freeze_id] = index
            report.check("%s.freeze_id" % where, True, freeze_id)
        _study = entry.get("study")
        report.check(
            "%s.study" % where,
            isinstance(_study, str) and bool(_study.strip()),
            str(_study),
        )
        _rationale = entry.get("rationale")
        report.check(
            "%s.rationale" % where,
            isinstance(_rationale, str) and bool(_rationale.strip()),
            str(_rationale)[:90],
        )
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            report.fail("%s.path" % where, "expected a non-empty path")
            continue
        if raw_path in seen_paths:
            report.fail(
                "%s.path.unique" % where,
                "duplicate path %r (also frozen by %s)"
                % (raw_path, seen_paths[raw_path]),
            )
            continue
        seen_paths[raw_path] = str(freeze_id)
        kind = entry.get("kind")
        if kind == "file":
            result = _check_file(report, root, entry, where)
        elif kind == "directory":
            result = _check_directory(report, root, entry, where)
        else:
            report.fail(
                "%s.kind" % where, "expected 'file' or 'directory', found %r" % (kind,)
            )
            result = None
        if result is not None:
            frozen_paths.append(result)
    report.check(
        "frozen.coverage",
        len(frozen_paths) > 0,
        "%d frozen path entries verified; %d file(s) tracked by directory manifests"
        % (len(frozen_paths), sum(count for _, count in frozen_paths)),
    )
    report.check(
        "frozen.entries.unique",
        len(seen_ids) == len(entries),
        "%d entries, %d unique ids" % (len(entries), len(seen_ids)),
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Verify that frozen research files are byte-identical and that no "
            "file was added to or removed from a frozen study directory."
        ),
        epilog=(
            "Exit codes: 0 pass, 1 check failed, 2 configuration error. "
            "Re-baselining a freeze requires a dedicated commit that updates "
            "FROZEN.yaml; --manifest prints the current directory manifests for "
            "review and never writes."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--frozen",
        default=None,
        help="Freeze spec (default: %s)." % common.DEFAULT_FROZEN,
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Print current directory manifests as YAML for a reviewed re-baseline.",
    )
    args = parser.parse_args(argv)

    try:
        root = common.repo_root(args.root)
    except common.ConfigError as exc:
        return common.config_error(TOOL, str(exc))
    frozen_path = Path(args.frozen) if args.frozen else root / common.DEFAULT_FROZEN
    if not frozen_path.is_absolute():
        frozen_path = (root / frozen_path).resolve()

    if args.manifest:
        if not frozen_path.is_file():
            return common.config_error(
                TOOL, "freeze spec not found: %s" % frozen_path
            )
        try:
            document = common.read_yaml(frozen_path)
        except common.ConfigError as exc:
            return common.config_error(TOOL, str(exc))
        return _print_manifest(root, document)

    report = build_report(root, frozen_path)
    return common.emit(report, args.json)


if __name__ == "__main__":
    sys.exit(main())
