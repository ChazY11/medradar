"""Unit tests for the deterministic state-bump flow.

Root-cause fix for the old flaky test: the seed used to copy the LIVE repo-root
PROJECT_STATE.yaml/pyproject.toml, so the fixture depended on mutable repository
state; every bump call also ignored its exit code. The seed is now a static
fixture under ``fixtures/`` and every call asserts success. The timestamp test
compares normalized instants (epoch seconds), not formatted strings.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from . import gitfix
from tools.governance import yamlmini

STATE_FIXTURE = gitfix.FIXTURES / "state_schema_v2.yaml"
PYPROJECT_FIXTURE = gitfix.FIXTURES / "pyproject_fixture.toml"


def _seed(root: Path) -> Path:
    gitfix.init_repo(root)
    gitfix.write(root / "PROJECT_STATE.yaml", STATE_FIXTURE.read_text(encoding="utf-8"))
    gitfix.write(root / "pyproject.toml", PYPROJECT_FIXTURE.read_text(encoding="utf-8"))
    gitfix.commit(root, "static fixture state")
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


def _instant(value: str) -> int:
    """Timezone/format-independent instant (epoch seconds) for a git ISO date."""
    return int(dt.datetime.fromisoformat(value).timestamp())


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

    def _bump_ok(self, *args: str) -> subprocess.CompletedProcess:
        result = _bump(self.root, *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_bump_records_the_ref_head_and_tree_counts(self):
        self._bump_ok("--ref", "HEAD", "--no-views")
        state = self._state()
        head = self._head()
        self.assertEqual(state["git"]["head"], head)
        self.assertEqual(state["git"]["short"], head[:7])
        self.assertEqual(state["git"]["ref"], "HEAD")
        self.assertEqual(state["verified"]["commit"], head)
        self.assertEqual(state["release"]["version"], "9.9.9")
        self.assertIsNone(state["release"]["commit"])
        tracked = gitfix.run_git(
            self.root, "ls-tree", "-r", "--name-only", "HEAD"
        ).stdout.splitlines()
        self.assertEqual(state["git"]["tracked_files"], len(tracked))
        self.assertEqual(state["git"]["workflows"], [])

    def test_second_run_is_a_noop(self):
        self._bump_ok("--ref", "HEAD", "--no-views")
        before = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        second = self._bump_ok("--ref", "HEAD", "--no-views")
        self.assertIn("UP TO DATE", second.stdout)
        after = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_dry_run_does_not_write(self):
        before = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        result = self._bump_ok("--ref", "HEAD", "--dry-run")
        self.assertIn("--- PROJECT_STATE.yaml", result.stdout)
        after = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_generated_at_is_the_ref_commit_time(self):
        self._bump_ok("--ref", "HEAD", "--no-views")
        expected_text = gitfix.run_git(
            self.root, "show", "-s", "--format=%cI", "HEAD"
        ).stdout.strip()
        actual_text = self._state()["generated_at"]
        self.assertEqual(
            _instant(actual_text),
            _instant(expected_text),
            "generated_at must be the ref commit instant: actual=%r expected=%r"
            % (actual_text, expected_text),
        )

    def test_release_commit_is_preserved(self):
        self._bump_ok("--ref", "HEAD", "--no-views")
        state = self._state()
        released = state["git"]["head"]
        text = (self.root / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
        text = text.replace("  commit: null", "  commit: %s" % released, 1)
        (self.root / "PROJECT_STATE.yaml").write_text(text, encoding="utf-8", newline="\n")
        gitfix.commit(self.root, "record a release commit")
        self._bump_ok("--ref", "HEAD", "--no-views")
        self.assertEqual(self._state()["release"]["commit"], released)
        self.assertEqual(self._state()["git"]["head"], self._head())


if __name__ == "__main__":
    unittest.main()
