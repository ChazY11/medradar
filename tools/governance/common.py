"""Shared helpers for the MedRadar governance gates (Python standard library only).

Every gate in ``tools/governance/`` uses this module so that they share:

* repository-root discovery (independent of the current working directory);
* read-only git queries (``git rev-parse``, ``git ls-files``, ``git diff``);
* deterministic YAML loading through :mod:`yamlmini`;
* a common pass/fail report with human-readable and ``--json`` output;
* one exit-code contract: 0 = pass, 1 = check failed, 2 = configuration/usage
  error (nothing was verified).

Nothing in this module writes to the repository, the network, or the clock;
governance output must be reproducible run to run.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

try:  # ``python tools/governance/check_x.py`` (directory on sys.path)
    import yamlmini  # type: ignore
except ImportError:  # pragma: no cover - ``python -m tools.governance.check_x``
    from . import yamlmini  # type: ignore

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2

YAML_SUBSET_HINT = (
    "see tools/governance/yamlmini.py for the supported YAML subset"
)

DEFAULT_STATE = "PROJECT_STATE.yaml"
DEFAULT_FROZEN = "docs/governance/FROZEN.yaml"
DEFAULT_LICENCES = "docs/governance/DATA_LICENSES.yaml"
DEFAULT_TEST_ARTIFACT = "docs/refoundation/phase0/_evidence/governance/pytest_count.json"

SCHEMA_STATE = "medradar.project_state.v2"
SCHEMA_FROZEN = "medradar.frozen.v1"
SCHEMA_LICENCES = "medradar.data_licenses.v1"
SCHEMA_TEST_ARTIFACT = "medradar.test_count.v1"


class ConfigError(RuntimeError):
    """Raised when the gate cannot verify anything (exit code 2)."""


def repo_root(start: str | Path | None = None) -> Path:
    """Return the repository root (the directory holding ``PROJECT_STATE.yaml``).

    ``start`` defaults to this module's location. The root is verified to
    contain ``PROJECT_STATE.yaml`` or a ``.git`` entry, so a gate can never run
    against an arbitrary directory by accident.
    """
    if start is not None:
        candidate = Path(start).expanduser()
        if not candidate.exists():
            raise ConfigError("--root does not exist: %s" % candidate)
        if candidate.is_file():
            candidate = candidate.parent
        candidate = candidate.resolve()
        if not (candidate / DEFAULT_STATE).is_file() and not (
            candidate / ".git"
        ).exists():
            raise ConfigError(
                "--root %s does not look like the MedRadar repository "
                "(no %s or .git)" % (candidate, DEFAULT_STATE)
            )
        return candidate
    here = Path(__file__).resolve().parents[2]
    if not (here / DEFAULT_STATE).is_file() and not (here / ".git").exists():
        raise ConfigError(
            "cannot locate the repository root from %s; pass --root" % here
        )
    return here


def rel_posix(path: Path, root: Path) -> str:
    """Repository-relative POSIX path (stable across platforms)."""
    return path.resolve().relative_to(root.resolve()).as_posix()


def is_within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# -- git ------------------------------------------------------------------


def run_git(root: Path, *args: str) -> tuple[int, str, str]:
    """Run a read-only git command. Returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - git is required
        raise ConfigError("git executable not found: %s" % exc) from exc
    return proc.returncode, proc.stdout, proc.stderr


def git_rev_parse(root: Path, ref: str) -> str | None:
    code, out, _ = run_git(root, "rev-parse", "--verify", ref + "^{commit}")
    if code != 0:
        return None
    value = out.strip()
    return value or None


def git_tracked_files(root: Path) -> list[str]:
    """All tracked files as repository-relative POSIX paths, sorted."""
    code, out, err = run_git(root, "ls-files", "-z")
    if code != 0:
        raise ConfigError("git ls-files failed: %s" % err.strip())
    return sorted(entry for entry in out.split("\0") if entry)


def git_diff_names(root: Path, ref: str, pathspec: str | None = None) -> list[str]:
    """Names changed between ``ref`` and the working tree (staged + unstaged)."""
    args = ["diff", "--name-only", ref]
    if pathspec is not None:
        args += ["--", pathspec]
    code, out, err = run_git(root, *args)
    if code != 0:
        raise ConfigError("git diff failed: %s" % err.strip())
    return sorted(entry for entry in out.splitlines() if entry)


# -- files ----------------------------------------------------------------


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def read_yaml(path: Path) -> object:
    """Load a governance YAML file through the documented subset parser."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError("cannot read %s: %s" % (path, exc)) from exc
    try:
        return yamlmini.loads(text, path=str(path))
    except yamlmini.YamlSubsetError as exc:
        raise ConfigError(str(exc)) from exc


def as_posix_patterns(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values.replace("\\", "/")]
    if isinstance(values, list):
        out: list[str] = []
        for item in values:
            if not isinstance(item, str):
                raise ConfigError("path pattern must be a string, got %r" % (item,))
            out.append(item.replace("\\", "/"))
        return out
    raise ConfigError("path patterns must be a string or list, got %r" % (values,))


@lru_cache(maxsize=256)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Translate a gitignore-style glob to a regex.

    ``**/`` matches zero or more directories, ``**`` matches anything,
    ``*``/``?`` never cross ``/``. Patterns are repo-relative POSIX paths.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile(r"\A" + "".join(out) + r"\Z")


def path_matches(pattern: str, path: str) -> bool:
    pattern = pattern.strip()
    if pattern.startswith("./"):
        pattern = pattern[2:]
    if pattern.startswith("/"):
        pattern = pattern[1:]
    return bool(_glob_regex(pattern).match(path))


def path_matches_any(patterns: list[str], path: str) -> bool:
    return any(path_matches(pattern, path) for pattern in patterns)


# -- report ---------------------------------------------------------------


class Report:
    """A deterministic checklist result shared by every gate."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self.checks: list[dict] = []
        self.warnings: list[str] = []

    def check(self, check_id: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"id": check_id, "ok": bool(ok), "detail": detail})
        return bool(ok)

    def fail(self, check_id: str, detail: str) -> None:
        self.check(check_id, False, detail)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def require(self, check_id: str, condition: bool, detail: str = "") -> bool:
        return self.check(check_id, condition, detail)

    @property
    def failures(self) -> list[dict]:
        return [check for check in self.checks if not check["ok"]]

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "check_count": len(self.checks),
            "failure_count": len(self.failures),
            "checks": self.checks,
            "warnings": self.warnings,
        }

    def render(self) -> str:
        lines: list[str] = []
        for check in self.checks:
            status = "[ok]  " if check["ok"] else "[FAIL]"
            detail = (": " + check["detail"]) if check["detail"] else ""
            lines.append("%s %s%s" % (status, check["id"], detail))
        for warning in self.warnings:
            lines.append("[WARN] %s" % warning)
        verdict = "PASS" if self.ok else "FAIL"
        lines.append(
            "%s %s (%d checks, %d failures, %d warnings)"
            % (verdict, self.tool, len(self.checks), len(self.failures), len(self.warnings))
        )
        return "\n".join(lines)


def emit(report: Report, as_json: bool) -> int:
    """Print the report and return the gate's exit code."""
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=False))
    else:
        print(report.render())
    return EXIT_PASS if report.ok else EXIT_FAIL


def config_error(tool: str, message: str) -> int:
    print("%s: ERROR: %s" % (tool, message), file=sys.stderr)
    return EXIT_CONFIG


# -- argparse -------------------------------------------------------------


def add_common_args(parser) -> None:
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root (default: derived from this script's location).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human checklist.",
    )
