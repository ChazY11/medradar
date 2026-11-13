#!/usr/bin/env python3
"""Audit changes to the governance rules themselves.

A gate that can be weakened silently is not a gate. This gate fails when the
governance surface changes without an accompanying, approved rule-change record:

Protected paths
---------------
* ``.github/workflows/governance.yml`` — the CI that runs the gates;
* ``tools/governance/**`` — the gate implementations;
* ``docs/governance/DATA_LICENSES.yaml`` and ``docs/governance/FROZEN.yaml`` —
  the licence/freeze rules.

Excluded (audit inputs, not rules): ``docs/governance/RULE_CHANGES.yaml`` (the
record being validated), ``docs/governance/DECISION_LOG.yaml`` (the approval
record) and ``docs/governance/DATA_INVENTORY.yaml`` (generated data manifest —
its content is still enforced by ``check_licence.py``).

How a change is approved
------------------------
The change must add a record to ``docs/governance/RULE_CHANGES.yaml`` that is
**new relative to the base ref** and covers every changed protected path. Each
record must have:

* a unique ``change_id``;
* a ``decision_id`` that exists as ``## D-nnn`` in ``research/DECISIONS.md`` or
  as an ``id`` in ``docs/governance/DECISION_LOG.yaml``;
* ``approved_by``, ``date`` and ``reason``;
* a non-empty ``paths`` list of repository-relative globs.

Limitation: this gate makes weakening explicit and reviewable; it does not
cryptographically verify who approved a decision. A maintainer with write access
can still forge an approval — what it removes is the *silent* weakening path
for an agent.

Exit codes: 0 pass, 1 check failed, 2 configuration/usage error.

Usage:
    python tools/governance/check_rule_audit.py [--json] [--base origin/main]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

try:  # ``python tools/governance/check_rule_audit.py``
    from . import common, yamlmini
except ImportError:  # ``python -m tools.governance.check_rule_audit``
    import common  # type: ignore
    import yamlmini  # type: ignore

TOOL = "check_rule_audit"
SCHEMA_RULES = "medradar.rule_changes.v1"
SCHEMA_DECISION_LOG = "medradar.decision_log.v1"
CHANGE_ID_RE = re.compile(r"\ARC-[0-9]{4}\Z")
DECISION_HEADING_RE = re.compile(r"^## (D-[0-9]{3})\b", re.MULTILINE)

PROTECTED_GLOBS = [
    ".github/workflows/governance.yml",
    "tools/governance/**",
    "docs/governance/DATA_LICENSES.yaml",
    "docs/governance/FROZEN.yaml",
]
EXCLUDED_GLOBS = [
    "docs/governance/RULE_CHANGES.yaml",
    "docs/governance/DECISION_LOG.yaml",
    "docs/governance/DATA_INVENTORY.yaml",
]
DEFAULT_RULES = "docs/governance/RULE_CHANGES.yaml"
DEFAULT_DECISION_LOG = "docs/governance/DECISION_LOG.yaml"
DEFAULT_DECISIONS = "research/DECISIONS.md"


def _is_protected(path: str) -> bool:
    if common.path_matches_any(EXCLUDED_GLOBS, path):
        return False
    return common.path_matches_any(PROTECTED_GLOBS, path)


def _changed_paths(root: Path, base: str | None, report: common.Report) -> list[str]:
    if not base:
        report.warn("base ref disabled; protected changes cannot be detected")
        return []
    if common.git_rev_parse(root, base) is None:
        report.fail(
            "base.resolve",
            "cannot resolve base ref %r; a rule audit needs the base commit" % base,
        )
        return []
    code, out, err = common.run_git(root, "diff", "--name-status", "--find-renames", base)
    if code != 0:
        report.fail("diff.scan", "git diff failed: %s" % err.strip())
        return []
    paths: set[str] = set()
    for line in out.splitlines():
        parts = line.split("\t")
        for path in parts[1:]:
            if path:
                paths.add(path)
    code, out, _ = common.run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if code == 0:
        for path in out.split("\0"):
            if path:
                paths.add(path)
    protected = sorted(path for path in paths if _is_protected(path))
    report.check(
        "diff.changed",
        True,
        "%d changed path(s), %d protected; protected: %s"
        % (len(paths), len(protected), ", ".join(protected) if protected else "none"),
    )
    return protected


def _load_document(path: Path, report: common.Report, label: str):
    if not path.is_file():
        return None
    try:
        return common.read_yaml(path)
    except common.ConfigError as exc:
        report.fail("%s.parse" % label, str(exc))
        return None


def _base_change_ids(root: Path, rules_path: Path, base: str | None) -> set[str]:
    if not base or common.git_rev_parse(root, base) is None:
        return set()
    try:
        rel = rules_path.relative_to(root).as_posix()
    except ValueError:
        return set()
    code, out, _ = common.run_git(root, "show", "%s:%s" % (base, rel))
    if code != 0:
        return set()
    try:
        document = yamlmini.loads(out, path="%s:%s" % (base, rel))
    except yamlmini.YamlSubsetError:
        return set()
    ids: set[str] = set()
    if isinstance(document, dict):
        for record in document.get("changes") or []:
            if isinstance(record, dict) and isinstance(record.get("change_id"), str):
                ids.add(record["change_id"])
    return ids


def _decision_ids(root: Path, decisions_file: str, log_path: Path) -> tuple[set[str], int]:
    ids: set[str] = set()
    count = 0
    path = root / decisions_file
    if path.is_file():
        found = DECISION_HEADING_RE.findall(path.read_text(encoding="utf-8", errors="replace"))
        ids.update(found)
        count += len(found)
    log = None
    if log_path.is_file():
        try:
            log = common.read_yaml(log_path)
        except common.ConfigError:
            log = None
    if isinstance(log, dict):
        for entry in log.get("decisions") or []:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                ids.add(entry["id"])
                count += 1
    return ids, count


def _validate_records(
    report: common.Report,
    document: dict,
    decision_ids: set[str],
) -> list[dict]:
    report.check(
        "rules.schema",
        document.get("schema") == SCHEMA_RULES,
        "expected %s, found %r" % (SCHEMA_RULES, document.get("schema")),
    )
    changes = document.get("changes")
    if not isinstance(changes, list):
        report.fail("rules.changes", "expected a 'changes' list")
        return []
    seen: set[str] = set()
    valid: list[dict] = []
    for index, record in enumerate(changes):
        where = "rules.changes[%d]" % index
        if not isinstance(record, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        change_id = record.get("change_id")
        ok = True
        ok &= report.check(
            "%s.change_id" % where,
            isinstance(change_id, str) and bool(CHANGE_ID_RE.match(change_id)),
            str(change_id),
        )
        if isinstance(change_id, str):
            if change_id in seen:
                ok &= report.check("%s.unique" % where, False, "duplicate %r" % change_id)
            seen.add(change_id)
        decision_id = record.get("decision_id")
        ok &= report.check(
            "%s.decision_id" % where,
            isinstance(decision_id, str) and decision_id in decision_ids,
            "%r is %s a recorded decision id"
            % (decision_id, "not" if decision_id not in decision_ids else ""),
        )
        ok &= report.check(
            "%s.approved_by" % where,
            isinstance(record.get("approved_by"), str) and bool(record["approved_by"].strip()),
            str(record.get("approved_by")),
        )
        ok &= report.check(
            "%s.reason" % where,
            isinstance(record.get("reason"), str) and bool(record["reason"].strip()),
            str(record.get("reason"))[:90],
        )
        date = record.get("date")
        if isinstance(date, str):
            try:
                dt.date.fromisoformat(date)
                report.check("%s.date" % where, True, date)
            except ValueError:
                ok &= report.check("%s.date" % where, False, "expected YYYY-MM-DD")
        else:
            ok &= report.check("%s.date" % where, False, "missing date")
        paths = record.get("paths")
        if not isinstance(paths, list) or not paths or not all(
            isinstance(item, str) and item for item in paths
        ):
            report.check("%s.paths" % where, False, "expected a non-empty list of globs")
            ok = False
        else:
            broad = [item for item in paths if not _is_protected(item) and not item.endswith("/**")]
            report.check(
                "%s.paths.protected" % where,
                not broad,
                "record covers unprotected path(s): %s" % broad if broad else "all paths are protected",
            )
            if broad:
                ok = False
        if ok:
            valid.append(record)
    report.check(
        "rules.records.valid",
        len(valid) > 0 or not changes,
        "%d valid record(s)" % len(valid),
    )
    return valid


def build_report(
    root: Path,
    *,
    base: str | None = "origin/main",
    rules_path: Path | None = None,
    decision_log: Path | None = None,
    decisions_file: str = DEFAULT_DECISIONS,
) -> common.Report:
    report = common.Report(TOOL)
    rules_path = rules_path or root / DEFAULT_RULES
    decision_log = decision_log or root / DEFAULT_DECISION_LOG
    decision_ids, decision_count = _decision_ids(root, decisions_file, decision_log)
    report.check(
        "decisions.available",
        decision_count > 0,
        "%d recorded decision id(s)" % decision_count,
    )
    document = _load_document(rules_path, report, "rules")
    if not isinstance(document, dict):
        report.fail(
            "rules.exists",
            "rule-change record not found or invalid: %s" % rules_path,
        )
        return report
    new_ids = {
        record.get("change_id")
        for record in (document.get("changes") or [])
        if isinstance(record, dict) and isinstance(record.get("change_id"), str)
    } - _base_change_ids(root, rules_path, base)
    valid = _validate_records(report, document, decision_ids)
    new_records = [record for record in valid if record.get("change_id") in new_ids]
    report.check(
        "rules.new_records",
        True,
        "%d new record(s) relative to base %r" % (len(new_records), base),
    )
    protected = _changed_paths(root, base, report)
    if not protected:
        report.check("rules.protected_changes", True, "no protected path changed")
        if new_records:
            report.warn(
                "%d new rule-change record(s) added without a protected change "
                "(unused record)" % len(new_records)
            )
        return report
    uncovered: list[str] = []
    for path in protected:
        covered = any(
            common.path_matches_any(record.get("paths") or [], path)
            for record in new_records
        )
        if not covered:
            uncovered.append(path)
    if uncovered:
        for path in uncovered:
            report.fail(
                "rules.uncovered_change",
                "protected governance path changed without a new rule-change "
                "record: %s — add an RC-nnnn record (decision_id + approved_by) "
                "to %s" % (path, rules_path.name),
            )
    else:
        report.check(
            "rules.covered",
            True,
            "all %d protected change(s) covered by new rule-change records"
            % len(protected),
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Fail when the governance surface (workflow, gate tools, licence/freeze "
            "rules) changes without a new approved rule-change record."
        ),
        epilog=(
            "Exit codes: 0 pass, 1 check failed, 2 configuration error. "
            "A record needs change_id, decision_id (D-nnn or DECISION_LOG id), "
            "approved_by, date, reason and protected paths."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref whose RULE_CHANGES.yaml defines the old records "
        "(default: origin/main; '' disables change detection).",
    )
    parser.add_argument(
        "--rules",
        default=None,
        help="Rule-change record (default: %s)." % DEFAULT_RULES,
    )
    parser.add_argument(
        "--decision-log",
        default=None,
        help="Governance decision log (default: %s)." % DEFAULT_DECISION_LOG,
    )
    args = parser.parse_args(argv)

    try:
        root = common.repo_root(args.root)
    except common.ConfigError as exc:
        return common.config_error(TOOL, str(exc))
    rules_path = Path(args.rules) if args.rules else root / DEFAULT_RULES
    if not rules_path.is_absolute():
        rules_path = (root / rules_path).resolve()
    decision_log = Path(args.decision_log) if args.decision_log else root / DEFAULT_DECISION_LOG
    if not decision_log.is_absolute():
        decision_log = (root / decision_log).resolve()
    report = build_report(
        root,
        base=args.base or None,
        rules_path=rules_path,
        decision_log=decision_log,
    )
    return common.emit(report, args.json)


if __name__ == "__main__":
    sys.exit(main())
