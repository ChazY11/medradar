#!/usr/bin/env python3
"""Generate the repository views that are derived from PROJECT_STATE.yaml.

Generated outputs
-----------------
1. the ``status`` region of ``README.md``;
2. ``docs/RESEARCH_INDEX.md`` (whole file);
3. the ``unreleased`` region of ``CHANGELOG.md``.

Determinism and tamper detection
--------------------------------
Every generated region records two digests as HTML comments:

* ``source-sha256`` — the SHA-256 of the ``PROJECT_STATE.yaml`` bytes the region
  was generated from;
* ``payload-sha256`` — the SHA-256 of the generated markdown payload.

That makes the decision unambiguous, without reading the clock:

* region equals the expected bytes .......................... up to date, no write
* region came from the *current* state but the payload differs .. **hand-edited: FAIL**
* region records an older source digest and its own payload digest is
  self-consistent ........................................... stale: regenerate
* region's payload digest does not match its own payload ....... **hand-edited: FAIL**

Running ``gen_views.py`` twice therefore produces a byte-identical result (the
second run is a no-op), which is what the CI freshness job checks with
``git diff --exit-code``.

Usage:
    python tools/governance/gen_views.py            # verify + regenerate stale views
    python tools/governance/gen_views.py --check    # verify only (no writes)
    python tools/governance/gen_views.py --init     # bootstrap missing regions
    python tools/governance/gen_views.py --write    # force regeneration (restore)
"""

from __future__ import annotations

import argparse
import collections
import json
import posixpath
import re
import sys
from pathlib import Path

try:  # ``python tools/governance/gen_views.py``
    from . import common, yamlmini
except ImportError:  # ``python -m tools.governance.gen_views``
    import common  # type: ignore
    import yamlmini  # type: ignore

TOOL = "gen_views"
STATUS_MARKERS = ("<!-- BEGIN GENERATED: status -->", "<!-- END GENERATED: status -->")
UNRELEASED_MARKERS = (
    "<!-- BEGIN GENERATED: unreleased -->",
    "<!-- END GENERATED: unreleased -->",
)
RESEARCH_INDEX = "docs/RESEARCH_INDEX.md"
GENERATED_NOTE = (
    "<!-- generated: do not edit by hand; "
    "regenerate with tools/governance/gen_views.py -->"
)
SOURCE_LINE = "<!-- source-sha256: %s -->"
PAYLOAD_LINE = "<!-- payload-sha256: %s -->"
STATUS_ORDER = ("working", "draft", "retired")


# --------------------------------------------------------------------------
# payload rendering (pure functions of PROJECT_STATE.yaml)
# --------------------------------------------------------------------------


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _num(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return format(value, ",")
    return str(value)


def _status_counts(state: dict) -> collections.Counter:
    capabilities = state.get("capabilities") or []
    return collections.Counter(
        entry.get("status") for entry in capabilities if isinstance(entry, dict)
    )


def _counts_cell(state: dict) -> str:
    statuses = _status_counts(state)
    return " · ".join(
        "%d %s" % (statuses.get(status, 0), status) for status in STATUS_ORDER
    )


def _protection(state: dict) -> str:
    governance = state.get("governance") or {}
    return "applied" if governance.get("branch_protection_applied") is True else "not applied"


def render_status(state: dict) -> str:
    """README status-table fragment."""
    project = state.get("project") or {}
    git = state.get("git") or {}
    verified = state.get("verified") or {}
    release = state.get("release") or {}
    tests = state.get("tests") or {}
    snapshot = state.get("data_snapshot") or {}
    prs = ((state.get("open_work") or {}).get("prs")) or {}
    studies = state.get("research_studies") or []
    public_claims = sum(
        1
        for study in studies
        if isinstance(study, dict) and study.get("public_claim") is True
    )
    head = git.get("head", "")
    short = git.get("short", "")
    verified_commit = verified.get("commit", "")
    verified_short = verified_commit[:7] if isinstance(verified_commit, str) else "?"
    release_commit = release.get("commit")
    release_commit_short = release_commit[:7] if isinstance(release_commit, str) else None
    repository = project.get("repository", "")
    head_cell = "`%s`" % short
    if repository and head:
        head_cell = "[`%s`](%s/commit/%s)" % (short, repository, head)
    lines = [
        "**Project status** — generated from [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml) "
        "at `%s` by `python tools/governance/gen_views.py`; edit the state file, "
        "never this block." % state.get("generated_at", "?"),
        "",
        "| Item | Value |",
        "| --- | --- |",
        "| Observed main head | %s — %s (may lag main; stale-by-design is a warning) |"
        % (head_cell, _cell(str(git.get("committed_at", "?")).split("T")[0])),
        "| Verified baseline | `%s` (%s passed, %s collected) |"
        % (verified_short, _num(tests.get("passed")), _num(tests.get("collected"))),
        "| Release | %s%s |"
        % (
            _cell(release.get("version", "?")),
            " (`%s`)" % release_commit_short if release_commit_short else " (unreleased)",
        ),
        "| Tests | %s passed, %s skipped, %s failed (%s collected, offline) |"
        % (
            _num(tests.get("passed")),
            _num(tests.get("skipped")),
            _num(tests.get("failed")),
            _num(tests.get("collected")),
        ),
        "| Capabilities | %s |" % _cell(_counts_cell(state)),
        "| Research studies | %d (%d with a public claim) |"
        % (len(studies), public_claims),
        "| Data snapshot | %s — %s events (local build; `data/` is gitignored) |"
        % (_cell(snapshot.get("date", "?")), _num(snapshot.get("events"))),
        "| Open PRs | %s open (%s draft), %s merged |"
        % (
            _num(prs.get("open_count")),
            _num(prs.get("draft_count")),
            _num(prs.get("merged_count")),
        ),
        "| Branch protection | %s |" % _protection(state),
        "",
        "See [`docs/governance/GOVERNANCE.md`](docs/governance/GOVERNANCE.md) for the "
        "gates and [`docs/RESEARCH_INDEX.md`](docs/RESEARCH_INDEX.md) for the "
        "generated research index.",
        "",
    ]
    return "\n".join(lines)


def render_unreleased(state: dict) -> str:
    """CHANGELOG unreleased snapshot fragment."""
    git = state.get("git") or {}
    verified = state.get("verified") or {}
    release = state.get("release") or {}
    tests = state.get("tests") or {}
    snapshot = state.get("data_snapshot") or {}
    prs = ((state.get("open_work") or {}).get("prs")) or {}
    statuses = _status_counts(state)
    lines = [
        "## [Unreleased] — generated governance snapshot",
        "",
        "_Snapshot of [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml) at `%s`. "
        "Regenerate with `python tools/governance/gen_views.py`; do not edit "
        "this block by hand._" % state.get("generated_at", "?"),
        "",
        "- **Observed main head:** `%s` (%s) — may lag main; stale-but-ancestor is a warning"
        % (
            git.get("short", "?"),
            str(git.get("committed_at", "?")).split("T")[0],
        ),
        "- **Verified baseline:** `%s`; release **%s**%s"
        % (
            verified.get("commit", "?"),
            release.get("version", "?"),
            "" if release.get("commit") is None else " at `%s`" % str(release.get("commit"))[:7],
        ),
        "- **Tests:** %s passed, %s skipped, %s failed (%s collected)"
        % (
            _num(tests.get("passed")),
            _num(tests.get("skipped")),
            _num(tests.get("failed")),
            _num(tests.get("collected")),
        ),
        "- **Capabilities:** %d working, %d draft, %d retired"
        % (
            statuses.get("working", 0),
            statuses.get("draft", 0),
            statuses.get("retired", 0),
        ),
        "- **Open PRs:** %s open (%s draft), %s merged; branch protection %s"
        % (
            _num(prs.get("open_count")),
            _num(prs.get("draft_count")),
            _num(prs.get("merged_count")),
            _protection(state),
        ),
        "- **Data snapshot:** %s, %s events (local build; `data/` is gitignored)"
        % (_cell(snapshot.get("date", "?")), _num(snapshot.get("events"))),
        "",
    ]
    return "\n".join(lines)


def _link(root_relative_path: str) -> str:
    """Relative markdown link from docs/ to a repository path."""
    return posixpath.relpath(root_relative_path, "docs")


def _evidence_cell(value: object) -> str:
    if isinstance(value, str):
        return "[`%s`](%s)" % (value, _link(value))
    return "?"


def render_research_index(state: dict) -> str:
    """Whole-file docs/RESEARCH_INDEX.md."""
    studies = state.get("research_studies") or []
    capabilities = state.get("capabilities") or []
    decisions = ((state.get("decisions") or {}).get("index")) or []
    lines = [
        "# Research index",
        "",
        "> Generated from [`PROJECT_STATE.yaml`](../PROJECT_STATE.yaml) at `%s` by "
        "`tools/governance/gen_views.py`. Do not edit this file by hand: edit the "
        "state file and regenerate. A hand edit fails "
        "`python tools/governance/gen_views.py --check` and the governance "
        "workflow." % state.get("generated_at", "?"),
        "",
        "## Research studies",
        "",
        "| Study | Verdict | Freeze | Public claim | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not studies:
        lines.append("| _none recorded_ |  |  |  |  |")
    for study in studies:
        if not isinstance(study, dict):
            continue
        lines.append(
            "| `%s` — %s | %s | `%s` | %s | %s |"
            % (
                _cell(study.get("id", "?")),
                _cell(study.get("title", "?")),
                _cell(study.get("verdict", "?")),
                _cell(study.get("freeze_ref", "?")),
                "yes" if study.get("public_claim") is True else "no",
                _evidence_cell(study.get("evidence")),
            )
        )
    lines += [
        "",
        "## Capabilities",
        "",
        "| Capability | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    if not capabilities:
        lines.append("| _none recorded_ |  |  |")
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        lines.append(
            "| `%s` — %s | %s | %s |"
            % (
                _cell(capability.get("id", "?")),
                _cell(capability.get("title", "?")),
                _cell(capability.get("status", "?")),
                _evidence_cell(capability.get("evidence")),
            )
        )
    lines += [
        "",
        "## Decisions index",
        "",
        "| Decision | Title | Record |",
        "| --- | --- | --- |",
    ]
    if not decisions:
        lines.append("| _none recorded_ |  |  |")
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        lines.append(
            "| `%s` | %s | %s |"
            % (
                _cell(decision.get("id", "?")),
                _cell(decision.get("title", "?")),
                _evidence_cell(decision.get("path")),
            )
        )
    lines += [
        "",
        "---",
        "",
        "_Generated artefact. The full decision record lives in "
        "[`research/DECISIONS.md`](../research/DECISIONS.md); capability evidence "
        "paths are verified by `python tools/governance/check_state.py`._",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# region bookkeeping
# --------------------------------------------------------------------------


def _region_meta(payload_sha: str, source_sha: str) -> list[str]:
    return [GENERATED_NOTE, SOURCE_LINE % source_sha, PAYLOAD_LINE % payload_sha]


def expected_region(payload: str, source_sha: str) -> str:
    """The exact bytes between (but excluding) the two region markers."""
    payload_sha = common.sha256_bytes(payload.encode("utf-8"))
    return "\n" + "\n".join(_region_meta(payload_sha, source_sha)) + "\n" + payload


def expected_block(payload: str, source_sha: str, markers: tuple[str, str]) -> str:
    begin, end = markers
    return begin + expected_region(payload, source_sha) + end


_META_RE = re.compile(
    r"<!--\s*(source-sha256|payload-sha256)\s*:\s*([0-9a-f]{64})\s*-->"
)


def parse_region(text: str, markers: tuple[str, str]) -> tuple[dict | None, str | None]:
    begin, end = markers
    start = text.find(begin)
    if start < 0:
        return None, "missing begin marker %r" % begin
    end_at = text.find(end, start + len(begin))
    if end_at < 0:
        return None, "missing end marker %r" % end
    inner = text[start + len(begin) : end_at]
    lines = inner.split("\n")
    index = 1 if lines and lines[0] == "" else 0
    meta: dict[str, str] = {}
    payload_start = index
    position = index
    while position < len(lines) and lines[position].startswith("<!--"):
        match = _META_RE.match(lines[position].strip())
        if match:
            meta[match.group(1)] = match.group(2)
        payload_start = position + 1
        position += 1
    return {
        "inner": inner,
        "meta": meta,
        "payload": "\n".join(lines[payload_start:]),
        "block_start": start,
        "block_end": end_at,
    }, None


def classify(actual: dict, expected_inner: str, source_sha: str) -> tuple[str, str]:
    """Return (status, detail) where status is ok | stale | tampered."""
    if actual["inner"] == expected_inner:
        return "ok", "up to date"
    source_meta = actual["meta"].get("source-sha256")
    payload_meta = actual["meta"].get("payload-sha256")
    if not source_meta or not payload_meta:
        return "tampered", "region has no generated-source metadata (hand-edited?)"
    if source_meta == source_sha:
        return (
            "tampered",
            "region records the current source digest but its content differs; "
            "hand-edited generated region",
        )
    if payload_meta == common.sha256_bytes(actual["payload"].encode("utf-8")):
        return "stale", "generated from an older PROJECT_STATE.yaml (%s)" % source_meta[:12]
    return (
        "tampered",
        "region payload digest does not match its own content; hand-edited region",
    )


def replace_region(
    text: str, markers: tuple[str, str], payload: str, source_sha: str
) -> str:
    actual, error = parse_region(text, markers)
    if error is not None:
        raise ValueError(error)
    begin, end = markers
    return (
        text[: actual["block_start"]]
        + expected_block(payload, source_sha, markers)
        + text[actual["block_end"] + len(end) :]
    )


def insert_block(text: str, block: str, anchor: str) -> str:
    """Insert a generated block at the documented anchor."""
    if anchor == "end":
        return text.rstrip("\n") + "\n\n" + block + "\n"
    if anchor == "before-first-h2":
        match = re.search(r"(?m)^## \[", text)
        if match:
            return text[: match.start()] + block + "\n" + text[match.start() :]
        return text.rstrip("\n") + "\n\n" + block + "\n"
    raise ValueError("unknown anchor %r" % anchor)


# --------------------------------------------------------------------------
# targets and the write/verify engine
# --------------------------------------------------------------------------


class RegionTarget:
    def __init__(
        self,
        name: str,
        path: str,
        payload_fn,
        markers: tuple[str, str],
        anchor: str,
    ) -> None:
        self.name = name
        self.path = path
        self.payload_fn = payload_fn
        self.markers = markers
        self.anchor = anchor


class WholeFileTarget:
    def __init__(self, name: str, path: str, payload_fn) -> None:
        self.name = name
        self.path = path
        self.payload_fn = payload_fn


def _whole_file_content(payload: str, source_sha: str) -> str:
    payload_sha = common.sha256_bytes(payload.encode("utf-8"))
    header = "\n".join(_region_meta(payload_sha, source_sha))
    return header + "\n" + payload


def _whole_file_meta(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in text.split("\n")[:4]:
        match = _META_RE.match(line.strip())
        if match:
            meta[match.group(1)] = match.group(2)
    return meta


def inspect_target(target, root: Path, payload: str, source_sha: str) -> tuple[str, str]:
    """Classify a target without writing. Returns (status, detail)."""
    path = root / target.path
    if not path.is_file():
        return "missing", "file not found"
    text = path.read_text(encoding="utf-8")
    if isinstance(target, RegionTarget):
        actual, error = parse_region(text, target.markers)
        if error is not None:
            return "missing_markers", error
        return classify(actual, expected_region(payload, source_sha), source_sha)
    expected = _whole_file_content(payload, source_sha)
    if text == expected:
        return "ok", "up to date"
    meta = _whole_file_meta(text)
    if meta.get("source-sha256") == source_sha:
        return (
            "tampered",
            "file was generated from the current state but its content changed; "
            "hand-edited",
        )
    payload_text = "\n".join(text.split("\n")[3:])
    if meta.get("payload-sha256") == common.sha256_bytes(payload_text.encode("utf-8")):
        return "stale", "generated from an older state"
    return (
        "tampered",
        "file has no self-consistent generated header; hand-edited",
    )


def write_target(target, root: Path, payload: str, source_sha: str) -> None:
    path = root / target.path
    if isinstance(target, RegionTarget):
        text = path.read_text(encoding="utf-8")
        new_text = replace_region(text, target.markers, payload, source_sha)
    else:
        new_text = _whole_file_content(payload, source_sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8", newline="\n")


def bootstrap_region(target: RegionTarget, root: Path, payload: str, source_sha: str) -> None:
    path = root / target.path
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    actual, error = parse_region(text, target.markers)
    block = expected_block(payload, source_sha, target.markers)
    if error is None:
        new_text = replace_region(text, target.markers, payload, source_sha)
    else:
        new_text = insert_block(text, block, target.anchor) if text else block + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8", newline="\n")


def run(
    root: Path,
    targets: list,
    state: dict,
    source_sha: str,
    *,
    check_only: bool,
    force: bool,
    init: bool,
) -> tuple[list[dict], bool]:
    results: list[dict] = []
    ok = True
    for target in targets:
        payload = target.payload_fn(state)
        status, detail = inspect_target(target, root, payload, source_sha)
        if not check_only:
            if force and status != "ok":
                write_target(target, root, payload, source_sha)
                status, detail = "written", "forced regeneration"
            elif status == "stale":
                write_target(target, root, payload, source_sha)
                status, detail = "written", detail
            elif init and status in ("missing", "missing_markers"):
                if isinstance(target, RegionTarget):
                    bootstrap_region(target, root, payload, source_sha)
                else:
                    write_target(target, root, payload, source_sha)
                status, detail = "written", "bootstrapped (--init)"
            elif init and status in ("stale", "tampered"):
                write_target(target, root, payload, source_sha)
                status, detail = "written", "bootstrapped (--init)"
        if status in ("tampered", "missing", "missing_markers"):
            ok = False
        results.append(
            {
                "target": target.name,
                "path": target.path,
                "status": status,
                "detail": detail,
            }
        )
    return results, ok


def default_targets() -> list:
    """The views generated from PROJECT_STATE.yaml, in stable order."""
    return [
        RegionTarget("readme-status", "README.md", render_status, STATUS_MARKERS, "end"),
        WholeFileTarget("research-index", RESEARCH_INDEX, render_research_index),
        RegionTarget(
            "changelog-unreleased",
            "CHANGELOG.md",
            render_unreleased,
            UNRELEASED_MARKERS,
            "before-first-h2",
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description=(
            "Generate and verify the views derived from PROJECT_STATE.yaml "
            "(README status block, docs/RESEARCH_INDEX.md, CHANGELOG snapshot)."
        ),
        epilog=(
            "Exit codes: 0 all regions valid, 1 a region is stale, missing or "
            "hand-edited, 2 configuration error. Determinism: two consecutive "
            "runs produce byte-identical files; the second run performs no writes."
        ),
    )
    common.add_common_args(parser)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify only; never write, and fail if any region is stale or missing.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Bootstrap missing marker blocks at their documented anchors.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Force regeneration (restoration after a deliberate edit).",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="State file (default: PROJECT_STATE.yaml).",
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
    source_bytes = state_path.read_bytes()
    try:
        state = yamlmini.loads(source_bytes.decode("utf-8"), path=str(state_path))
    except (UnicodeDecodeError, yamlmini.YamlSubsetError) as exc:
        return common.config_error(TOOL, "cannot read %s: %s" % (state_path, exc))
    if not isinstance(state, dict):
        return common.config_error(TOOL, "%s must be a YAML mapping" % state_path)
    source_sha = common.sha256_bytes(source_bytes)

    targets = default_targets()
    results, ok = run(
        root,
        targets,
        state,
        source_sha,
        check_only=args.check,
        force=args.write,
        init=args.init,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "tool": TOOL,
                    "ok": ok,
                    "source_sha256": source_sha,
                    "results": results,
                },
                indent=2,
            )
        )
    else:
        for result in results:
            passed = result["status"] in ("ok", "written")
            print(
                "%s %s (%s): %s"
                % (
                    "PASS" if passed else "FAIL",
                    result["target"],
                    result["path"],
                    result["detail"],
                )
            )
        print("%s %s (%d targets)" % ("PASS" if ok else "FAIL", TOOL, len(results)))
    return common.EXIT_PASS if ok else common.EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
