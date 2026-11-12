#!/usr/bin/env python3
"""Verify frozen research artifacts: content digests, manifests and re-baselines.

What this gate blocks
---------------------
1. **Content change** — any file listed in ``docs/governance/FROZEN.yaml`` whose
   SHA-256 no longer matches (including files inside a frozen directory: the
   manifest carries a digest per file, so a name-only edit no longer hides).
2. **Structure change** — a file added to or removed from a frozen directory.
3. **Unapproved re-baseline** — when run with ``--base <ref>`` (default
   ``origin/main``), every changed digest or manifest entry must be covered by a
   ``rebalances:`` record whose ``decision_id`` exists in the decision record
   (``research/DECISIONS.md``) or the governance decision log
   (``docs/governance/DECISION_LOG.yaml``), with matching ``previous_sha256`` /
   ``new_sha256``. Editing a frozen file and updating its digest in the same
   commit is therefore visible and must cite an approved decision.

Coverage: the registered study directory, ``research/forecasts/`` (a new
forecast set is an unreviewed addition) and ``papers/CLAIMS.json`` (the
machine-verified claim map). Adding a new *top-level* freeze entry is allowed
(strengthening); changing or removing one requires a rebalance.

Exit codes: 0 pass, 1 check failed, 2 configuration/usage error.

Usage:
    python tools/governance/check_frozen.py [--json]
    python tools/governance/check_frozen.py --base origin/main
    python tools/governance/check_frozen.py --manifest   # print current manifests
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import sys
from pathlib import Path

try:  # ``python tools/governance/check_frozen.py``
    from . import common, yamlmini
except ImportError:  # ``python -m tools.governance.check_frozen``
    import common  # type: ignore
    import yamlmini  # type: ignore

TOOL = "check_frozen"
SCHEMA_FROZEN = "medradar.frozen.v2"
FREEZE_ID_RE = re.compile(r"\AFZ-[0-9]{3}\Z")
DECISION_RE = re.compile(r"^## (D-[0-9]{3})\b", re.MULTILINE)
SHA_RE = re.compile(r"\A[0-9a-f]{64}\Z")
DEFAULT_DECISIONS = "research/DECISIONS.md"
DEFAULT_DECISION_LOG = "docs/governance/DECISION_LOG.yaml"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, raw: str, where: str, report: common.Report) -> Path | None:
    if not isinstance(raw, str) or not raw:
        report.fail("%s.path" % where, "expected a non-empty path")
        return None
    if raw.startswith("/") or re.match(r"\A[A-Za-z]:[\\/]", raw):
        report.fail("%s.path" % where, "absolute path is not allowed: %r" % raw)
        return None
    if ".." in Path(raw).parts:
        report.fail("%s.path" % where, "path must stay inside the repository: %r" % raw)
        return None
    return root / raw


# --------------------------------------------------------------------------
# current-state validation
# --------------------------------------------------------------------------


def _check_file_entry(
    report: common.Report, root: Path, entry: dict, where: str
) -> tuple[str, str] | None:
    path = _relative(root, entry.get("path"), where, report)
    sha = entry.get("sha256")
    if path is None:
        return None
    if not isinstance(sha, str) or not SHA_RE.match(sha):
        report.fail("%s.sha256" % where, "expected 64 lowercase hex characters")
        return None
    if not path.is_file():
        report.fail("%s.exists" % where, "frozen file is missing: %s" % entry["path"])
        return None
    actual = _sha256(path)
    report.check(
        "%s.sha256" % where,
        actual == sha,
        "%s expected %s... got %s..."
        % (entry["path"], sha[:16], actual[:16]),
    )
    return entry["path"], actual


def _manifest_map(
    report: common.Report, root: Path, entry: dict, where: str
) -> dict[str, str] | None:
    """Validate a directory entry's per-file manifest and return {rel: sha}."""
    if entry.get("no_new_files") is not True:
        report.fail(
            "%s.no_new_files" % where,
            "a frozen directory entry must declare no_new_files: true",
        )
    files = entry.get("files")
    if not isinstance(files, list) or not files:
        report.fail("%s.files" % where, "expected a non-empty per-file manifest")
        return None
    directory = _relative(root, entry.get("path"), where, report)
    if directory is None:
        return None
    if not directory.is_dir():
        report.fail("%s.exists" % where, "frozen directory is missing: %s" % entry["path"])
        return None
    declared: dict[str, str] = {}
    for index, item in enumerate(files):
        item_where = "%s.files[%d]" % (where, index)
        if not isinstance(item, dict):
            report.fail("%s.type" % item_where, "expected a mapping")
            continue
        rel = item.get("path")
        sha = item.get("sha256")
        if not isinstance(rel, str) or not rel or ".." in Path(rel).parts:
            report.fail("%s.path" % item_where, "expected a relative path")
            continue
        if not isinstance(sha, str) or not SHA_RE.match(sha):
            report.fail("%s.sha256" % item_where, "expected 64 lowercase hex characters")
            continue
        if rel in declared:
            report.fail("%s.duplicate" % item_where, "duplicate manifest path %r" % rel)
            continue
        declared[rel] = sha
    actual_files = sorted(
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    )
    added = [rel for rel in actual_files if rel not in declared]
    removed = [rel for rel in declared if rel not in actual_files]
    if added:
        report.fail(
            "%s.no_new_files" % where,
            "new file(s) under %s: %s" % (entry["path"], added),
        )
    else:
        report.check("%s.no_new_files" % where, True, "no new files")
    if removed:
        report.fail(
            "%s.no_removed_files" % where,
            "missing file(s) under %s: %s" % (entry["path"], removed),
        )
    else:
        report.check("%s.no_removed_files" % where, True, "no removed files")
    mismatches = 0
    for rel in sorted(set(declared) & set(actual_files)):
        actual = _sha256(directory / rel)
        if actual != declared[rel]:
            mismatches += 1
            report.fail(
                "%s.files[%s].sha256" % (where, rel),
                "%s/%s expected %s... got %s..."
                % (entry["path"], rel, declared[rel][:16], actual[:16]),
            )
    if not mismatches:
        report.check("%s.files.sha256" % where, True, "%d file digests match" % len(declared))
    return declared


def _current_state(
    report: common.Report, root: Path, document: dict
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    files: dict[str, str] = {}
    directories: dict[str, dict[str, str]] = {}
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        report.fail("frozen.entries", "expected a non-empty 'entries' list")
        return files, directories
    report.check("frozen.entries.count", True, "%d entries" % len(entries))
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        where = "frozen.entries[%d]" % index
        if not isinstance(entry, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        freeze_id = entry.get("freeze_id")
        if not isinstance(freeze_id, str) or not FREEZE_ID_RE.match(freeze_id):
            report.fail("%s.freeze_id" % where, "expected an id like FZ-001")
        elif freeze_id in seen_ids:
            report.fail("%s.freeze_id.unique" % where, "duplicate id %r" % freeze_id)
        else:
            seen_ids.add(freeze_id)
        report.check(
            "%s.study" % where,
            isinstance(entry.get("study"), str) and bool(entry["study"].strip()),
            str(entry.get("study")),
        )
        report.check(
            "%s.rationale" % where,
            isinstance(entry.get("rationale"), str) and bool(entry["rationale"].strip()),
            str(entry.get("rationale"))[:90],
        )
        kind = entry.get("kind")
        if kind == "file":
            result = _check_file_entry(report, root, entry, where)
            if result:
                path, sha = result
                if path in files:
                    report.fail("%s.path.unique" % where, "duplicate frozen path %r" % path)
                files[path] = sha
        elif kind == "directory":
            manifest = _manifest_map(report, root, entry, where)
            if manifest is not None:
                path = entry["path"]
                if path in directories:
                    report.fail("%s.path.unique" % where, "duplicate frozen dir %r" % path)
                directories[path] = manifest
        else:
            report.fail("%s.kind" % where, "expected 'file' or 'directory', found %r" % (kind,))
    return files, directories


# --------------------------------------------------------------------------
# decisions and rebalances
# --------------------------------------------------------------------------


def _decision_ids(root: Path, document: dict) -> set[str]:
    ids: set[str] = set()
    decisions_file = str(document.get("decisions_file") or DEFAULT_DECISIONS)
    path = root / decisions_file
    if path.is_file():
        ids.update(DECISION_RE.findall(path.read_text(encoding="utf-8", errors="replace")))
    log_path = root / str(document.get("decision_log_file") or DEFAULT_DECISION_LOG)
    if log_path.is_file():
        try:
            log = common.read_yaml(log_path)
        except common.ConfigError:
            log = None
        if isinstance(log, dict):
            for entry in log.get("decisions") or []:
                if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                    ids.add(entry["id"])
    return ids


def _valid_rebalances(
    report: common.Report, document: dict, decision_ids: set[str]
) -> list[dict]:
    rebalances = document.get("rebalances")
    if rebalances is None:
        rebalances = []
    if not isinstance(rebalances, list):
        report.fail("frozen.rebalances", "expected a list")
        return []
    valid: list[dict] = []
    for index, record in enumerate(rebalances):
        where = "rebalances[%d]" % index
        if not isinstance(record, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        path = record.get("path")
        previous = record.get("previous_sha256")
        new = record.get("new_sha256")
        decision_id = record.get("decision_id")
        date = record.get("date")
        reason = record.get("reason")
        approved_by = record.get("approved_by")
        ok = True
        ok &= report.check(
            "%s.path" % where,
            isinstance(path, str) and bool(path) and ".." not in Path(path).parts,
            str(path),
        )
        ok &= report.check(
            "%s.previous_sha256" % where,
            previous is None or (isinstance(previous, str) and SHA_RE.match(previous)),
            str(previous),
        )
        ok &= report.check(
            "%s.new_sha256" % where,
            new is None or (isinstance(new, str) and SHA_RE.match(new)),
            str(new),
        )
        ok &= report.check(
            "%s.transition" % where,
            previous != new,
            "previous and new digests differ",
        )
        ok &= report.check(
            "%s.decision_id" % where,
            isinstance(decision_id, str) and bool(decision_id.strip()),
            str(decision_id),
        )
        ok &= report.check(
            "%s.decision_id.exists" % where,
            isinstance(decision_id, str) and decision_id in decision_ids,
            "%r is %s a recorded decision id"
            % (decision_id, "not" if decision_id not in decision_ids else ""),
        )
        ok &= report.check(
            "%s.approved_by" % where,
            isinstance(approved_by, str) and bool(approved_by.strip()),
            str(approved_by),
        )
        if isinstance(date, str):
            try:
                dt.date.fromisoformat(date)
                report.check("%s.date" % where, True, date)
            except ValueError:
                ok &= report.check("%s.date" % where, False, "expected YYYY-MM-DD")
        else:
            ok &= report.check("%s.date" % where, False, "missing date")
        ok &= report.check(
            "%s.reason" % where,
            isinstance(reason, str) and bool(reason.strip()),
            str(reason)[:90],
        )
        if ok:
            valid.append(record)
    report.check(
        "frozen.rebalances.count", True, "%d valid rebalance record(s)" % len(valid)
    )
    return valid


def _load_base_state(
    root: Path, frozen_path: Path, base: str | None
) -> tuple[dict[str, str], dict[str, dict[str, str]]] | None:
    if not base:
        return None
    if common.git_rev_parse(root, base) is None:
        return None
    rel = frozen_path.relative_to(root).as_posix()
    code, out, _ = common.run_git(root, "show", "%s:%s" % (base, rel))
    if code != 0:
        return None
    try:
        document = yamlmini.loads(out, path="%s:%s" % (base, rel))
    except yamlmini.YamlSubsetError:
        return None
    if not isinstance(document, dict) or document.get("schema") != SCHEMA_FROZEN:
        return None
    noop = common.Report("base")
    files: dict[str, str] = {}
    directories: dict[str, dict[str, str]] = {}
    for entry in document.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if entry.get("kind") == "file" and isinstance(path, str):
            files[path] = str(entry.get("sha256"))
        elif entry.get("kind") == "directory" and isinstance(path, str):
            manifest = entry.get("files") or []
            directories[path] = {
                item["path"]: item["sha256"]
                for item in manifest
                if isinstance(item, dict)
                and isinstance(item.get("path"), str)
                and isinstance(item.get("sha256"), str)
            }
    return files, directories


def _audit_rebaselines(
    report: common.Report,
    root: Path,
    frozen_path: Path,
    document: dict,
    current: tuple[dict[str, str], dict[str, dict[str, str]]],
    base: str | None,
) -> int:
    base_state = _load_base_state(root, frozen_path, base)
    if base_state is None:
        report.warn(
            "rebalance audit skipped: base %r is missing or uses an older "
            "FROZEN.yaml schema" % (base,)
        )
        return 0
    current_files, current_dirs = current
    base_files, base_dirs = base_state
    changes: list[dict] = []
    for path, sha in current_files.items():
        if path in base_files and base_files[path] != sha:
            changes.append({"path": path, "previous": base_files[path], "new": sha})
        elif path not in base_files:
            # new top-level freeze entry = new coverage (strengthening)
            continue
    for path in base_files:
        if path not in current_files:
            changes.append({"path": path, "previous": base_files[path], "new": None})
    for directory, manifest in current_dirs.items():
        base_manifest = base_dirs.get(directory)
        if base_manifest is None:
            continue  # new directory coverage
        for rel, sha in manifest.items():
            full = "%s/%s" % (directory, rel)
            if rel in base_manifest and base_manifest[rel] != sha:
                changes.append({"path": full, "previous": base_manifest[rel], "new": sha})
            elif rel not in base_manifest:
                changes.append({"path": full, "previous": None, "new": sha})
        for rel, sha in base_manifest.items():
            if rel not in manifest:
                changes.append(
                    {"path": "%s/%s" % (directory, rel), "previous": sha, "new": None}
                )
    if not changes:
        report.check("rebalance.required", True, "no frozen artifact changed vs %s" % base)
        return 0
    valid = _valid_rebalances(report, document, _decision_ids(root, document))
    uncovered = []
    for change in changes:
        matched = False
        for record in valid:
            if record.get("path") != change["path"]:
                continue
            if record.get("previous_sha256") != change["previous"]:
                continue
            if record.get("new_sha256") != change["new"]:
                continue
            matched = True
            break
        if not matched:
            uncovered.append(change)
    if uncovered:
        for change in uncovered:
            report.fail(
                "rebalance.unapproved",
                "frozen artifact changed without an approved rebalance record: %s "
                "(previous=%s new=%s); add a `rebalances:` entry with a decision_id"
                % (
                    change["path"],
                    (change["previous"] or "none")[:12],
                    (change["new"] or "none")[:12],
                ),
            )
    else:
        report.check(
            "rebalance.approved",
            True,
            "%d frozen change(s) covered by approved rebalance records" % len(changes),
        )
    return len(changes)


def build_report(root: Path, frozen_path: Path, base: str | None = "origin/main") -> common.Report:
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
        document.get("schema") == SCHEMA_FROZEN,
        "expected %s, found %r" % (SCHEMA_FROZEN, document.get("schema")),
    )
    report.check(
        "frozen.frozen_at",
        isinstance(document.get("frozen_at"), str) and bool(document.get("frozen_at")),
        str(document.get("frozen_at", "")),
    )
    current = _current_state(report, root, document)
    _valid_rebalances(report, document, _decision_ids(root, document))
    _audit_rebaselines(report, root, frozen_path, document, current, base)
    report.check(
        "frozen.coverage",
        True,
        "%d hashed file entries, %d directory manifests (%d files)"
        % (
            len(current[0]),
            len(current[1]),
            sum(len(files) for files in current[1].values()),
        ),
    )
    return report


# --------------------------------------------------------------------------
# manifest printer (for a reviewed re-baseline)
# --------------------------------------------------------------------------


def print_manifest(root: Path, frozen_path: Path) -> int:
    try:
        document = common.read_yaml(frozen_path)
    except (OSError, common.ConfigError) as exc:
        print("%s: ERROR: %s" % (TOOL, exc), file=sys.stderr)
        return common.EXIT_CONFIG
    if not isinstance(document, dict):
        print("%s: ERROR: FROZEN.yaml must be a mapping" % TOOL, file=sys.stderr)
        return common.EXIT_CONFIG
    output: list[dict] = []
    for entry in document.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("kind") != "directory":
            continue
        directory = root / str(entry.get("path"))
        files = []
        if directory.is_dir():
            files = [
                {"path": path.relative_to(directory).as_posix(), "sha256": _sha256(path)}
                for path in sorted(directory.rglob("*"))
                if path.is_file()
            ]
        output.append(
            {"freeze_id": entry.get("freeze_id"), "path": entry.get("path"), "files": files}
        )
    print(yamlmini.dumps({"directories": output}), end="")
    return common.EXIT_PASS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Verify frozen research artifacts: per-file SHA-256 manifests, "
            "directory structure and approved re-baselines against a base ref."
        ),
        epilog=(
            "Exit codes: 0 pass, 1 check failed, 2 configuration error. "
            "Changing a frozen artifact requires a FROZEN.yaml `rebalances:` "
            "record with a decision_id; --manifest prints current manifests."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--frozen",
        default=None,
        help="Freeze spec (default: %s)." % common.DEFAULT_FROZEN,
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref for the re-baseline audit (default: origin/main; '' disables).",
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Print current directory manifests (for a reviewed re-baseline).",
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
        return print_manifest(root, frozen_path)
    report = build_report(root, frozen_path, base=args.base or None)
    return common.emit(report, args.json)


if __name__ == "__main__":
    sys.exit(main())
