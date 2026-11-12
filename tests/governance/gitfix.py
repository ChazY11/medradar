"""Helpers for governance gate tests: throwaway git repos and gate invocation.

Fixtures are synthetic only (see ``fixtures/README.md``). No network, no real
data, no secrets: the restricted-token marker in the fixtures exists solely to
assert that gate logs never echo file content.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_DIR = REPO_ROOT / "tools" / "governance"
GOVERNANCE_SRC = REPO_ROOT / "docs" / "governance"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MARKER = "SYNTHETIC-RESTRICTED-TOKEN-42"


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    if check and result.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), result.stderr))
    return result


def init_repo(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "init", "-q")
    run_git(path, "config", "user.name", "governance-test")
    run_git(path, "config", "user.email", "refoundation-test")
    write(path / ".gitignore", "data/\n")
    return path


def write(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def commit(root: Path, message: str = "fixture") -> None:
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "-m", message)


def stage(root: Path, *paths: str) -> None:
    run_git(root, "add", *paths)


def run_gate(script: str, root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(GATE_DIR)
    return subprocess.run(
        [sys.executable, str(GATE_DIR / script), "--root", str(root), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def copy_policy(root: Path) -> None:
    write(
        Path(root) / "docs/governance/DATA_LICENSES.yaml",
        (GOVERNANCE_SRC / "DATA_LICENSES.yaml").read_text(encoding="utf-8"),
    )


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()
