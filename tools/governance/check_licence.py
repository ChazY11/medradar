#!/usr/bin/env python3
"""Verify committed data against the licence policy — pattern, inventory and content.

This gate has three layers, in increasing strength:

1. **Pattern tripwire** (Phase 0): a tracked file matching a RED source pattern
   fails; an AMBER match needs an explicit ``policy_entries`` record.
2. **Positive inventory** (Phase 1 hardening): every tracked file with a data
   extension, and every tracked file whose content is a restricted binary
   format, must appear in ``docs/governance/DATA_INVENTORY.yaml``. A file that
   is moved, renamed, or created in a new location is therefore not invisible:
   it has no entry and fails. Entries are reviewed in the commit diff.
3. **Content classification**: the gate sniffs the bytes (SQLite, Parquet, HDF5,
   gzip, zip, ELF, PDF, image, JSON, CSV, text, binary) and compares them with
   the inventory's declared content kind. A ``.csv`` that is really SQLite, or a
   declared CSV whose bytes were swapped for a database, fails.

Scope of the scan
-----------------
* the **final git tree** (``git ls-files``: committed tree plus staged changes),
  reading content from the worktree, so untracked files cannot hide: untracked
  data files are reported separately and fail;
* the **PR diff** against ``--base`` (default ``origin/main``): added, modified,
  renamed and deleted paths are compared with the inventory, so a relocated or
  renamed restricted file cannot slip through as "new path, old story".

What this is not
----------------
This is a **repository consistency control, not a legal guarantee**. It detects
*known* restricted formats and *undeclared* data files; it cannot decide whether
a particular bytes-to-licence combination is lawful. A human review path is
retained:

    python tools/governance/check_licence.py --write-inventory   # regenerate
    python tools/governance/check_licence.py --summary           # human review list

Logs contain paths, formats and reason codes only — never file contents, values
or extracted text (there is a test for that).

Exit codes: 0 pass, 1 check failed, 2 configuration/usage error.

Usage:
    python tools/governance/check_licence.py [--json] [--base origin/main]
    python tools/governance/check_licence.py --write-inventory
    python tools/governance/check_licence.py --summary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:  # ``python tools/governance/check_licence.py``
    from . import common, yamlmini
except ImportError:  # ``python -m tools.governance.check_licence``
    import common  # type: ignore
    import yamlmini  # type: ignore

TOOL = "check_licence"
SCHEMA_POLICY = "medradar.data_licenses.v2"
SCHEMA_INVENTORY = "medradar.data_inventory.v1"
STATUSES = {"GREEN", "AMBER", "RED"}
STATUS_RANK = {"RED": 3, "AMBER": 2, "GREEN": 1}
ENTRY_KINDS = {"derived-aggregate", "derived-report", "metadata", "claims", "index"}

DEFAULT_DATA_EXTENSIONS = [
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".ndjson",
    ".parquet",
    ".arrow",
    ".feather",
    ".sqlite",
    ".db",
    ".duckdb",
    ".h5",
    ".hdf5",
    ".npy",
    ".npz",
    ".bin",
    ".gz",
    ".gzip",
    ".zip",
]

#: Binary formats that are never an allowed committed representation of raw
#: third-party data. They are allowed only for synthetic test fixtures.
DEFAULT_RESTRICTED_KINDS = ["sqlite", "parquet", "hdf5", "gzip", "zip", "elf", "binary"]

#: Formats detected but not restricted (normal repository media).
MEDIA_KINDS = {"png", "jpeg", "gif", "pdf"}


# --------------------------------------------------------------------------
# content classification (pure, testable)
# --------------------------------------------------------------------------


def detect_kind(data: bytes) -> str:
    """Classify *data* by content. Returns a short stable kind string."""
    if not data:
        return "empty"
    if data.startswith(b"SQLite format 3\x00"):
        return "sqlite"
    if data.startswith(b"PAR1"):
        return "parquet"
    if data.startswith(b"\x89HDF\r\n\x1a\n"):
        return "hdf5"
    if data.startswith(b"\x1f\x8b"):
        return "gzip"
    if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
        return "zip"
    if data.startswith(b"\x7fELF"):
        return "elf"
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"GIF8"):
        return "gif"
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return "text"  # UTF-16 text with BOM (e.g. Windows console logs)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        if b"\x00" in data[:64]:
            for encoding in ("utf-16-le", "utf-16-be"):
                try:
                    candidate = data.decode(encoding)
                except UnicodeDecodeError:
                    continue
                sample = candidate[:2000]
                printable = sum(
                    1
                    for char in sample
                    if char.isprintable() or char in "\n\r\t"
                )
                if sample and printable / len(sample) >= 0.90:
                    return "text"
        # Legacy console logs can contain non-UTF-8 bytes; classify by
        # printability so they are not mistaken for restricted binary data.
        sample = data[:4096]
        printable = sum(
            1 for byte in sample if byte in (9, 10, 13) or 32 <= byte < 127 or byte >= 0xA0
        )
        return "text" if sample and printable / len(sample) >= 0.90 else "binary"
    text = text.lstrip("\ufeff")
    stripped = text.lstrip()
    if not stripped:
        return "text"
    if stripped[:1] in "{[":
        try:
            json.loads(text)
            return "json"
        except ValueError:
            pass
    lines = [line for line in text.splitlines()[:5] if line.strip()]
    if len(lines) >= 2:
        for delimiter in (",", ";", "\t"):
            counts = [line.count(delimiter) for line in lines]
            if counts[0] >= 1 and all(count == counts[0] for count in counts):
                return "csv"
    return "text"


def _suffix(path: str) -> str:
    return Path(path).suffix.lower()


# --------------------------------------------------------------------------
# policy and inventory loading
# --------------------------------------------------------------------------


def _string_list(report: common.Report, mapping: dict, key: str, where: str) -> list[str]:
    value = mapping.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    report.fail("%s.%s" % (where, key), "expected a string or list of strings")
    return []


class Policy:
    """Loaded, validated DATA_LICENSES.yml policy."""

    def __init__(self, document: dict, report: common.Report) -> None:
        self.document = document
        self.sources: dict[str, dict] = {}
        self.patterns: list[tuple[str, str, str]] = []  # (pattern, source_id, status)
        self.policy_entries: list[dict] = []
        inventory = document.get("inventory") or {}
        self.inventory_file = str(inventory.get("file") or "docs/governance/DATA_INVENTORY.yaml")
        self.data_extensions = [
            item.lower()
            for item in (inventory.get("data_extensions") or DEFAULT_DATA_EXTENSIONS)
            if isinstance(item, str)
        ]
        self.restricted_kinds = set(
            inventory.get("restricted_content_kinds") or DEFAULT_RESTRICTED_KINDS
        )
        self.manual_review = str(inventory.get("manual_review") or "")
        self.disclaimer = str(inventory.get("disclaimer") or "")
        for index, source in enumerate(document.get("sources") or []):
            where = "sources[%d]" % index
            if not isinstance(source, dict):
                report.fail("%s.type" % where, "expected a mapping")
                continue
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                report.fail("%s.source_id" % where, "missing source_id")
                continue
            if source_id in self.sources:
                report.fail("%s.source_id.unique" % where, "duplicate source_id %r" % source_id)
                continue
            status = source.get("status")
            if status not in STATUSES:
                report.fail("%s.status" % where, "expected GREEN/AMBER/RED, found %r" % (status,))
                continue
            self.sources[source_id] = source
            for pattern in _string_list(report, source, "tracked_patterns", where):
                self.patterns.append((pattern, source_id, status))
        for entry in document.get("policy_entries") or []:
            if isinstance(entry, dict):
                self.policy_entries.append(entry)
        # deterministic classification order: worst status, then longest pattern
        self.patterns.sort(key=lambda item: (-STATUS_RANK[item[2]], -len(item[0]), item[0]))

    def classify(self, path: str) -> tuple[str, str, str] | None:
        for pattern, source_id, status in self.patterns:
            if common.path_matches(pattern, path):
                return source_id, status, pattern
        return None

    def policy_entry_covers(self, source_id: str, path: str) -> bool:
        for entry in self.policy_entries:
            if entry.get("source_id") != source_id:
                continue
            if isinstance(entry.get("path"), str) and entry["path"] == path:
                return True
            if isinstance(entry.get("path_pattern"), str) and common.path_matches(
                entry["path_pattern"], path
            ):
                return True
        return False


def load_inventory(path: Path, report: common.Report) -> dict:
    if not path.is_file():
        report.fail(
            "inventory.exists",
            "data inventory missing: %s (run `python tools/governance/check_licence.py "
            "--write-inventory` and review it)" % path,
        )
        return {"schema": None, "entries": []}
    try:
        document = common.read_yaml(path)
    except common.ConfigError as exc:
        report.fail("inventory.parse", str(exc))
        return {"schema": None, "entries": []}
    if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
        report.fail("inventory.parse", "expected a mapping with an 'entries' list")
        return {"schema": None, "entries": []}
    report.check(
        "inventory.schema",
        document.get("schema") == SCHEMA_INVENTORY,
        "expected %s, found %r" % (SCHEMA_INVENTORY, document.get("schema")),
    )
    by_path: dict[str, dict] = {}
    for index, entry in enumerate(document["entries"]):
        where = "inventory.entries[%d]" % index
        if not isinstance(entry, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        path_value = entry.get("path")
        if not isinstance(path_value, str) or not path_value:
            report.fail("%s.path" % where, "missing path")
            continue
        if path_value in by_path:
            report.fail("%s.path.unique" % where, "duplicate inventory path %r" % path_value)
            continue
        if entry.get("status") not in STATUSES:
            report.fail(
                "%s.status" % where,
                "expected GREEN/AMBER/RED, found %r" % (entry.get("status"),),
            )
            continue
        by_path[path_value] = entry
    report.check("inventory.entries.count", True, "%d declared data files" % len(by_path))
    return {"schema": document.get("schema"), "entries": document["entries"], "by_path": by_path}


# --------------------------------------------------------------------------
# tree / diff scanning
# --------------------------------------------------------------------------


def _read_text_from_git(root: Path, path: str) -> bytes | None:
    code, out, _ = common.run_git(root, "show", ":%s" % path)
    if code != 0:
        return None
    # ``git show :path`` returns text through our subprocess helper; for binary
    # content we fall back to reading the worktree file instead.
    return out.encode("utf-8", errors="surrogateescape")


def tracked_files(root: Path) -> list[str]:
    """Final git tree: committed tree plus staged changes, via the index."""
    try:
        return common.git_tracked_files(root)
    except common.ConfigError as exc:
        raise SystemExit(str(exc))


def untracked_files(root: Path) -> list[str]:
    code, out, _ = common.run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if code != 0:
        return []
    return sorted(entry for entry in out.split("\0") if entry)


def changed_paths(root: Path, base: str) -> tuple[list[str], str | None]:
    """PR-style change set: added/modified/renamed/deleted paths vs *base*."""
    if not base:
        return [], "diff scan disabled"
    if common.git_rev_parse(root, base) is None:
        return [], "base ref %r not found; PR-diff scan skipped" % base
    code, out, err = common.run_git(root, "diff", "--name-only", "--find-renames", base)
    if code != 0:
        return [], "git diff failed: %s" % err.strip()
    paths = {line for line in out.splitlines() if line}
    code, out, _ = common.run_git(root, "diff", "--name-status", "--find-renames", base)
    if code == 0:
        for line in out.splitlines():
            parts = line.split("\t")
            for extra in parts[1:]:
                if extra:
                    paths.add(extra)
    paths.update(untracked_files(root))
    return sorted(paths), None


def read_content(root: Path, path: str) -> bytes:
    target = root / path
    try:
        return target.read_bytes()
    except OSError:
        data = _read_text_from_git(root, path)
        return data or b""


def _is_data_candidate(path: str, policy: Policy, data: bytes) -> bool:
    if _suffix(path) in policy.data_extensions:
        return True
    return detect_kind(data) in policy.restricted_kinds


def _synthetic_entry(entry: dict | None, policy: Policy) -> bool:
    if not entry:
        return False
    source = policy.sources.get(entry.get("source_id"), {})
    return bool(entry.get("synthetic")) and bool(source.get("synthetic"))


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def check_tree(
    root: Path,
    policy: Policy,
    inventory: dict,
    report: common.Report,
) -> tuple[list[tuple[str, bytes]], int]:
    """Inventory coverage + content-kind checks over the final git tree."""
    paths = tracked_files(root)
    by_path = inventory.get("by_path") or {}
    data_files: list[tuple[str, bytes]] = []
    flagged: list[dict] = []
    for path in paths:
        data = read_content(root, path)
        kind = detect_kind(data)
        if not _is_data_candidate(path, policy, data):
            continue
        data_files.append((path, data))
        entry = by_path.get(path)
        if entry is not None and entry.get("status") == "RED":
            report.fail(
                "content.red_source",
                "inventory entry is classified RED and may not be committed: %s "
                "(source %r)" % (path, entry.get("source_id")),
            )
            flagged.append({"path": path, "kind": kind, "reason": "red-source"})
            continue
        if entry is None:
            report.fail(
                "inventory.coverage",
                "tracked data file has no inventory entry: %s (kind=%s); "
                "run --write-inventory and review the diff" % (path, kind),
            )
            if kind in policy.restricted_kinds:
                report.fail(
                    "content.restricted_kind",
                    "restricted binary format is not allowed without a reviewed "
                    "synthetic-fixture declaration: %s (%s); raw data belongs in "
                    "gitignored data/" % (path, kind),
                )
            flagged.append({"path": path, "kind": kind, "reason": "not-in-inventory"})
            continue
        declared = entry.get("content")
        if declared != kind:
            report.fail(
                "inventory.content_match",
                "content kind changed since inventory: %s declared=%r detected=%r"
                % (path, declared, kind),
            )
            flagged.append({"path": path, "kind": kind, "reason": "content-mismatch"})
            continue
        if kind in policy.restricted_kinds and not _synthetic_entry(entry, policy):
            report.fail(
                "content.restricted_kind",
                "restricted binary format committed outside synthetic fixtures: %s (%s)"
                % (path, kind),
            )
            flagged.append({"path": path, "kind": kind, "reason": "restricted-kind"})
            continue
        if kind in MEDIA_KINDS and _suffix(path) not in policy.data_extensions:
            continue
        # extension masquerade: declared database/archive extensions must match
        expected = {
            ".sqlite": "sqlite",
            ".db": "sqlite",
            ".duckdb": "sqlite",
            ".parquet": "parquet",
            ".h5": "hdf5",
            ".hdf5": "hdf5",
            ".gz": "gzip",
            ".gzip": "gzip",
            ".zip": "zip",
        }.get(_suffix(path))
        if expected is not None and kind != expected and not _synthetic_entry(entry, policy):
            report.fail(
                "inventory.extension_masquerade",
                "extension masquerade: %s looks like %s but content is %s"
                % (path, expected, kind),
            )
            flagged.append({"path": path, "kind": kind, "reason": "extension-masquerade"})
    report.check(
        "tree.data_files",
        True,
        "%d tracked data-like files classified, %d flagged"
        % (len(data_files), len(flagged)),
    )
    # inventory entries that no longer exist are stale (renamed/deleted files)
    tracked_set = set(paths)
    stale = [path for path in by_path if path not in tracked_set]
    if stale:
        for path in sorted(stale):
            report.fail(
                "inventory.stale_entry",
                "inventory lists a file that is no longer tracked: %s "
                "(deletion/rename must update the inventory)" % path,
            )
    else:
        report.check("inventory.stale_entry", True, "no stale inventory entries")
    return data_files, len(flagged)


def check_whitelist_sources(
    root: Path, policy: Policy, report: common.Report
) -> list[tuple[str, str]]:
    """Legacy source-pattern rules, computed from the inventory for transparency."""
    violations: list[tuple[str, str]] = []
    for path in tracked_files(root):
        match = policy.classify(path)
        if match is None:
            continue
        source_id, status, _pattern = match
        if status == "RED":
            violations.append((path, source_id))
        elif status == "AMBER":
            if not policy.policy_entry_covers(source_id, path):
                violations.append((path, source_id))
    if violations:
        for path, source_id in violations:
            report.fail(
                "source.pattern",
                "RESTRICTED/AMBER source %r has a tracked file without a policy "
                "entry: %s" % (source_id, path),
            )
    else:
        report.check("source.pattern", True, "no RED/AMBER pattern violations")
    return violations


def check_untracked(root: Path, policy: Policy, report: common.Report) -> list[str]:
    offenders: list[str] = []
    for path in untracked_files(root):
        data = read_content(root, path)
        if not _is_data_candidate(path, policy, data):
            continue
        offenders.append(path)
        report.fail(
            "untracked.data_file",
            "untracked data file is not in the final tree and could hide: %s (%s); "
            "add it (with inventory) or remove it" % (path, detect_kind(data)),
        )
    if not offenders:
        report.check("untracked.data_file", True, "no untracked data files")
    return offenders


def check_diff(
    root: Path,
    policy: Policy,
    inventory: dict,
    base: str,
    report: common.Report,
) -> tuple[list[str], str | None]:
    paths, note = changed_paths(root, base)
    if note:
        report.warn(note)
        return paths, note
    by_path = inventory.get("by_path") or {}
    data_changes = 0
    for path in paths:
        if not (root / path).is_file():
            continue
        data = read_content(root, path)
        if not _is_data_candidate(path, policy, data):
            continue
        data_changes += 1
        entry = by_path.get(path)
        if entry is not None and entry.get("status") == "RED":
            report.fail(
                "content.red_source",
                "inventory entry is classified RED and may not be committed: %s "
                "(source %r)" % (path, entry.get("source_id")),
            )
            flagged.append({"path": path, "kind": kind, "reason": "red-source"})
            continue
        if entry is None:
            report.fail(
                "diff.changed_data_file",
                "PR changes a data file with no inventory entry: %s" % path,
            )
            continue
        kind = detect_kind(data)
        if entry.get("content") != kind:
            report.fail(
                "diff.changed_content",
                "PR changes a declared data file to a different content kind: %s "
                "declared=%r detected=%r" % (path, entry.get("content"), kind),
            )
    report.check(
        "diff.scanned",
        True,
        "%d changed path(s) vs %s, %d data file(s)" % (len(paths), base, data_changes),
    )
    return paths, None


# --------------------------------------------------------------------------
# inventory generation
# --------------------------------------------------------------------------


def generate_inventory(root: Path, policy: Policy) -> dict:
    entries: list[dict] = []
    for path in tracked_files(root):
        data = read_content(root, path)
        kind = detect_kind(data)
        if not _is_data_candidate(path, policy, data):
            continue
        match = policy.classify(path)
        if match is None:
            source_id, status = "unclassified", "RED"
            synthetic = False
        else:
            source_id, status, _pattern = match
            synthetic = bool(policy.sources.get(source_id, {}).get("synthetic"))
        entries.append(
            {
                "path": path,
                "source_id": source_id,
                "status": status,
                "content": kind,
                "synthetic": synthetic,
            }
        )
    return {
        "schema": SCHEMA_INVENTORY,
        "generated_by": "tools/governance/check_licence.py --write-inventory",
        "note": (
            "Positive inventory of committed data files. Any added, moved, renamed "
            "or content-changed data file must update this file in the same PR. "
            "This is a repository control, not a legal guarantee."
        ),
        "entries": entries,
    }


def write_inventory(root: Path, policy: Policy, path: Path) -> int:
    document = generate_inventory(root, policy)
    payload = (
        "# MedRadar data inventory — generated; review every change in the PR.\n"
        "# Regenerate only with: python tools/governance/check_licence.py --write-inventory\n"
        "# This is a repository consistency control, not a legal guarantee.\n"
        + yamlmini.dumps(document)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8", newline="\n")
    kinds: dict[str, int] = {}
    for entry in document["entries"]:
        kinds[entry["content"]] = kinds.get(entry["content"], 0) + 1
    print(
        "%s: wrote %s (%d data files: %s)"
        % (
            TOOL,
            path,
            len(document["entries"]),
            ", ".join("%s=%d" % (kind, count) for kind, count in sorted(kinds.items())),
        )
    )
    print("Review the diff before committing; entries must be classified by a human.")
    return common.EXIT_PASS


# --------------------------------------------------------------------------
# report / CLI
# --------------------------------------------------------------------------


def _check_policy_sections(report: common.Report, document: dict, root: Path) -> None:
    report.check(
        "policy.schema",
        document.get("schema") == SCHEMA_POLICY,
        "expected %s, found %r" % (SCHEMA_POLICY, document.get("schema")),
    )
    inventory = document.get("inventory")
    if not isinstance(inventory, dict):
        report.fail("policy.inventory", "expected an 'inventory' mapping")
        return
    report.check(
        "policy.inventory.manual_review",
        isinstance(inventory.get("manual_review"), str) and inventory["manual_review"].strip() != "",
        "manual review path documented",
    )
    report.check(
        "policy.inventory.disclaimer",
        isinstance(inventory.get("disclaimer"), str) and "legal guarantee" in inventory["disclaimer"],
        "disclaimer says this is not a legal guarantee",
    )
    report.check(
        "policy.inventory.data_extensions",
        isinstance(inventory.get("data_extensions"), list) and len(inventory["data_extensions"]) > 0,
        "%d data extensions" % len(inventory.get("data_extensions") or []),
    )
    policy = document.get("policy") or {}
    raw_root = str(policy.get("raw_root") or "data/")
    if not raw_root.endswith("/"):
        raw_root += "/"
    report.check(
        "policy.raw_root",
        raw_root == "data/",
        "raw data root=%r (RED content may only live under data/)" % raw_root,
    )
    code, _, _ = common.run_git(root, "check-ignore", "-q", raw_root)
    report.check(
        "policy.raw_root.gitignored",
        code == 0,
        "%s is %s by .gitignore" % (raw_root, "ignored" if code == 0 else "NOT ignored"),
    )


def build_report(
    root: Path,
    licences_path: Path,
    *,
    base: str | None = "origin/main",
    summary_only: bool = False,
) -> common.Report:
    report = common.Report(TOOL)
    if not licences_path.is_file():
        report.fail("policy.exists", "licence policy not found: %s" % licences_path)
        return report
    try:
        document = common.read_yaml(licences_path)
    except common.ConfigError as exc:
        report.fail("policy.parse", str(exc))
        return report
    if not isinstance(document, dict):
        report.fail("policy.parse", "DATA_LICENSES.yaml must be a mapping")
        return report
    _check_policy_sections(report, document, root)
    policy = Policy(document, report)
    inventory_path = (root / policy.inventory_file).resolve()
    inventory = load_inventory(inventory_path, report)
    data_files, flagged = check_tree(root, policy, inventory, report)
    check_whitelist_sources(root, policy, report)
    check_untracked(root, policy, report)
    if not summary_only:
        check_diff(root, policy, inventory, base or "", report)
    if policy.manual_review:
        report.warn("manual review path: %s" % policy.manual_review)
    report.check(
        "scan.coverage",
        True,
        "%d data-like files scanned; restricted formats: %s"
        % (len(data_files), ", ".join(sorted(policy.restricted_kinds))),
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Verify committed data files against DATA_LICENSES.yaml using a "
            "positive inventory plus content/magic-byte classification, and scan "
            "the PR diff against a base ref. This is a repository control, not a "
            "legal guarantee."
        ),
        epilog=(
            "Exit codes: 0 pass, 1 check failed, 2 configuration error. "
            "Manual review: --summary prints the inventory classification; "
            "--write-inventory regenerates the inventory for review."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--licences",
        default=None,
        help="Licence policy (default: %s)." % common.DEFAULT_LICENCES,
    )
    parser.add_argument(
        "--inventory",
        default=None,
        help="Override the inventory path from the policy.",
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref for the PR-diff scan (default: origin/main; '' disables).",
    )
    parser.add_argument(
        "--write-inventory",
        action="store_true",
        help="Regenerate the positive inventory from the final git tree (review the diff).",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Human review list: print the inventory classification, skip the diff scan.",
    )
    args = parser.parse_args(argv)

    try:
        root = common.repo_root(args.root)
    except common.ConfigError as exc:
        return common.config_error(TOOL, str(exc))
    licences_path = Path(args.licences) if args.licences else root / common.DEFAULT_LICENCES
    if not licences_path.is_absolute():
        licences_path = (root / licences_path).resolve()
    if not licences_path.is_file():
        return common.config_error(TOOL, "licence policy not found: %s" % licences_path)
    try:
        document = common.read_yaml(licences_path)
    except common.ConfigError as exc:
        return common.config_error(TOOL, str(exc))
    report = common.Report(TOOL)
    _check_policy_sections(report, document, root)
    policy = Policy(document, report)
    inventory_path = (
        Path(args.inventory)
        if args.inventory
        else (root / policy.inventory_file)
    )
    if not inventory_path.is_absolute():
        inventory_path = (root / inventory_path).resolve()

    if args.write_inventory:
        if not report.ok:
            return common.emit(report, args.json)
        return write_inventory(root, policy, inventory_path)

    if args.summary:
        inventory = load_inventory(inventory_path, report)
        print("inventory: %s" % inventory_path.relative_to(root))
        by_source: dict[str, int] = {}
        for entry in inventory.get("entries") or []:
            by_source[entry.get("source_id", "?")] = by_source.get(entry.get("source_id", "?"), 0) + 1
        for source_id in sorted(by_source):
            print("  %-28s %d" % (source_id, by_source[source_id]))
        print("Manual review path: %s" % (policy.manual_review or "not documented"))
        return common.emit(report, args.json)

    report = build_report(
        root, licences_path, base=args.base or None, summary_only=False
    )
    return common.emit(report, args.json)


if __name__ == "__main__":
    sys.exit(main())
