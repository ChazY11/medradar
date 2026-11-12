"""Unit tests for the deterministic state-bump flow."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import gitfix
from tools.governance import yamlmini


def _seed(root: Path) -> Path:
    gitfix.init_repo(root)
    gitfix.write(
        root / "PROJECT_STATE.yaml",
        (gitfix.REPO_ROOT / "PROJECT_STATE.yaml").read_text(encoding="utf-8"),
    )
    gitfix.write(
        root / "pyproject.toml",
        (gitfix.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    )
    gitfix.commit(root, "state fixture")
    gitfix.write(root / "docs/extra.md", "simulated main advance\n")
    gitfix.commit(root, "simulated main advance")
    return root


def _bump(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(gitfix.GATE_DIR / "bump_state.py"),
            "--root",
            str(root),
            *args,
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
    )


class BumpStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = _seed(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _head(self) -> str:
        return gitfix.run_git(self.root, "rev-parse", "HEAD").stdout.strip()

    def _state(self) -> dict:
        return yamlmini.load(str(self.root / "PROJECT_STATE.yaml"))

    def test_bump_records_the_ref_head_and_tree_counts(self):
        result = _bump(self.root, "--ref", "HEAD")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = self._state()
        head = self._head()
        self.assertEqual(state["main"]["head"], head)
        self.assertEqual(state["main"]["short"], head[:7])
        self.assertEqual(state["main"]["ref"], "HEAD")
        self.assertEqual(state["main"]["version"], "0.5.0")
        tracked = gitfix.run_git(
            self.root, "ls-tree", "-r", "--name-only", "HEAD"
        ).stdout.splitlines()
        self.assertEqual(state["main"]["tracked_files"], len(tracked))
        self.assertEqual(state["main"]["workflows"], [])

    def test_second_run_is_a_noop(self):
        _bump(self.root, "--ref", "HEAD")
        before = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        second = _bump(self.root, "--ref", "HEAD")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("UP TO DATE", second.stdout)
        after = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_dry_run_does_not_write(self):
        before = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        result = _bump(self.root, "--ref", "HEAD", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--- PROJECT_STATE.yaml", result.stdout)
        after = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_generated_at_is_the_ref_commit_time(self):
        _bump(self.root, "--ref", "HEAD")
        expected = gitfix.run_git(
            self.root, "show", "-s", "--format=%cI", "HEAD"
        ).stdout.strip()
        self.assertEqual(self._state()["generated_at"], expected)


if __name__ == "__main__":
    unittest.main()
