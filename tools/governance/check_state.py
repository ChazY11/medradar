#!/usr/bin/env python3
"""Validate PROJECT_STATE.yaml against the repository and its own contract.

What this gate blocks
---------------------
* a state file that is malformed, missing a required section, or has duplicate
  identifiers;
* a recorded `main` head that does not match the actual git ref
  (`--main-ref`, default: the ref named in the state file, i.e. `origin/main`);
* a recorded commit date, subject, version or tracked-file count that does not
  match the actual commit / `pyproject.toml` / main tree;
* a `tests` claim that disagrees with the committed measurement artifact
  (`docs/refoundation/phase0/_evidence/governance/pytest_count.json`);
* a referenced path (capability evidence, study evidence, decision source,
  freeze plan, test artifact, ...) that does not exist;
* a decision or freeze identifier that is cited but does not exist;
* a capability/study status outside `working | draft | retired`.

Exit codes: 0 pass, 1 check failed, 2 configuration/usage error.

Usage:
    python tools/governance/check_state.py [--json] [--drift-warn]
    python tools/governance/check_state.py --main-ref main --tests-mode off
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

try:  # ``python tools/governance/check_state.py``
    from . import common
except ImportError:  # ``python -m tools.governance.check_state``
    import common  # type: ignore

TOOL = "check_state"
HEAD_RE = re.compile(r"\A[0-9a-f]{40}\Z")
FREEZE_ID_RE = re.compile(r"\AFZ-[0-9]{3}\Z")
CAPABILITY_STATUSES = {"working", "draft", "retired"}
PATH_KEYS = {
    "artifact",
    "evidence",
    "pages_source",
    "path",
    "plan",
    "source",
    "version_source",
}
DECISION_HEADING_RE = re.compile(r"^## (D-[0-9]{3})\b", re.MULTILINE)


# --------------------------------------------------------------------------
# small structural helpers
# --------------------------------------------------------------------------


def _mapping(report: common.Report, value: object, where: str) -> dict | None:
    if isinstance(value, dict):
        return value
    report.fail("%s.type" % where, "expected a mapping, found %s" % type(value).__name__)
    return None


def _sequence(report: common.Report, value: object, where: str) -> list | None:
    if isinstance(value, list):
        return value
    report.fail("%s.type" % where, "expected a list, found %s" % type(value).__name__)
    return None


def _string(
    report: common.Report,
    mapping: dict,
    key: str,
    where: str,
    required: bool = True,
) -> str | None:
    label = "%s.%s" % (where, key)
    if key not in mapping:
        if required:
            report.fail(label, "missing required field")
        return None
    value = mapping[key]
    if not isinstance(value, str) or value.strip() == "":
        report.fail(label, "expected a non-empty string, found %r" % (value,))
        return None
    report.check(label, True, value if len(value) <= 80 else value[:77] + "...")
    return value


def _integer(
    report: common.Report,
    mapping: dict,
    key: str,
    where: str,
    required: bool = True,
    minimum: int = 0,
) -> int | None:
    label = "%s.%s" % (where, key)
    if key not in mapping:
        if required:
            report.fail(label, "missing required field")
        return None
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int):
        report.fail(label, "expected an integer, found %r" % (value,))
        return None
    if value < minimum:
        report.fail(label, "expected >= %d, found %d" % (minimum, value))
        return None
    report.check(label, True, str(value))
    return value


def _boolean(
    report: common.Report, mapping: dict, key: str, where: str
) -> bool | None:
    label = "%s.%s" % (where, key)
    if key not in mapping:
        report.fail(label, "missing required field")
        return None
    value = mapping[key]
    if not isinstance(value, bool):
        report.fail(label, "expected true/false, found %r" % (value,))
        return None
    report.check(label, True, str(value))
    return value


def _unique_ids(
    report: common.Report, entries: list, where: str, id_field: str = "id"
) -> list[str]:
    seen: dict[str, int] = {}
    ids: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        identifier = entry.get(id_field)
        if not isinstance(identifier, str) or identifier == "":
            continue
        ids.append(identifier)
        if identifier in seen:
            report.fail(
                "%s.unique_ids" % where,
                "duplicate id %r at positions %d and %d"
                % (identifier, seen[identifier], index),
            )
        else:
            seen[identifier] = index
    if len(ids) != len(set(ids)):
        return ids
    report.check("%s.unique_ids" % where, True, "%d unique ids" % len(ids))
    return ids


def _walk_paths(value: object, trail: str = ""):
    """Yield (trail, string_value) for every field whose key names a path."""
    if isinstance(value, dict):
        for key, item in value.items():
            child = ("%s.%s" % (trail, key)) if trail else str(key)
            if key in PATH_KEYS and isinstance(item, str):
                yield child, item
            else:
                yield from _walk_paths(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_paths(item, "%s[%d]" % (trail, index))


def _check_path(report: common.Report, root: Path, trail: str, raw: str) -> None:
    label = "path.%s" % trail
    if raw.startswith("/") or re.match(r"\A[A-Za-z]:[\\/]", raw):
        report.fail(label, "absolute paths are not allowed: %r" % raw)
        return
    if ".." in Path(raw).parts:
        report.fail(label, "path must stay inside the repository: %r" % raw)
        return
    target = root / raw
    if not target.exists():
        report.fail(label, "referenced path does not exist: %r" % raw)
        return
    kind = "dir" if target.is_dir() else "file"
    report.check(label, True, "%s (%s)" % (raw, kind))


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def _check_project(report: common.Report, root: Path, project: object) -> None:
    data = _mapping(report, project, "project")
    if data is None:
        return
    for key in ("name", "owner", "repository", "licence", "mission"):
        _string(report, data, key, "project")
    repository = data.get("repository")
    if isinstance(repository, str):
        report.check(
            "project.repository_url",
            repository.startswith("https://github.com/"),
            repository,
        )


def _check_main(
    report: common.Report, root: Path, project: object, main: object, main_ref: str
) -> None:
    data = _mapping(report, main, "main")
    if data is None:
        return
    head = _string(report, data, "head", "main")
    short = _string(report, data, "short", "main")
    ref = _string(report, data, "ref", "main")
    committed_at = _string(report, data, "committed_at", "main")
    subject = _string(report, data, "commit_subject", "main")
    version = _string(report, data, "version", "main")
    tracked = _integer(report, data, "tracked_files", "main", minimum=1)
    _string(report, data, "version_source", "main")

    if head is not None:
        report.check(
            "main.head.format",
            bool(HEAD_RE.match(head)),
            head if HEAD_RE.match(head) else "expected 40 lowercase hex characters",
        )
        if short is not None:
            report.check(
                "main.short.consistent",
                head.startswith(short) and len(short) == 7,
                "short=%r head=%r" % (short, head),
            )

    resolved_ref = main_ref or (ref if isinstance(ref, str) else "origin/main")
    actual_head = common.git_rev_parse(root, resolved_ref)
    if actual_head is None:
        report.fail(
            "main.head.git",
            "cannot resolve git ref %r; fetch it (git fetch origin main) "
            "or pass --main-ref" % resolved_ref,
        )
    else:
        report.check(
            "main.head.git",
            head is not None and actual_head == head,
            "%s resolves to %s, state records %s"
            % (resolved_ref, actual_head, head),
        )

    if actual_head is not None:
        code, out, err = common.run_git(root, "show", "-s", "--format=%cI", actual_head)
        if code == 0:
            actual_date = out.strip()
            report.check(
                "main.committed_at.git",
                committed_at is None or actual_date == committed_at,
                "expected %s, found %s" % (committed_at, actual_date),
            )
        else:
            report.fail("main.committed_at.git", "git show failed: %s" % err.strip())
        code, out, err = common.run_git(root, "show", "-s", "--format=%s", actual_head)
        if code == 0:
            actual_subject = out.strip()
            report.check(
                "main.commit_subject.git",
                subject is None or actual_subject == subject,
                "expected %r, found %r" % (subject, actual_subject),
            )
        else:
            report.fail("main.commit_subject.git", "git show failed: %s" % err.strip())

        if tracked is not None:
            code, out, err = common.run_git(
                root, "ls-tree", "-r", "--name-only", actual_head
            )
            if code == 0:
                actual_count = len([line for line in out.splitlines() if line])
                report.check(
                    "main.tracked_files.git",
                    actual_count == tracked,
                    "main tree has %d files, state records %d"
                    % (actual_count, tracked),
                )
            else:
                report.fail(
                    "main.tracked_files.git", "git ls-tree failed: %s" % err.strip()
                )

        workflows = data.get("workflows")
        if _sequence(report, workflows, "main.workflows") is not None:
            code, out, _ = common.run_git(
                root, "ls-tree", "-r", "--name-only", actual_head, "--", ".github/workflows"
            )
            if code == 0:
                actual_workflows = sorted(
                    Path(path).stem
                    for path in out.splitlines()
                    if path.startswith(".github/workflows/") and path.endswith(".yml")
                )
                declared = sorted(w for w in workflows if isinstance(w, str))
                report.check(
                    "main.workflows.git",
                    actual_workflows == declared,
                    "main has %r, state records %r"
                    % (actual_workflows, declared),
                )
            else:
                report.fail(
                    "main.workflows.git", "git ls-tree failed for workflows"
                )

    if version is not None:
        pyproject = root / "pyproject.toml"
        if not pyproject.is_file():
            report.fail("main.version.pyproject", "pyproject.toml is missing")
        else:
            text = pyproject.read_text(encoding="utf-8")
            match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
            if match is None:
                report.fail(
                    "main.version.pyproject", "no project version in pyproject.toml"
                )
            else:
                report.check(
                    "main.version.pyproject",
                    match.group(1) == version,
                    "pyproject=%s state=%s" % (match.group(1), version),
                )
    # pages source must be a directory
    if isinstance(project, dict) and isinstance(project.get("pages_source"), str):
        pages = root / project["pages_source"]
        report.check(
            "project.pages_source.directory",
            pages.is_dir(),
            "%r is %s" % (project["pages_source"], "a directory" if pages.is_dir() else "not a directory"),
        )


def _check_tests(
    report: common.Report,
    root: Path,
    tests: object,
    main_head: str | None,
    artifact_path: Path,
    tests_mode: str,
    drift_warn: bool,
) -> None:
    data = _mapping(report, tests, "tests")
    if data is None:
        return
    collected = _integer(report, data, "collected", "tests", minimum=1)
    passed = _integer(report, data, "passed", "tests")
    skipped = _integer(report, data, "skipped", "tests")
    failed = _integer(report, data, "failed", "tests")
    _integer(report, data, "subtests_passed", "tests", required=False)
    _string(report, data, "command", "tests")
    _string(report, data, "measured_at", "tests")
    _string(report, data, "artifact", "tests")
    _string(report, data, "tested_head", "tests")
    policy = _string(report, data, "policy", "tests")
    if policy is not None:
        report.check(
            "tests.policy.value",
            policy in {"strict", "warn"},
            "expected 'strict' or 'warn', found %r" % policy,
        )
    if None not in (collected, passed, skipped, failed):
        report.check(
            "tests.arithmetic",
            passed + skipped + failed == collected,
            "passed+skipped+failed=%d collected=%d"
            % (passed + skipped + failed, collected),
        )
        report.check("tests.failed.zero", failed == 0, "failed=%d" % failed)

    if tests_mode == "off":
        report.warn("tests: verification disabled with --tests-mode off")
        return

    if not artifact_path.is_file():
        report.fail(
            "tests.artifact.exists",
            "measurement artifact missing: %s (run python -m pytest and "
            "python tools/governance/record_tests.py)" % artifact_path,
        )
        return
    report.check("tests.artifact.exists", True, str(artifact_path.relative_to(root)))
    try:
        with artifact_path.open("r", encoding="utf-8") as handle:
            artifact = json.load(handle)
    except (OSError, ValueError) as exc:
        report.fail("tests.artifact.parse", "cannot parse measurement artifact: %s" % exc)
        return
    if not isinstance(artifact, dict):
        report.fail("tests.artifact.parse", "artifact is not a mapping")
        return
    report.check(
        "tests.artifact.schema",
        artifact.get("schema") == common.SCHEMA_TEST_ARTIFACT,
        "expected %s, found %r"
        % (common.SCHEMA_TEST_ARTIFACT, artifact.get("schema")),
    )
    a_collected = artifact.get("collected")
    a_passed = artifact.get("passed")
    a_skipped = artifact.get("skipped")
    a_failed = artifact.get("failed")
    a_head = artifact.get("tested_head")
    report.check(
        "tests.artifact.tests_unchanged",
        artifact.get("tests_unchanged_from_head") is True,
        "artifact records that tests/ matched the measured commit",
    )
    if not isinstance(a_head, str) or not HEAD_RE.match(a_head):
        report.fail(
            "tests.artifact.tested_head",
            "expected a 40-hex commit in tested_head, found %r" % (a_head,),
        )
    else:
        exists = (
            common.run_git(root, "cat-file", "-e", a_head + "^{commit}")[0] == 0
        )
        ancestor = exists and (
            common.run_git(root, "merge-base", "--is-ancestor", a_head, "HEAD")[0] == 0
        )
        report.check(
            "tests.artifact.tested_head",
            exists and ancestor,
            "tested_head %s is %s and %s an ancestor of HEAD"
            % (
                a_head[:12],
                "present" if exists else "missing",
                "is" if ancestor else "is NOT",
            ),
        )
        if main_head is not None and a_head != main_head:
            report.warn(
                "test count was measured on %s, not main.head %s; refresh with "
                "`python tools/governance/record_tests.py` when the change lands"
                % (a_head[:12], main_head[:12])
            )
    report.check(
        "tests.artifact.failed_zero",
        a_failed == 0,
        "artifact records failed=%r" % (a_failed,),
    )
    mismatches: list[str] = []
    for name, declared, measured in (
        ("collected", collected, a_collected),
        ("passed", passed, a_passed),
        ("skipped", skipped, a_skipped),
    ):
        if declared is not None and declared != measured:
            mismatches.append("%s: state=%r artifact=%r" % (name, declared, measured))
    if mismatches:
        strict = (policy or "strict") == "strict" and not drift_warn
        message = "declared test counts disagree with the measurement artifact: %s" % "; ".join(
            mismatches
        )
        if strict:
            report.fail("tests.artifact.match", message)
        else:
            report.check("tests.artifact.match", True, "drift warning mode")
            report.warn(message)
    else:
        report.check(
            "tests.artifact.match",
            True,
            "%d collected / %d passed / %d skipped"
            % (a_collected, a_passed, a_skipped),
        )


def _check_data_snapshot(report: common.Report, data: object) -> None:
    mapping = _mapping(report, data, "data_snapshot")
    if mapping is None:
        return
    date = _string(report, mapping, "date", "data_snapshot")
    if date is not None:
        try:
            dt.date.fromisoformat(date)
            report.check("data_snapshot.date.format", True, date)
        except ValueError:
            report.fail(
                "data_snapshot.date.format", "expected YYYY-MM-DD, found %r" % date
            )
    _integer(report, mapping, "events", "data_snapshot", minimum=1)
    _string(report, mapping, "evidence", "data_snapshot")
    _string(report, mapping, "storage", "data_snapshot")
    sources = _sequence(report, mapping.get("sources"), "data_snapshot.sources")
    if sources is None:
        return
    report.check(
        "data_snapshot.sources.nonempty", len(sources) > 0, "%d sources" % len(sources)
    )
    _unique_ids(report, sources, "data_snapshot.sources")
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            report.fail(
                "data_snapshot.sources[%d].type" % index, "expected a mapping"
            )
            continue
        _string(report, source, "id", "data_snapshot.sources[%d]" % index)
        _integer(report, source, "rows", "data_snapshot.sources[%d]" % index)


def _check_capabilities(report: common.Report, data: object) -> None:
    entries = _sequence(report, data, "capabilities")
    if entries is None:
        return
    report.check(
        "capabilities.nonempty", len(entries) > 0, "%d entries" % len(entries)
    )
    _unique_ids(report, entries, "capabilities")
    for index, entry in enumerate(entries):
        where = "capabilities[%d]" % index
        if not isinstance(entry, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        _string(report, entry, "id", where)
        _string(report, entry, "title", where)
        status = _string(report, entry, "status", where)
        if status is not None and status not in CAPABILITY_STATUSES:
            report.fail(
                "%s.status" % where,
                "expected one of %s, found %r"
                % (sorted(CAPABILITY_STATUSES), status),
            )
        _string(report, entry, "evidence", where)


def _check_studies(
    report: common.Report, data: object, freeze_ids: set[str]
) -> None:
    entries = _sequence(report, data, "research_studies")
    if entries is None:
        return
    _unique_ids(report, entries, "research_studies")
    for index, entry in enumerate(entries):
        where = "research_studies[%d]" % index
        if not isinstance(entry, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        _string(report, entry, "id", where)
        _string(report, entry, "title", where)
        _string(report, entry, "verdict", where)
        _string(report, entry, "evidence", where)
        _boolean(report, entry, "public_claim", where)
        freeze_ref = _string(report, entry, "freeze_ref", where)
        if freeze_ref is not None:
            report.check(
                "%s.freeze_ref.exists" % where,
                freeze_ref in freeze_ids,
                "freeze_ref=%r, known freeze ids=%s"
                % (freeze_ref, sorted(freeze_ids) or "none"),
            )


def _check_open_work(report: common.Report, root: Path, data: object) -> None:
    mapping = _mapping(report, data, "open_work")
    if mapping is None:
        return
    prs = _mapping(report, mapping.get("prs"), "open_work.prs")
    if prs is not None:
        merged = _integer(report, prs, "merged_count", "open_work.prs")
        opened = _integer(report, prs, "open_count", "open_work.prs")
        drafts = _integer(report, prs, "draft_count", "open_work.prs")
        _string(report, prs, "merged_range", "open_work.prs")
        _string(report, prs, "open_range", "open_work.prs")
        _string(report, prs, "measured_from", "open_work.prs")
        if None not in (opened, drafts):
            report.check(
                "open_work.prs.drafts_le_open",
                drafts <= opened,
                "drafts=%d open=%d" % (drafts, opened),
            )
    branches = _mapping(report, mapping.get("branches"), "open_work.branches")
    if branches is not None:
        verified = _boolean(report, branches, "verified", "open_work.branches")
        _integer(report, branches, "local_refs", "open_work.branches")
        _integer(report, branches, "remote_refs", "open_work.branches")
        _string(report, branches, "measured_from", "open_work.branches")
        if verified is True:
            report.warn(
                "open_work.branches is marked verified=true, but no gate verifies it; "
                "set verified=false or add a check"
            )


def _check_governance(report: common.Report, data: object) -> None:
    mapping = _mapping(report, data, "governance")
    if mapping is None:
        return
    applied = _boolean(report, mapping, "branch_protection_applied", "governance")
    _string(report, mapping, "plan", "governance")
    _string(report, mapping, "note", "governance")
    checks = _sequence(report, mapping.get("required_status_checks"), "governance.required_status_checks")
    if checks is not None:
        report.check(
            "governance.required_status_checks.list",
            all(isinstance(item, str) for item in checks),
            "%d entries" % len(checks),
        )
        if applied is True and not checks:
            report.fail(
                "governance.required_status_checks.nonempty_when_applied",
                "branch protection is recorded as applied but no required checks are listed",
            )
        if applied is False and checks:
            report.warn(
                "governance declares required checks but branch protection is not applied"
            )


def _check_decisions(report: common.Report, root: Path, data: object) -> None:
    mapping = _mapping(report, data, "decisions")
    if mapping is None:
        return
    source = _string(report, mapping, "source", "decisions")
    count = _integer(report, mapping, "count", "decisions", minimum=1)
    _string(report, mapping, "format", "decisions")
    index = _sequence(report, mapping.get("index"), "decisions.index")
    if index is None:
        return
    _unique_ids(report, index, "decisions.index")
    headings: set[str] = set()
    source_path = root / source if source else None
    if source_path is None or not source_path.is_file():
        report.fail(
            "decisions.source.exists",
            "decision record not found: %r" % (source,),
        )
    else:
        text = source_path.read_text(encoding="utf-8", errors="replace")
        found = DECISION_HEADING_RE.findall(text)
        headings = set(found)
        report.check(
            "decisions.source.headings",
            len(found) == len(headings),
            "%d headings, %d unique" % (len(found), len(headings)),
        )
        if count is not None:
            report.check(
                "decisions.count.matches_source",
                count == len(headings),
                "state records %d, %s has %d headings"
                % (count, source, len(headings)),
            )
    for index_number, entry in enumerate(index):
        where = "decisions.index[%d]" % index_number
        if not isinstance(entry, dict):
            report.fail("%s.type" % where, "expected a mapping")
            continue
        identifier = _string(report, entry, "id", where)
        _string(report, entry, "title", where)
        _string(report, entry, "path", where)
        if identifier is not None and headings:
            report.check(
                "%s.heading_exists" % where,
                identifier in headings,
                "%r is %s in %s"
                % (
                    identifier,
                    "present" if identifier in headings else "missing",
                    source,
                ),
            )


def _check_not_claimed(report: common.Report, data: object) -> None:
    entries = _sequence(report, data, "not_claimed")
    if entries is None:
        return
    report.check(
        "not_claimed.nonempty", len(entries) > 0, "%d entries" % len(entries)
    )
    for index, entry in enumerate(entries):
        report.check(
            "not_claimed[%d].string" % index,
            isinstance(entry, str) and entry.strip() != "",
            str(entry)[:80],
        )


def _freeze_ids(report: common.Report, root: Path, frozen_arg: str | None) -> set[str]:
    path = Path(frozen_arg) if frozen_arg else root / common.DEFAULT_FROZEN
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        report.fail("frozen.exists", "freeze spec not found: %s" % path)
        return set()
    try:
        document = common.read_yaml(path)
    except common.ConfigError as exc:
        report.fail("frozen.parse", str(exc))
        return set()
    if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
        report.fail("frozen.parse", "expected a mapping with an 'entries' list")
        return set()
    allowed_freeze_schemas = {"medradar.frozen.v1", "medradar.frozen.v2"}
    report.check(
        "frozen.schema",
        document.get("schema") in allowed_freeze_schemas,
        "expected one of %s, found %r"
        % (sorted(allowed_freeze_schemas), document.get("schema")),
    )
    ids: set[str] = set()
    for index, entry in enumerate(document["entries"]):
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("freeze_id")
        if not isinstance(identifier, str) or not FREEZE_ID_RE.match(identifier):
            report.fail(
                "frozen.entries[%d].freeze_id" % index,
                "expected an id like FZ-001, found %r" % (identifier,),
            )
            continue
        ids.add(identifier)
    report.check(
        "frozen.entries.unique", len(ids) == len(document["entries"]), "%d entries" % len(ids)
    )
    return ids


def build_report(
    root: Path,
    state_path: Path,
    main_ref: str | None,
    test_artifact: Path,
    tests_mode: str,
    drift_warn: bool,
    frozen_path: str | None,
) -> common.Report:
    """Run every check and return the report (also used by tests)."""
    report = common.Report(TOOL)
    try:
        document = common.read_yaml(state_path)
    except common.ConfigError as exc:
        report.fail("state.parse", str(exc))
        return report
    if not isinstance(document, dict):
        report.fail("state.parse", "PROJECT_STATE.yaml must be a mapping")
        return report

    required = (
        "schema",
        "generated_at",
        "project",
        "main",
        "tests",
        "data_snapshot",
        "capabilities",
        "research_studies",
        "open_work",
        "governance",
        "decisions",
        "not_claimed",
    )
    missing = [key for key in required if key not in document]
    report.check(
        "state.required_sections",
        not missing,
        "present" if not missing else "missing: %s" % ", ".join(missing),
    )
    report.check(
        "state.schema",
        document.get("schema") == common.SCHEMA_STATE,
        "expected %s, found %r"
        % (common.SCHEMA_STATE, document.get("schema")),
    )
    generated_at = document.get("generated_at")
    if isinstance(generated_at, str):
        try:
            dt.datetime.fromisoformat(generated_at)
            report.check("state.generated_at.format", True, generated_at)
        except ValueError:
            report.fail(
                "state.generated_at.format",
                "expected ISO-8601 with offset, found %r" % generated_at,
            )
    else:
        report.fail("state.generated_at", "missing or not a string")

    _check_project(report, root, document.get("project"))
    _check_main(report, root, document.get("project"), document.get("main"), main_ref)

    main_data = document.get("main") if isinstance(document.get("main"), dict) else {}
    declared_head = main_data.get("head") if isinstance(main_data.get("head"), str) else None
    _check_tests(
        report,
        root,
        document.get("tests"),
        declared_head,
        test_artifact,
        tests_mode,
        drift_warn,
    )
    _check_data_snapshot(report, document.get("data_snapshot"))
    _check_capabilities(report, document.get("capabilities"))
    freeze_ids = _freeze_ids(report, root, frozen_path)
    _check_studies(report, document.get("research_studies"), freeze_ids)
    _check_open_work(report, root, document.get("open_work"))
    _check_governance(report, document.get("governance"))
    _check_decisions(report, root, document.get("decisions"))
    _check_not_claimed(report, document.get("not_claimed"))

    for trail, raw in _walk_paths(document):
        _check_path(report, root, trail, raw)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Validate PROJECT_STATE.yaml: structure, git main head, referenced "
            "paths, duplicate ids and the measured test count."
        ),
        epilog=(
            "Exit codes: 0 pass, 1 check failed, 2 configuration error. "
            "The YAML subset is documented in tools/governance/yamlmini.py."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--state",
        default=None,
        help="State file (default: PROJECT_STATE.yaml).",
    )
    parser.add_argument(
        "--frozen",
        default=None,
        help="Freeze spec used to resolve study freeze_ref ids "
        "(default: docs/governance/FROZEN.yaml).",
    )
    parser.add_argument(
        "--main-ref",
        default=None,
        help="Git ref that must match main.head (default: the ref declared in "
        "PROJECT_STATE.yaml, i.e. origin/main).",
    )
    parser.add_argument(
        "--test-artifact",
        default=None,
        help="Test-count measurement artifact (default: %s)."
        % common.DEFAULT_TEST_ARTIFACT,
    )
    parser.add_argument(
        "--tests-mode",
        choices=["artifact", "off"],
        default="artifact",
        help="Verify the declared test count against the artifact (default) or skip.",
    )
    parser.add_argument(
        "--drift-warn",
        action="store_true",
        help="Downgrade a test-count mismatch to a warning (drift-warning mode).",
    )
    args = parser.parse_args(argv)

    try:
        root = common.repo_root(args.root)
    except common.ConfigError as exc:
        return common.config_error(TOOL, str(exc))

    state_path = Path(args.state) if args.state else root / common.DEFAULT_STATE
    if not state_path.is_absolute():
        state_path = (root / state_path).resolve()
    if not state_path.is_file():
        return common.config_error(TOOL, "state file not found: %s" % state_path)
    artifact = (
        Path(args.test_artifact)
        if args.test_artifact
        else root / common.DEFAULT_TEST_ARTIFACT
    )
    if not artifact.is_absolute():
        artifact = (root / artifact).resolve()

    report = build_report(
        root=root,
        state_path=state_path,
        main_ref=args.main_ref,
        test_artifact=artifact,
        tests_mode=args.tests_mode,
        drift_warn=args.drift_warn,
        frozen_path=args.frozen,
    )
    return common.emit(report, args.json)


if __name__ == "__main__":
    sys.exit(main())
