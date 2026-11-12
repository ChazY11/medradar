#!/usr/bin/env python3
"""Verify that committed data files respect the per-source redistribution policy.

What this gate blocks
---------------------
* a tracked file that looks like raw content from a **RED** source. RED means
  "not redistributable": the raw bytes may only live under the gitignored
  ``data/`` tree, so every tracked match is a violation, no exception possible;
* a tracked file matching an **AMBER** source pattern without an explicit,
  reviewed policy entry (an AMBER source may contribute derived aggregates,
  but only ones somebody wrote down and justified);
* a policy file that is internally inconsistent (unknown status, unknown
  source reference, a raw pattern outside ``data/``, a stale entry);
* a ``data/`` root that is not actually gitignored, which would make the RED
  rule meaningless.

GREEN sources may be redistributed with attribution, so their tracked files
need no entry (the attribution is still required to be recorded).

Exit codes: 0 pass, 1 check failed, 2 configuration/usage error.

Usage:
    python tools/governance/check_licence.py [--json]
    python tools/governance/check_licence.py --licences docs/governance/DATA_LICENSES.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:  # ``python tools/governance/check_licence.py``
    from . import common
except ImportError:  # ``python -m tools.governance.check_licence``
    import common  # type: ignore

TOOL = "check_licence"
STATUSES = {"GREEN", "AMBER", "RED"}
ENTRY_KINDS = {"derived-aggregate", "derived-report", "metadata", "claims", "index"}
REQUIRED_SOURCE_FIELDS = ("source_id", "status", "may_redistribute", "attribution")


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


def _check_sources(report: common.Report, root: Path, document: dict) -> dict[str, dict]:
    sources = document.get("sources")
    if not isinstance(sources, list) or not sources:
        report.fail("licences.sources", "expected a non-empty 'sources' list")
        return {}
    report.check("licences.sources.nonempty", True, "%d sources" % len(sources))
    by_id: dict[str, dict] = {}
    raw_root = str(((document.get("policy") or {}).get("raw_root")) or "data/")
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
    for index, source in enumerate(sources):
        where = "sources[%d]" % index
        if not isinstance(source, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        for field in ("source_id", "status", "attribution"):
            value = source.get(field)
            report.check(
                "%s.%s" % (where, field),
                isinstance(value, str) and value.strip() != "",
                "%r" % (value,),
            )
        report.check(
            "%s.may_redistribute.type" % where,
            isinstance(source.get("may_redistribute"), bool),
            "%r" % (source.get("may_redistribute"),),
        )
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            continue
        if source_id in by_id:
            report.fail("%s.source_id.unique" % where, "duplicate source_id %r" % source_id)
            continue
        by_id[source_id] = source
        status = source.get("status")
        if status not in STATUSES:
            report.fail(
                "%s.status" % where,
                "expected one of %s, found %r" % (sorted(STATUSES), status),
            )
            continue
        may = source.get("may_redistribute")
        expected = status == "GREEN"
        report.check(
            "%s.may_redistribute.consistent" % where,
            isinstance(may, bool) and may == expected,
            "%s source %r must have may_redistribute: %s, found %r"
            % (status, source_id, str(expected).lower(), may),
        )
        raw_patterns = _string_list(report, source, "raw_patterns", where)
        if raw_patterns:
            outside = [item for item in raw_patterns if not item.startswith(raw_root)]
            report.check(
                "%s.raw_patterns.under_data" % where,
                not outside,
                "raw pattern(s) outside %s: %s" % (raw_root, outside)
                if outside
                else "%d raw patterns under %s" % (len(raw_patterns), raw_root),
            )
        _string_list(report, source, "tracked_patterns", where)
    return by_id


def _check_policy_entries(
    report: common.Report,
    sources: dict[str, dict],
    document: dict,
    tracked: list[str],
) -> dict[tuple[str, str], dict]:
    entries = document.get("policy_entries")
    covered: dict[tuple[str, str], dict] = {}
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        report.fail("licences.policy_entries", "expected a list")
        return covered
    report.check(
        "licences.policy_entries.count", True, "%d explicit entries" % len(entries)
    )
    for index, entry in enumerate(entries):
        where = "policy_entries[%d]" % index
        if not isinstance(entry, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        source_id = entry.get("source_id")
        report.check(
            "%s.source_id.known" % where,
            isinstance(source_id, str) and source_id in sources,
            "%r is %s" % (source_id, "known" if source_id in sources else "unknown"),
        )
        if isinstance(source_id, str) and source_id in sources:
            report.check(
                "%s.red_source_forbidden" % where,
                sources[source_id].get("status") != "RED",
                "RED sources may not have redistribution entries",
            )
        kind = entry.get("kind")
        report.check(
            "%s.kind" % where,
            kind in ENTRY_KINDS,
            "expected one of %s, found %r" % (sorted(ENTRY_KINDS), kind),
        )
        reason = entry.get("reason")
        report.check(
            "%s.reason" % where,
            isinstance(reason, str) and bool(reason.strip()),
            str(reason)[:100],
        )
        has_path = isinstance(entry.get("path"), str) and entry.get("path")
        has_pattern = isinstance(entry.get("path_pattern"), str) and entry.get(
            "path_pattern"
        )
        report.check(
            "%s.path_xor_pattern" % where,
            bool(has_path) != bool(has_pattern),
            "declare exactly one of path or path_pattern",
        )
        matched: list[str] = []
        if has_path:
            matched = [entry["path"]] if entry["path"] in tracked else []
            report.check(
                "%s.path_is_tracked" % where,
                bool(matched),
                "%r %s a tracked file"
                % (entry["path"], "is" if matched else "is NOT"),
            )
        elif has_pattern:
            matched = [path for path in tracked if common.path_matches(entry["path_pattern"], path)]
            report.check(
                "%s.path_pattern_matches" % where,
                bool(matched),
                "%r matches %d tracked file(s)" % (entry["path_pattern"], len(matched)),
            )
        if isinstance(source_id, str):
            for path in matched:
                covered[(source_id, path)] = entry
    return covered


def _check_tracked_files(
    report: common.Report,
    sources: dict[str, dict],
    tracked: list[str],
    covered: dict[tuple[str, str], dict],
) -> None:
    patterns_by_source: dict[str, list[str]] = {}
    for source_id, source in sources.items():
        value = source.get("tracked_patterns")
        if isinstance(value, str):
            patterns_by_source[source_id] = [value]
        elif isinstance(value, list):
            patterns_by_source[source_id] = [
                item for item in value if isinstance(item, str)
            ]
        else:
            patterns_by_source[source_id] = []

    green_seen = 0
    amber_seen = 0
    red_violations: list[tuple[str, str]] = []
    amber_violations: list[tuple[str, str]] = []
    for path in tracked:
        for source_id, source in sources.items():
            patterns = patterns_by_source.get(source_id, [])
            if not patterns or not common.path_matches_any(patterns, path):
                continue
            status = source.get("status")
            if status == "GREEN":
                green_seen += 1
            elif status == "AMBER":
                amber_seen += 1
                if (source_id, path) not in covered:
                    amber_violations.append((source_id, path))
            elif status == "RED":
                red_violations.append((source_id, path))
    report.check(
        "tracked.green_files",
        True,
        "%d tracked file/source matches are GREEN (redistributable with attribution)"
        % green_seen,
    )
    if red_violations:
        for source_id, path in red_violations:
            report.fail(
                "tracked.red_violation",
                "RED source %r has a tracked file outside data/: %s "
                "(RED content may only live under the gitignored data/ tree)"
                % (source_id, path),
            )
    else:
        report.check(
            "tracked.red_violation", True, "no tracked file matches a RED source pattern"
        )
    if amber_violations:
        for source_id, path in amber_violations:
            report.fail(
                "tracked.amber_policy",
                "AMBER source %r matches tracked file %s with no explicit "
                "policy_entries record" % (source_id, path),
            )
    else:
        report.check(
            "tracked.amber_policy",
            True,
            "%d AMBER file match(es) are all covered by explicit policy entries"
            % amber_seen,
        )
    # AMBER/RED sources must declare which tracked paths would be attributable.
    for source_id, source in sources.items():
        if source.get("status") in ("AMBER", "RED"):
            patterns = patterns_by_source.get(source_id, [])
            report.check(
                "sources.%s.tracked_patterns" % source_id,
                bool(patterns),
                "AMBER/RED source %r declares %d tracked pattern(s)"
                % (source_id, len(patterns)),
            )


def build_report(root: Path, licences_path: Path) -> common.Report:
    report = common.Report(TOOL)
    if not licences_path.is_file():
        report.fail("licences.exists", "licence policy not found: %s" % licences_path)
        return report
    try:
        document = common.read_yaml(licences_path)
    except common.ConfigError as exc:
        report.fail("licences.parse", str(exc))
        return report
    if not isinstance(document, dict):
        report.fail("licences.parse", "DATA_LICENSES.yaml must be a mapping")
        return report
    report.check(
        "licences.schema",
        document.get("schema") == common.SCHEMA_LICENCES,
        "expected %s, found %r"
        % (common.SCHEMA_LICENCES, document.get("schema")),
    )
    policy = document.get("policy")
    if not isinstance(policy, dict):
        report.fail("licences.policy", "expected a 'policy' mapping")
        policy = {}
    report.check(
        "licences.policy.default_status",
        policy.get("default_status") in STATUSES,
        "default_status=%r" % (policy.get("default_status"),),
    )
    report.check(
        "licences.policy.rule",
        isinstance(policy.get("rule"), str) and bool(policy.get("rule").strip()),
        "rule is documented",
    )
    try:
        tracked = common.git_tracked_files(root)
    except common.ConfigError as exc:
        report.fail("licences.tracked_files", str(exc))
        return report
    report.check("licences.tracked_files", True, "%d tracked files scanned" % len(tracked))
    sources = _check_sources(report, root, document)
    covered = _check_policy_entries(report, sources, document, tracked)
    _check_tracked_files(report, sources, tracked, covered)
    notes = document.get("review_notes")
    report.check(
        "licences.review_notes",
        isinstance(notes, list) and all(isinstance(item, str) for item in notes),
        "%d review note(s)"
        % (len(notes) if isinstance(notes, list) else 0),
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Verify committed data files against the per-source licence policy: "
            "RED sources may not be committed, AMBER sources need explicit entries."
        ),
        epilog=(
            "Exit codes: 0 pass, 1 check failed, 2 configuration error. "
            "Tracked files come from `git ls-files`; untracked files are ignored "
            "on purpose (they are not redistributed)."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--licences",
        default=None,
        help="Licence policy (default: %s)." % common.DEFAULT_LICENCES,
    )
    args = parser.parse_args(argv)

    try:
        root = common.repo_root(args.root)
    except common.ConfigError as exc:
        return common.config_error(TOOL, str(exc))
    licences_path = (
        Path(args.licences) if args.licences else root / common.DEFAULT_LICENCES
    )
    if not licences_path.is_absolute():
        licences_path = (root / licences_path).resolve()
    report = build_report(root, licences_path)
    return common.emit(report, args.json)


if __name__ == "__main__":
    sys.exit(main())
